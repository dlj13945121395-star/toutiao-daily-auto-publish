# -*- coding: utf-8 -*-
"""只读探针：确认头条创作者后台的「评论管理」入口是否存在、登录态是否有效、评论区能否打开。
不发布、不回复、不改任何线上内容。
"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
auth = json.load(open(os.path.join(ROOT, cfg["auth_file"]), encoding="utf-8"))
if isinstance(auth, dict):
    auth = auth.get("cookies", [])

SHOT = os.path.join(ROOT, "probe_comment.png")

CANDIDATES = [
    "https://mp.toutiao.com/profile_v4/manage/comment",
    "https://mp.toutiao.com/profile_v4/interaction/comment",
    "https://mp.toutiao.com/profile_v4/comment",
]

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 1000})
    ctx.add_cookies(auth)
    page = ctx.new_page()

    print("== 1) 打开创作者后台首页，列出所有导航入口 ==")
    page.goto("https://mp.toutiao.com/profile_v4/", wait_until="domcontentloaded", timeout=45000)
    time.sleep(6)
    print("URL:", page.url)
    print("TITLE:", page.title())
    links = page.evaluate(
        """() => Array.from(document.querySelectorAll('a')).map(a => (a.innerText||'').trim() + ' | ' + a.getAttribute('href'))"""
    )
    hits = [l for l in links if any(k in l for k in ("评论", "互动", "留言", "私信"))]
    print("疑似评论相关入口:", hits if hits else "无")
    print("全部非空入口(前40):")
    for l in [x for x in links if x.split(" | ")[0]][:40]:
        print("   ", l)

    print("\n== 2) 逐个尝试评论管理候选地址 ==")
    for u in CANDIDATES:
        try:
            page.goto(u, wait_until="domcontentloaded", timeout=45000)
            time.sleep(6)
            txt = page.evaluate("() => document.body ? document.body.innerText : ''")
            has_box = page.evaluate(
                """() => {
                    const c = document.querySelectorAll("textarea, [contenteditable='true']").length;
                    return c;
                }"""
            )
            print(f"\n--- {u}")
            print("  落地 URL:", page.url)
            print("  标题:", page.title())
            print("  可输入框数量:", has_box)
            print("  正文前 300 字:", " ".join(txt.split())[:300])
        except Exception as e:  # noqa: BLE001
            print(f"\n--- {u}\n  异常: {str(e)[:120]}")

    page.screenshot(path=SHOT, full_page=False)
    print("\n截图:", SHOT)
    b.close()
