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
}

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
    over("summary", "summary_max", text_len(content.get("summary")), "摘要")
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
