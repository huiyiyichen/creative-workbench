"""平台版本规则（设计文档 6.1）。改规则只改这里。"""

from __future__ import annotations

PLATFORM_RULES: dict[str, dict] = {
    "xhs": {
        "label": "小红书",
        "title_max": 20,
        "body_max": 1000,
        "tags_min": 3,
        "tags_max": 8,
        "cover_text_max": 12,
        "images_min": 3,
        "images_max": 9,
        "format": "text",
        "guide": "口语、分段短句、适度表情符号；正文不超过 1000 字；3–8 个话题；封面文案 12 字内；给 3–9 张配图建议。",
        "publish_url": "https://creator.xiaohongshu.com/publish/publish",
    },
    "zhihu": {
        "label": "知乎",
        "title_max": 100,
        "body_max": 20000,
        "format": "markdown",
        "guide": "Markdown；用小标题分节；论证清楚，有数据和例子；文末列出来源。",
        "publish_url": "https://zhuanlan.zhihu.com/write",
    },
    "wechat": {
        "label": "公众号",
        "title_max": 64,
        "summary_max": 120,
        "body_max": 20000,
        "format": "html",
        "guide": "标题、摘要（≤120 字）、正文 HTML，只用 p、h2、h3、strong、em、blockquote、ul、ol、li、img、a 标签。",
        "publish_url": "https://mp.weixin.qq.com/",
    },
    "bilibili": {
        "label": "B站",
        "title_max": 80,
        "body_max": 3000,
        "summary_max": 250,
        "cover_text_max": 15,
        "tags_min": 3,
        "tags_max": 10,
        "format": "script",
        "guide": (
            "B站视频稿。title：有梗、有信息量，不做标题党（80 字内）；hook：开头 15 秒点明看点的一句话（30 字内）；"
            "body：口播稿，分段，中段设 2–3 个弹幕互动点，用单独一行【弹幕】+ 观众可能刷的弹幕写出来，结尾自然引导三连；"
            "summary：视频简介（250 字内）；cover_text：封面大字（15 字内）；tags：3–10 个标签。语气像 UP 主跟观众聊天，可以玩梗但别硬凹。"
        ),
        "publish_url": "https://member.bilibili.com/platform/upload/video/frame",
    },
    "douyin": {
        "label": "抖音",
        "title_max": 55,
        "body_max": 600,
        "hook_max": 20,
        "cover_text_max": 10,
        "tags_min": 3,
        "tags_max": 5,
        "format": "script",
        "guide": (
            "抖音竖屏口播。hook：前三秒钩子（20 字内），直接抛反差、悬念或结论，不要寒暄；"
            "body：口播稿，一行一个镜头，行首用【画面：…】写画面提示，句子短、节奏快，全片控制在 60 秒左右；"
            "title：发布文案（55 字内）；cover_text：封面大字（10 字内）；tags：3–5 个话题。"
        ),
        "publish_url": "https://creator.douyin.com/creator-micro/content/upload",
    },
}

# 短视频平台（口播稿形态），其余是图文 / 长文
SCRIPT_KINDS = ("bilibili", "douyin")

WECHAT_TAGS = {"p", "h2", "h3", "strong", "em", "blockquote", "ul", "ol", "li", "img", "a"}
WECHAT_ATTRS = {"a": {"href", "title"}, "img": {"src", "alt"}}


def text_len(text: str | None) -> int:
    """按字符计数（汉字、字母、标点都算 1），与平台计数口径一致。"""
    return len((text or "").strip())


def check(kind: str, content: dict) -> list[dict]:
    """返回超限提示：[{field, message, limit, actual}]。"""
    rules = PLATFORM_RULES.get(kind)
    if not rules:
        return []
    issues: list[dict] = []

    def over(field: str, limit_key: str, actual: int, label: str) -> None:
        limit = rules.get(limit_key)
        if limit is not None and actual > limit:
            issues.append(
                {"field": field, "limit": limit, "actual": actual, "message": f"{label}超过 {limit} 字（{actual}）"}
            )

    over("title", "title_max", text_len(content.get("title")), "标题")
    body = content.get("body") or ""
    if rules["format"] == "html":
        import re

        body = re.sub(r"<[^>]+>", "", body)
    over("body", "body_max", text_len(body), "正文")
    over("cover_text", "cover_text_max", text_len(content.get("cover_text")), "封面文案")
    over("summary", "summary_max", text_len(content.get("summary")), "简介" if kind == "bilibili" else "摘要")
    over("hook", "hook_max", text_len(content.get("hook")), "开头钩子")
    tags = content.get("tags") or []
    if "tags_min" in rules and not rules["tags_min"] <= len(tags) <= rules["tags_max"]:
        issues.append(
            {
                "field": "tags",
                "limit": rules["tags_max"],
                "actual": len(tags),
                "message": f"话题需要 {rules['tags_min']}–{rules['tags_max']} 个（现在 {len(tags)}）",
            }
        )
    return issues
