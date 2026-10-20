"""阶段 4 第 ⑥ 步：抖音、小红书（本机浏览器读页面接口响应）与评论（被项目用作来源时采集）。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.models.content import ContentItem, ContentStatus
from app.models.content_observation import ContentComment
from app.schemas.projects import ProjectCreate, SourceAdd
from app.services import comments, project_service as ps
from app.services.platforms import (
    PlatformError,
    browser,
    describe_platforms,
    douyin as dy,
    get_adapter,
    xiaohongshu as xhs,
)
from app.services.scrapers.recognizer import recognize_input

AWEME = {
    "aweme_id": "7412345678901234567",
    "desc": "Claude Code 实测\n#AI编程 #效率",
    "create_time": 1760000000,
    "author": {"nickname": "程序员小王", "sec_uid": "MS4wLjABAAAAabc"},
    "video": {
        "cover": {"url_list": ["http://p3.douyinpic.com/a.jpeg", "https://p9.douyinpic.com/b.jpeg"]},
        "width": 1080,
        "height": 1920,
        "duration": 61500,
    },
    "statistics": {"digg_count": 12000, "comment_count": 345, "share_count": 67, "collect_count": 890, "play_count": 0},
    "text_extra": [{"hashtag_name": "AI编程"}, {"hashtag_name": "效率"}],
}
DY_COMMENTS = {
    "comments": [
        {
            "cid": "c1",
            "text": "第二热",
            "digg_count": 50,
            "user": {"nickname": "甲", "avatar_thumb": {"url_list": ["x"]}},
            "create_time": 1760000100,
            "reply_comment_total": 3,
        },
        {"cid": "c2", "text": "最热的评论", "digg_count": 900, "user": {"nickname": "乙"}, "create_time": 1760000200},
        {"cid": "c3", "text": "  ", "digg_count": 1},
    ]
}
XHS_NOTE = {
    "id": "6650a1b2c3d4e5f600000001",
    "xsec_token": "ABtok==",
    "model_type": "note",
    "note_card": {
        "type": "normal",
        "display_title": "我用 AI 一周写完论文",
        "user": {"user_id": "5f0000000000000000000001", "nickname": "小红薯"},
        "interact_info": {"liked_count": "1.2万", "collected_count": "3456", "comment_count": "89"},
        "cover": {"url_default": "http://sns-webpic-qc.xhscdn.com/c.jpg", "width": 1080, "height": 1440},
        "image_list": [{"url_default": "x"}, {"url_default": "y"}],
    },
}
XHS_COMMENTS = {
    "data": {
        "comments": [
            {
                "id": "x1",
                "content": "求工具清单",
                "like_count": "1.1万",
                "user_info": {"nickname": "丙"},
                "create_time": 1760000000000,
                "sub_comment_count": "12",
            },
            {"id": "x2", "content": "收藏了", "like_count": "35", "user_info": {"nickname": "丁"}},
        ]
    }
}


class FakeBrowser:
    def __init__(self, responses: dict[str, dict], state=None, error: str | None = None):
        self.responses = responses
        self.state = state
        self.error = error
        self.calls: list[tuple[str, str]] = []

    async def capture(self, platform, url, matchers, **kw):
        self.calls.append((platform, url))
        if self.error:
            raise PlatformError(self.error)
        out = browser.Captured(final_url=url, page_state=self.state)
        for name, part in matchers.items():
            for key, payload in self.responses.items():
                if part in key:
                    out.responses.setdefault(name, []).append(payload)
        return out


@pytest.fixture
def fake_browser(monkeypatch):
    def install(responses, **kw):
        fb = FakeBrowser(responses, **kw)
        monkeypatch.setattr(browser, "BROWSER", fb)
        return fb

    return install


def test_douyin_entry_and_comments_parsing():
    e = dy.to_entry(AWEME)
    assert e["title"] == "Claude Code 实测" and e["platform_item_id"] == "7412345678901234567"
    assert e["cover_url"] == "https://p9.douyinpic.com/b.jpeg"
    assert e["media"] == {"duration": 61, "orientation": "portrait"}
    assert e["metrics"] == {"likes": 12000, "comments": 345, "favorites": 890, "shares": 67}
    assert e["author_url"] == "https://www.douyin.com/user/MS4wLjABAAAAabc" and e["tags"] == ["AI编程", "效率"]
    # 综合搜索的卡片里也能取出视频
    assert [
        x["platform_item_id"] for x in dy.posts_from({"data": [{"type": 1, "aweme_info": AWEME}, {"type": 9}]})
    ] == ["7412345678901234567"]
    cs = dy.comments_from(DY_COMMENTS, 20)
    assert [c.text for c in cs] == ["最热的评论", "第二热"] and cs[1].replies == 3 and cs[0].id == "c2"


def test_xiaohongshu_entry_counts_and_state_detail():
    e = xhs.to_entry(XHS_NOTE)
    assert e["platform_item_id"] == "6650a1b2c3d4e5f600000001" and e["media"]["xsec_token"] == "ABtok=="
    assert "xsec_token=ABtok%3D%3D" in e["url"] and e["media_type"] == "image" and e["media"]["images"] == 2
    assert e["metrics"] == {"likes": 12000, "favorites": 3456, "comments": 89}
    assert e["cover_url"].startswith("https://")
    assert xhs.split_ref(e["url"]) == ("6650a1b2c3d4e5f600000001", "ABtok==")
    assert xhs.split_ref("abc|tok") == ("abc", "tok")
    state = {
        "note": {
            "noteDetailMap": {
                "n1": {
                    "note": {
                        "title": "标题",
                        "desc": "正文",
                        "type": "video",
                        "time": 1760000000000,
                        "interactInfo": {"likedCount": "10"},
                        "imageList": [{"urlDefault": "https://img/1.jpg"}],
                        "user": {"userId": "u1", "nickname": "作者"},
                    }
                }
            }
        }
    }
    d = xhs.detail_from_state(state, "n1", "tok")
    assert d["title"] == "标题" and d["media_type"] == "video" and d["metrics"] == {"likes": 10}
    assert d["published_at"].year == 2025
    cs = xhs.comments_from(XHS_COMMENTS, 20)
    assert cs[0].likes == 11000 and cs[0].replies == 12 and cs[1].author == "丁"


@pytest.mark.asyncio
async def test_adapters_via_browser_capture(fake_browser):
    fb = fake_browser(
        {
            "https://www.douyin.com/aweme/v1/web/aweme/post/?x": {"aweme_list": [AWEME]},
            "https://www.douyin.com/aweme/v1/web/search/item/?q": {"data": [{"aweme_info": AWEME}]},
            "https://www.douyin.com/aweme/v1/web/comment/list/?a": DY_COMMENTS,
        }
    )
    async with httpx.AsyncClient() as client:
        a = get_adapter("douyin", client)
        posts = await a.list_posts("MS4wLjABAAAAabc")
        assert posts[0]["platform_item_id"] == AWEME["aweme_id"]
        assert fb.calls[-1] == ("douyin", "https://www.douyin.com/user/MS4wLjABAAAAabc")
        assert (await a.search("Claude Code"))[0]["title"] == "Claude Code 实测"
        assert "search/Claude%20Code" in fb.calls[-1][1]
        assert [c.text for c in await a.fetch_comments(AWEME["aweme_id"])][0] == "最热的评论"
        with pytest.raises(PlatformError):
            await a.list_posts("12345")  # 不是 sec_uid

        fake_browser({"https://edith.xiaohongshu.com/api/sns/web/v1/search/notes": {"data": {"items": [XHS_NOTE]}}})
        x = get_adapter("xiaohongshu", client)
        found = await x.search("AI 论文")
        assert found[0]["author"] == "小红薯"


@pytest.mark.asyncio
async def test_wall_detection_and_status(tmp_path, monkeypatch):
    with pytest.raises(PlatformError, match="登录失效"):
        browser.check_wall("xiaohongshu", "https://www.xiaohongshu.com/login?redirect=1", "")
    with pytest.raises(PlatformError, match="验证码"):
        browser.check_wall("douyin", "https://www.douyin.com/", "请完成安全验证")
    browser.check_wall("douyin", "https://www.douyin.com/video/1", "正常页面")
    from app.services.source_sync_service import classify_sync_error

    assert classify_sync_error("douyin 登录失效，请在「信源 · 浏览器登录」里重新登录")[0].value == "login"
    assert classify_sync_error("xiaohongshu 出现验证码")[0].value == "captcha"

    monkeypatch.setattr(browser, "PROFILE_ROOT", tmp_path)
    pool = browser.BrowserPool()
    calls = []

    async def fake_open(platform, url, *a):
        calls.append(url)
        if "bad" in url:
            raise PlatformError("douyin 登录失效")
        return browser.Captured(responses={"x": [{}]})

    monkeypatch.setattr(pool, "_open", fake_open)
    monkeypatch.setattr(browser, "MIN_INTERVAL", {"douyin": 0.0})
    await pool.capture("douyin", "https://ok", {"x": "/x"})
    assert pool.status("douyin")["last_ok_at"]
    with pytest.raises(PlatformError):
        await pool.capture("douyin", "https://bad", {"x": "/x"})
    st = pool.status("douyin")
    assert "登录失效" in st["last_error"] and st["profile"] is True
    # 全局并发 1：两次并发调用依次执行
    await asyncio.gather(
        pool.capture("douyin", "https://ok/1", {"x": "/x"}), pool.capture("douyin", "https://ok/2", {"x": "/x"})
    )
    assert calls[-2:] == ["https://ok/1", "https://ok/2"]


def test_describe_and_recognize():
    by = {p["platform"]: p for p in describe_platforms()}
    assert by["douyin"]["browser"] and by["xiaohongshu"]["capabilities"]["fetch_comments"]
    assert not by["bilibili"]["browser"]
    r = recognize_input("https://www.douyin.com/user/MS4wLjABAAAAabc?from=tab")
    assert r["url"] == "platform://douyin/user/MS4wLjABAAAAabc"
    r = recognize_input("https://www.xiaohongshu.com/user/profile/5f0000000000000000000001")
    assert r["url"] == "platform://xiaohongshu/user/5f0000000000000000000001"
    r = recognize_input("https://www.xiaohongshu.com/search_result?keyword=AI%E8%AE%BA%E6%96%87")
    assert r["kind"] == "keyword" and r["platforms"] == ["xiaohongshu"] and r["query"] == "AI论文"


@pytest.mark.asyncio
async def test_project_source_triggers_comment_collection(test_session_factory, monkeypatch, fake_browser):
    fb = fake_browser({"https://edith.xiaohongshu.com/api/sns/web/v2/comment/page?x": XHS_COMMENTS})
    monkeypatch.setattr(comments, "SESSION_FACTORY", test_session_factory)
    async with test_session_factory() as db:
        c = ContentItem(
            title="我用 AI 一周写完论文",
            url="https://www.xiaohongshu.com/explore/6650a1b2c3d4e5f600000001",
            platform="xiaohongshu",
            platform_item_id="6650a1b2c3d4e5f600000001",
            media={"xsec_token": "ABtok=="},
            status=ContentStatus.PENDING,
            crawled_at=datetime.now(UTC),
        )
        db.add(c)
        await db.commit()
        p = await ps.create_project(db, 1, ProjectCreate(theme="t"))
        await ps.add_source(db, p["id"], SourceAdd(content_id=c.id))
        await asyncio.gather(*list(comments._bg))
        assert fb.calls and "xsec_token=ABtok%3D%3D" in fb.calls[0][1]
        rows = (await db.execute(select(ContentComment).where(ContentComment.content_id == c.id))).scalars().all()
        assert {r.text for r in rows} == {"求工具清单", "收藏了"} and all(r.platform == "xiaohongshu" for r in rows)
        item = await db.get(ContentItem, c.id, populate_existing=True)
        assert item.comment_state == comments.STATE_COLLECTED
        # 项目来源算「保留」：30 天清理不删它的评论
        assert c.id in await comments._kept_content_ids(db)


@pytest.mark.asyncio
async def test_comment_login_wall_marks_failed(test_session_factory, fake_browser):
    fake_browser({}, error="douyin 登录失效，请在「信源 · 浏览器登录」里重新登录")
    async with test_session_factory() as db:
        c = ContentItem(
            title="抖音视频",
            url="https://www.douyin.com/video/7412345678901234567",
            platform="douyin",
            platform_item_id="7412345678901234567",
            status=ContentStatus.PENDING,
            crawled_at=datetime.now(UTC),
        )
        db.add(c)
        await db.commit()
        out = await comments.collect(db, c.id)
        assert "登录失效" in out["error"]
        assert (await db.get(ContentItem, c.id)).comment_state == comments.STATE_FAILED


@pytest.mark.asyncio
async def test_note_used_for_new_project(db):
    from app.models.library import Note

    n = Note(body="# 智能体成本\n每天 601 美元值不值", source="app")
    db.add(n)
    await db.commit()
    p = await ps.create_project(db, 1, ProjectCreate(sources=[f"note:{n.id}"]))
    assert p["brief"]["theme"] == "智能体成本" and "601" in p["brief"]["intent"]
    assert p["sources"] == [] and p["title"] == "智能体成本"


def test_browser_proxy_and_channel(monkeypatch):
    for k in ("CW_BROWSER_PROXY", "HTTPS_PROXY", "https_proxy", "ALL_PROXY"):
        monkeypatch.delenv(k, raising=False)
    assert browser._proxy() is None
    monkeypatch.setenv("CW_BROWSER_PROXY", "http://u:p@127.0.0.1:7890")
    assert browser._proxy() == {"server": "http://127.0.0.1:7890", "username": "u", "password": "p"}
    monkeypatch.setattr(browser, "BROWSER_CHANNEL", "chromium")
    assert "channel" not in browser._channel_kwargs() and browser._channel_kwargs()["proxy"]["server"]
    monkeypatch.setattr(browser, "BROWSER_CHANNEL", "msedge")
    assert browser._channel_kwargs()["channel"] == "msedge"
