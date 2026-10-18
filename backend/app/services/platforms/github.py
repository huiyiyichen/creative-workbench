"""GitHub 适配器：仓库发布（订阅）、仓库搜索（追踪词）、Trending（榜单）、热门 Issue（评论）。"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from .base import (
    COMMENTS,
    DETAIL,
    LIST_POSTS,
    RANKING,
    SEARCH,
    Comment,
    PlatformAdapter,
    PlatformError,
    from_iso,
    strip_tags,
)

API = "https://api.github.com"


def social_preview(full_name: str) -> str:
    return f"https://opengraph.githubassets.com/1/{full_name}"


class GithubAdapter(PlatformAdapter):
    platform = "github"
    label = "GitHub"
    capabilities: ClassVar[frozenset[str]] = frozenset({LIST_POSTS, SEARCH, RANKING, DETAIL, COMMENTS})

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def repo_entry(self, r: dict[str, Any]) -> dict[str, Any]:
        full = r.get("full_name") or ""
        owner = r.get("owner") or {}
        metrics = {
            "stars": r.get("stargazers_count"),
            "forks": r.get("forks_count"),
        }
        return {
            "title": full + (f"：{r['description']}" if r.get("description") else ""),
            "url": r.get("html_url") or f"https://github.com/{full}",
            "summary": r.get("description"),
            "author": owner.get("login"),
            "author_id": str(owner.get("id")) if owner.get("id") else None,
            "author_url": owner.get("html_url"),
            "published_at": from_iso(r.get("pushed_at") or r.get("created_at")),
            "cover_url": social_preview(full) if full else None,
            "platform": self.platform,
            "media_type": "repo",
            "platform_item_id": full,
            "media": {"language": r.get("language"), "topics": (r.get("topics") or [])[:8]},
            "metrics": {k: v for k, v in metrics.items() if isinstance(v, int)},
            "tags": (r.get("topics") or [])[:5],
        }

    supports_paging: ClassVar[bool] = True

    async def list_posts(self, target: str, *, limit: int = 20, page: int = 1) -> list[dict[str, Any]]:
        """订阅仓库发布：target = ``owner/repo``。"""
        full = target.strip().removeprefix("https://github.com/").strip("/")
        if full.count("/") != 1:
            raise PlatformError("GitHub 订阅需要 owner/repo 形式的仓库")
        releases = await self._get_json(
            f"{API}/repos/{full}/releases", params={"per_page": min(limit, 30), "page": page}, headers=self._headers()
        )
        out = []
        for rel in releases[:limit]:
            out.append(
                {
                    "title": f"{full} 发布 {rel.get('name') or rel.get('tag_name')}",
                    "url": rel.get("html_url"),
                    "summary": (rel.get("body") or "")[:1000] or None,
                    "raw_content": rel.get("body"),
                    "author": (rel.get("author") or {}).get("login"),
                    "published_at": from_iso(rel.get("published_at") or rel.get("created_at")),
                    "cover_url": social_preview(full),
                    "platform": self.platform,
                    "media_type": "repo",
                    "platform_item_id": f"{full}@{rel.get('tag_name')}",
                    "media": {"repo": full, "tag": rel.get("tag_name"), "prerelease": bool(rel.get("prerelease"))},
                    "metrics": {},
                }
            )
        return out

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._get_json(
            f"{API}/search/repositories",
            params={"q": query, "sort": "updated", "order": "desc", "per_page": min(limit, 30)},
            headers=self._headers(),
        )
        return [self.repo_entry(r) for r in (data.get("items") or [])[:limit]]

    async def fetch_detail(self, item_id: str) -> dict[str, Any]:
        return self.repo_entry(await self._get_json(f"{API}/repos/{item_id}", headers=self._headers()))

    async def list_ranking(self, name: str = "", *, limit: int = 25) -> list[dict[str, Any]]:
        """GitHub Trending：name = ``daily`` / ``weekly`` / ``monthly``，可写 ``python:daily`` 限定语言。"""
        lang, _, since = name.rpartition(":") if ":" in name else ("", "", name or "daily")
        url = f"https://github.com/trending/{lang}" if lang else "https://github.com/trending"
        resp = await self.client.get(url, params={"since": since or "daily"}, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return parse_trending(resp.text)[:limit]

    async def fetch_comments(self, item_id: str, *, limit: int = 20) -> list[Comment]:
        issues = await self._get_json(
            f"{API}/repos/{item_id}/issues",
            params={"sort": "comments", "direction": "desc", "state": "all", "per_page": min(limit, 30)},
            headers=self._headers(),
        )
        return [
            Comment(
                text=f"{i.get('title')}\n{(i.get('body') or '')[:400]}".strip(),
                author=(i.get("user") or {}).get("login"),
                replies=i.get("comments"),
                likes=(i.get("reactions") or {}).get("total_count"),
                published_at=from_iso(i.get("created_at")),
            )
            for i in issues[:limit]
        ]


_ARTICLE_RE = re.compile(r"<article class=\"Box-row\">(.*?)</article>", re.S)
_REPO_RE = re.compile(r"<h2[^>]*>\s*<a[^>]*href=\"/([^\"]+)\"", re.S)
_DESC_RE = re.compile(r"<p class=\"col-9[^\"]*\">(.*?)</p>", re.S)
_LANG_RE = re.compile(r"itemprop=\"programmingLanguage\">([^<]+)<")
_STARS_RE = re.compile(r"href=\"/[^\"]+/stargazers\"[^>]*>.*?</svg>\s*([\d,]+)", re.S)
_TODAY_RE = re.compile(r"([\d,]+)\s+stars? (?:today|this week|this month)")


def _int(text: str | None) -> int | None:
    return int(text.replace(",", "")) if text else None


def parse_trending(html_text: str) -> list[dict[str, Any]]:
    out = []
    for rank, block in enumerate(_ARTICLE_RE.findall(html_text), start=1):
        repo = _REPO_RE.search(block)
        if not repo:
            continue
        full = repo.group(1).strip()
        desc = _DESC_RE.search(block)
        lang = _LANG_RE.search(block)
        stars = _STARS_RE.search(block)
        today = _TODAY_RE.search(block)
        summary = strip_tags(desc.group(1)) if desc else None
        metrics = {"rank": rank}
        if stars:
            metrics["stars"] = _int(stars.group(1))
        out.append(
            {
                "title": full + (f"：{summary}" if summary else ""),
                "url": f"https://github.com/{full}",
                "summary": summary,
                "author": full.split("/")[0],
                "cover_url": social_preview(full),
                "platform": "github",
                "media_type": "repo",
                "platform_item_id": full,
                "media": {
                    "language": lang.group(1).strip() if lang else None,
                    "stars_gained": _int(today.group(1)) if today else None,
                },
                "metrics": metrics,
            }
        )
    return out
