"""爆款拆解：一条内容为什么火 —— 钩子、结构节拍、情绪点、评论区热词，外加可复用的结构模板。

* 入口：贴链接、条目详情、灵感库条目。拆过的内容一律收进灵感库，结果存在 ``library_items.meta.breakdown``，
  下次直接读；「照这个结构写」用这条灵感库条目做来源、把结构模板写进创作思路。
* 评论：已入库的内容用评论服务的缓存（没有就试着抓一次）；贴进来的链接按平台直接抓热门评论，抓不到就只拆正文。
* 评论热词先本地按词频粗算一遍（没有分词库，按 2–4 字片段计数并去掉被包含的短片段），再交给模型挑出真正的梗。
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ValidationError
from app.models.content import ContentItem
from app.models.content_observation import ContentComment
from app.models.library import LibraryItem
from app.services import prompt_kit
from app.utils.prompt_safety import sanitize_prompt_input

logger = logging.getLogger(__name__)

MAX_COMMENTS = 30
STOP = set(
    "的了是我你他她它们在有就不也都还这那个啊吧呢吗哈哈哈哈一个什么怎么因为所以但是而且如果真的就是还是可以没有已经自己"
)

SYSTEM_PROMPT = (
    "你是做过很多爆款的内容操盘手。拆解用户给的一条内容为什么能火，给可以照着用的结论，不要空话。"
    "只根据给出的标题、正文、指标和评论判断；材料不够的地方直说「材料里看不出」，没有画面材料时视觉相关的判断标明「推断」。"
    "<how_to_analyze>钩子不只是第一句话，而是开场的整体设计：文字（标题、封面字）、口播第一句、情节悬念、画面。"
    "「为什么火」只给一个主要机制（例如身份认同、解释了一个大家说不清的问题、替人表达情绪、内容有用值得收藏），"
    "用正文或评论原话做证据，不要堆砌理论；情绪被触动、认同观点、愿意转发是三件不同的事，分开说。"
    "不预测播放量。模板只借结构，不复用原句。</how_to_analyze>" + prompt_kit.UNTRUSTED + "只返回 JSON："
    '{"verdict":"一句话说它为什么火（30 字内）",'
    '"hook":{"text":"开头钩子原话或概括","type":"反差/悬念/痛点/利益/身份/数字 之一","why":"为什么抓人"},'
    '"beats":[{"name":"节拍名（如 抛问题）","does":"这一段做了什么"}],'
    '"emotions":[{"point":"情绪点（如 替打工人出气）","evidence":"正文或评论里的依据"}],'
    '"comment_words":[{"word":"评论区热词或梗","meaning":"大家在玩什么"}],'
    '"template":"可复用的结构模板，用 1. 2. 3. 分行，每行写这一步要做什么，换个话题也能套",'
    '"titles":["照这个套路的 3 个标题示例（换成通用话题）"]}'
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def hot_phrases(texts: list[str], *, top: int = 12) -> list[tuple[str, int]]:
    """评论里反复出现的 2–4 字片段（中文无分词时的粗糙热词）。至少出现在两条评论里才算。"""
    counter: Counter[str] = Counter()
    for t in texts:
        seen: set[str] = set()
        for run in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9]{2,}", t or ""):
            if run.isascii():
                seen.add(run.lower())
                continue
            for n in (4, 3, 2):
                for i in range(len(run) - n + 1):
                    seg = run[i : i + n]
                    if sum(ch in STOP for ch in seg) * 2 >= n:
                        continue
                    seen.add(seg)
        counter.update(seen)
    picked: list[tuple[str, int]] = []
    for seg, cnt in sorted(counter.items(), key=lambda kv: (-kv[1], -len(kv[0]))):
        if cnt < 2:
            break
        # 被更长且同样频繁的片段包含的不要（「打工」被「打工人」吃掉）
        if any(seg in p and c >= cnt for p, c in picked):
            continue
        picked.append((seg, cnt))
        if len(picked) >= top:
            break
    return picked


async def _comments_for_content(db: AsyncSession, content_id: int) -> list[str]:
    from app.services import comments as comments_svc

    rows = (
        (
            await db.execute(
                select(ContentComment)
                .where(ContentComment.content_id == content_id)
                .order_by(ContentComment.like_count.desc().nullslast())
                .limit(MAX_COMMENTS)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        try:
            await comments_svc.collect(db, content_id)
        except Exception as exc:  # noqa: BLE001 — 评论抓不到不影响拆正文
            logger.info("breakdown comments collect failed: %s", str(exc)[:200])
            await db.rollback()
            return []
        rows = (
            (
                await db.execute(
                    select(ContentComment).where(ContentComment.content_id == content_id).limit(MAX_COMMENTS)
                )
            )
            .scalars()
            .all()
        )
    return [r.text for r in rows if r.text]


async def _comments_for_url(db: AsyncSession, url: str) -> list[str]:
    from app.services import comments as comments_svc
    from app.services.library import parse_link
    from app.services.platforms import ADAPTERS, COMMENTS

    platform, pid = parse_link(url)
    if not pid or platform not in comments_svc.COMMENT_PLATFORMS or platform not in ADAPTERS:
        return []
    if COMMENTS not in ADAPTERS[platform].capabilities:
        return []
    if platform == "xiaohongshu":
        if "xsec_token=" not in url:
            return []
        pid = url
    try:
        got = await comments_svc._fetch(db, platform, pid)
    except Exception as exc:  # noqa: BLE001
        logger.info("breakdown url comments failed: %s", str(exc)[:200])
        return []
    return [c.text for c in got[:MAX_COMMENTS] if c.text]


async def resolve_item(
    db: AsyncSession, *, url: str | None = None, content_id: int | None = None, library_item_id: int | None = None
) -> tuple[LibraryItem, ContentItem | None]:
    from app.services import library as lib

    if library_item_id:
        item = await db.get(LibraryItem, library_item_id)
        if item is None:
            raise ValidationError("灵感库里没有这条")
    elif content_id:
        try:
            item = await lib.add_from_content(db, content_id, method="breakdown")
        except lib.LibraryNotFoundError as exc:
            raise ValidationError("这条内容不存在") from exc
    elif url:
        try:
            item = await lib.add_from_link(db, url, method="breakdown")
        except lib.LibraryError as exc:
            raise ValidationError(str(exc)) from exc
    else:
        raise ValidationError("给一个链接、内容或灵感库条目")
    content = await db.get(ContentItem, item.content_id) if item.content_id else None
    return item, content


def _material(item: LibraryItem, content: ContentItem | None, comments: list[str]) -> dict[str, Any]:
    metrics = (item.meta or {}).get("metrics") or {}
    body = item.body or ""
    if content is not None:
        body = "\n".join(filter(None, [content.summary, content.raw_content])) or body
    return {
        "platform": item.platform or (content.platform if content else None) or "网页",
        "title": item.title,
        "author": item.author,
        "metrics": {k: v for k, v in metrics.items() if isinstance(v, int | float)},
        "body": body,
        "comments": comments,
    }


def _messages(m: dict[str, Any], phrases: list[tuple[str, int]]) -> list[dict[str, str]]:
    comments = "\n".join(f"- {sanitize_prompt_input(c, max_chars=200)}" for c in m["comments"][:MAX_COMMENTS])
    user = (
        f"平台：{m['platform']}\n标题：{sanitize_prompt_input(m['title'] or '', max_chars=200)}\n"
        f"作者：{m['author'] or '未知'}\n指标：{m['metrics'] or '无'}\n\n"
        f"正文：\n{sanitize_prompt_input(m['body'] or '（没有正文，只有标题）', max_chars=4000)}\n\n"
        f"热门评论（{len(m['comments'])} 条）：\n{comments or '（没抓到评论）'}\n\n"
        f"评论高频片段（词，出现条数）：{', '.join(f'{w}({c})' for w, c in phrases) or '无'}"
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _clean(reply: Any, phrases: list[tuple[str, int]]) -> dict[str, Any]:
    if not isinstance(reply, dict):
        raise AppException("拆解失败：模型没有返回结果", 503, {"code": "model_unavailable"})

    def strs(v: Any, n: int) -> list[str]:
        return [str(x).strip() for x in (v or []) if str(x).strip()][:n]

    def dicts(v: Any, keys: tuple[str, ...], n: int) -> list[dict[str, str]]:
        out = []
        for x in v or []:
            if isinstance(x, dict) and str(x.get(keys[0]) or "").strip():
                out.append({k: str(x.get(k) or "").strip() for k in keys})
        return out[:n]

    hook = reply.get("hook") if isinstance(reply.get("hook"), dict) else {}
    counts = dict(phrases)
    words = dicts(reply.get("comment_words"), ("word", "meaning"), 8)
    for w in words:
        w["count"] = counts.get(w["word"], 0)  # type: ignore[assignment]
    return {
        "verdict": str(reply.get("verdict") or "").strip()[:80],
        "hook": {k: str(hook.get(k) or "").strip() for k in ("text", "type", "why")},
        "beats": dicts(reply.get("beats"), ("name", "does"), 8),
        "emotions": dicts(reply.get("emotions"), ("point", "evidence"), 5),
        "comment_words": words,
        "template": str(reply.get("template") or "").strip()[:2000],
        "titles": strs(reply.get("titles"), 3),
    }


async def breakdown(
    db: AsyncSession,
    *,
    url: str | None = None,
    content_id: int | None = None,
    library_item_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    from app.services.llm import call_llm_json

    item, content = await resolve_item(db, url=url, content_id=content_id, library_item_id=library_item_id)
    cached = (item.meta or {}).get("breakdown")
    if cached and not force:
        return {"item_id": item.id, "title": item.title, "url": item.url, "platform": item.platform, **cached}
    if content is not None:
        comments = await _comments_for_content(db, content.id)
    elif item.url:
        comments = await _comments_for_url(db, item.url)
    else:
        comments = []
    m = _material(item, content, comments)
    phrases = hot_phrases(comments)
    try:
        reply = await call_llm_json(_messages(m, phrases), temperature=0.4, max_tokens=1800, scene="breakdown")
    except Exception as exc:  # noqa: BLE001
        logger.warning("breakdown llm failed: %s", str(exc)[:200])
        raise AppException("拆解失败，请检查模型配置或稍后重试", 503, {"code": "model_unavailable"}) from exc
    result = _clean(reply, phrases)
    result.update({"comments_used": len(comments), "phrases": [[w, c] for w, c in phrases], "at": _now()})
    item = await db.get(LibraryItem, item.id)
    meta = deepcopy(item.meta or {})
    meta["breakdown"] = result
    item.meta = meta
    await db.commit()
    return {"item_id": item.id, "title": item.title, "url": item.url, "platform": item.platform, **result}


def intent_from(b: dict[str, Any], title: str) -> str:
    """「照这个结构写」写进创作思路的文字。"""
    lines = [f"参考爆款：{title}"]
    if b.get("verdict"):
        lines.append(f"它为什么火：{b['verdict']}")
    hook = b.get("hook") or {}
    if hook.get("text"):
        lines.append(f"钩子（{hook.get('type') or '—'}）：{hook['text']}")
    if b.get("template"):
        lines += ["", "照这个结构写：", b["template"]]
    return "\n".join(lines)[:5000]
