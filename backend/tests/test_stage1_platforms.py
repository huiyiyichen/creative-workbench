"""阶段 1：平台适配器、追踪词、统一添加（改造方案 3.1 / 3.2）。"""

from __future__ import annotations

import httpx
import pytest

from app.services.platforms import NotSupported, describe_platforms, get_adapter
from app.services.platforms.base import parse_duration
from app.services.platforms.bilibili import BilibiliAdapter, mixin_key, sign_params
from app.services.platforms.github import parse_trending
from app.services.scrapers.platform import KeywordScraper, PlatformScraper, parse_platform_url
from app.services.scrapers.recognizer import recognize_input


def test_wbi_signature_matches_reference_vector():
    key = mixin_key("7cd084941338484aae1ad9425b84077c", "4932caff0ff746eab6f01bf08b70ac45")
    assert key == "ea1db124af3c7062474693fa704f4ff8"
    signed = sign_params({"foo": "114", "bar": "514", "zab": 1919810}, key, wts=1702204169)
    assert signed["w_rid"] == "8f6f2b5b3d485fe1886cec6a0be8c5d4"


def test_parse_duration_formats():
    assert parse_duration("12:34") == 754
    assert parse_duration("1:02:03") == 3723
    assert parse_duration("PT1H2M3S") == 3723
    assert parse_duration(61) == 61
    assert parse_duration("abc") is None


def test_bilibili_entry_keeps_real_metrics_and_cover():
    adapter = BilibiliAdapter(httpx.AsyncClient())
    entry = adapter.to_entry(
        {
            "bvid": "BV1ab",
            "aid": 9,
            "title": '<em class="keyword">Opus</em> 5.5 实测',
            "pic": "//i0.hdslb.com/x.jpg",
            "pubdate": 1760000000,
            "duration": "3:05",
            "owner": {"mid": 42, "name": "UP"},
            "stat": {"view": 1200, "like": 30, "coin": 0},
            "dimension": {"width": 1080, "height": 1920, "rotate": 0},
        }
    )
    assert entry["title"] == "Opus 5.5 实测"
    assert entry["cover_url"] == "https://i0.hdslb.com/x.jpg"
    assert entry["metrics"] == {"views": 1200, "likes": 30, "coins": 0}
    assert entry["media"]["duration"] == 185 and entry["media"]["orientation"] == "portrait"
    assert entry["author_url"] == "https://space.bilibili.com/42"


TRENDING_HTML = """
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a href="/anthropics/claude-code" class="Link">anthropics / claude-code</a></h2>
  <p class="col-9 color-fg-muted my-1 pr-4">Agentic coding &amp; more</p>
  <span itemprop="programmingLanguage">TypeScript</span>
  <a href="/anthropics/claude-code/stargazers" class="Link"><svg></svg> 42,184</a>
  <span>1,203 stars today</span>
</article>
"""


def test_github_trending_parse():
    rows = parse_trending(TRENDING_HTML)
    assert rows[0]["platform_item_id"] == "anthropics/claude-code"
    assert rows[0]["metrics"] == {"rank": 1, "stars": 42184}
    assert rows[0]["media"]["stars_gained"] == 1203
    assert rows[0]["summary"] == "Agentic coding & more"
    assert rows[0]["cover_url"].startswith("https://opengraph.githubassets.com/")


@pytest.mark.asyncio
async def test_youtube_search_needs_key():
    async with httpx.AsyncClient() as client:
        adapter = get_adapter("youtube", client, api_key=None)
        with pytest.raises(NotSupported):
            await adapter.search("opus")


def test_describe_platforms_marks_capabilities():
    by = {p["platform"]: p for p in describe_platforms()}
    assert by["bilibili"]["capabilities"]["fetch_subtitles"] is True
    assert by["hn"]["capabilities"]["list_posts"] is False
    assert by["youtube"]["needs_key"] is True


@pytest.mark.parametrize(
    ("text", "kind", "url"),
    [
        ("Opus 5.5 视频", "keyword", "keyword://Opus%205.5%20%E8%A7%86%E9%A2%91"),
        ("https://space.bilibili.com/946974", "subscription", "platform://bilibili/user/946974"),
        ("https://www.bilibili.com/v/popular/all", "list", "platform://bilibili/ranking/popular"),
        ("https://github.com/anthropics/claude-code", "subscription", "platform://github/repo/anthropics/claude-code"),
        ("github.com/trending/python?since=weekly", "list", "platform://github/ranking/python:weekly"),
        (
            "https://www.youtube.com/channel/UCXZCJLdBC09xxGZ6gcdrc6A",
            "subscription",
            "platform://youtube/user/UCXZCJLdBC09xxGZ6gcdrc6A",
        ),
        ("https://www.reddit.com/r/LocalLLaMA/", "subscription", "platform://reddit/user/LocalLLaMA"),
        ("https://news.ycombinator.com/", "list", "platform://hn/ranking/front"),
        ("https://example.com/feed.xml", "subscription", "https://example.com/feed.xml"),
    ],
)
def test_recognize_input(text, kind, url):
    result = recognize_input(text)
    assert (result["kind"], result["url"]) == (kind, url)


def test_parse_platform_url():
    assert parse_platform_url("platform://github/repo/a/b") == ("github", "repo", "a/b")


def _transport(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, response in routes.items():
            if str(request.url).startswith(prefix):
                return response(request) if callable(response) else response
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_keyword_scraper_merges_platforms_and_tolerates_failures():
    routes = {
        "https://hn.algolia.com/api/v1/search_by_date": httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "objectID": "1",
                        "title": "Opus 5.5 is out",
                        "points": 120,
                        "num_comments": 40,
                        "created_at_i": 1760000000,
                    }
                ]
            },
        ),
        "https://api.github.com/search/repositories": httpx.Response(500),
    }
    scraper = KeywordScraper("keyword://Opus", {"query": "Opus 5.5", "platforms": ["hn", "github", "youtube", "nope"]})
    async with httpx.AsyncClient(transport=_transport(routes)) as client:
        entries = await scraper.fetch(client)
    assert [e["platform"] for e in entries] == ["hn"]
    assert entries[0]["_keyword"] == "Opus 5.5" and entries[0]["metrics"] == {"score": 120, "comments": 40}
    assert set(scraper.platform_errors) == {"github", "youtube"}  # YouTube 缺 Key 只记录，不算失败


@pytest.mark.asyncio
async def test_keyword_scraper_fails_when_every_platform_fails():
    scraper = KeywordScraper("keyword://x", {"query": "x", "platforms": ["hn"]})
    async with httpx.AsyncClient(transport=_transport({})) as client:
        with pytest.raises(RuntimeError):
            await scraper.fetch(client)


@pytest.mark.asyncio
async def test_platform_scraper_ranking_adds_rank():
    routes = {
        "https://hn.algolia.com/api/v1/search": httpx.Response(
            200, json={"hits": [{"objectID": "7", "title": "A"}, {"objectID": "8", "title": "B", "points": 3}]}
        )
    }
    async with httpx.AsyncClient(transport=_transport(routes)) as client:
        entries = await PlatformScraper("platform://hn/ranking/front").fetch(client)
    assert [e["metrics"].get("rank") for e in entries] == [1, 2]


@pytest.mark.asyncio
async def test_create_keyword_source_filters_platforms(db):
    from app.services.source_registry import create_source

    source = await create_source(
        db,
        {
            "kind": "keyword",
            "source_type": "Keyword",
            "url": "keyword://opus",
            "query": "Opus",
            "platforms": ["hn", "douyin"],
        },
    )
    assert source.platforms == ["hn"] and source.fetch_interval_minutes == 120 and source.platform == "multi"
