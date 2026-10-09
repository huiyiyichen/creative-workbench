"""Read public creator pages using the site's own browser responses."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime

from playwright.async_api import async_playwright


def _douyin_posts(data: dict) -> list[dict]:
    entries = []
    for post in data.get("aweme_list", []):
        description = post.get("desc", "")
        cover = post.get("video", {}).get("cover", {}).get("url_list", [])
        entries.append({
            "title": description.split("\n")[0],
            "summary": description,
            "raw_content": description,
            "url": f"https://www.douyin.com/video/{post['aweme_id']}",
            "author": post.get("author", {}).get("nickname", ""),
            "published_at": datetime.fromtimestamp(post["create_time"], UTC) if post.get("create_time") else None,
            "cover_url": cover[-1] if cover else None,
            "tags": [tag["hashtag_name"] for tag in post.get("text_extra", []) if tag.get("hashtag_name")],
            "_creator_meta": {key: value for key, value in {
                "likes": post.get("statistics", {}).get("digg_count"),
                "comments": post.get("statistics", {}).get("comment_count"),
                "shares": post.get("statistics", {}).get("share_count"),
                "favorites": post.get("statistics", {}).get("collect_count"),
            }.items() if value is not None},
        })
    return entries


def _bilibili_posts(data: dict) -> list[dict]:
    entries = []
    for post in data.get("data", {}).get("list", {}).get("vlist", []):
        entries.append({
            "title": post["title"], "summary": post.get("description", ""),
            "raw_content": post.get("description", ""),
            "url": f"https://www.bilibili.com/video/{post['bvid']}",
            "author": post.get("author", ""),
            "published_at": datetime.fromtimestamp(post["created"], UTC) if post.get("created") else None,
            "cover_url": post.get("pic"),
        })
    return entries


async def fetch_creator_posts(route: str) -> list[dict]:
    douyin = re.fullmatch(r"douyin/user/(MS4w[\w-]+)", route)
    bilibili = re.fullmatch(r"bilibili/user/video(?:-all)?/(\d+)", route)
    if douyin:
        url = f"https://www.douyin.com/user/{douyin[1]}"
        response_path, parse = "/aweme/post", _douyin_posts
    elif bilibili:
        url = f"https://space.bilibili.com/{bilibili[1]}/upload/video"
        response_path, parse = "/arc/search", _bilibili_posts
    else:
        raise ValueError("博主地址格式错误")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
            posts: list[dict] = []

            async def read_response(response):
                if response_path in response.url and response.status == 200:
                    try:
                        posts.extend(parse(await response.json()))
                    except (ValueError, KeyError):
                        pass

            pending: set[asyncio.Task] = set()

            def capture(response):
                task = asyncio.create_task(read_response(response))
                pending.add(task)
                task.add_done_callback(pending.discard)

            page.on("response", capture)
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            for _ in range(40):
                if posts:
                    return posts
                await asyncio.sleep(1)
            raise RuntimeError("博主作品加载失败，请在浏览器打开主页检查平台验证状态")
        finally:
            await browser.close()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
