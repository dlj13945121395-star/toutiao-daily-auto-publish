# -*- coding: utf-8 -*-
"""只读探针 2：打开「评论管理」真实页，列出评论、检查是否存在回复入口。不发送任何回复。"""
import json
import os
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
auth = json.load(open(os.path.join(ROOT, cfg["auth_file"]), encoding="utf-8"))
if isinstance(auth, dict):
    auth = auth.get("cookies", [])

SHOT = os.path.join(ROOT, "probe_comment.png")
URL = "https://mp.toutiao.com/profile_v4/manage/comment/all?enter_from=left_menu"

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 1100})
    ctx.add_cookies(auth)
    page = ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    time.sleep(9)

    print("URL:", page.url)
    txt = page.evaluate("() => document.body ? document.body.innerText : ''")
    flat = " ".join(txt.split())
    print("正文:", flat[:1200])

    print("\n回复类元素统计:")
    for kw in ["回复", "点赞", "删除", "全部", "待回复"]:
        n = page.evaluate(
            """(k) => Array.from(document.querySelectorAll('*')).filter(
                   e => e.children.length === 0 && (e.innerText||'').trim() === k).length""",
            kw,
        )
        print(f"   '{kw}' 精确文本节点: {n}")

    print("\n可输入元素:")
    print("  textarea/contenteditable:", page.evaluate(
        "() => document.querySelectorAll(\"textarea,[contenteditable='true']\").length"))
    print("\n页面上出现的按钮 class（前 30 个）:")
    print(page.evaluate(
        """() => Array.from(document.querySelectorAll('button')).slice(0,30)
                 .map(b => (b.innerText||'').trim().slice(0,12) + ' :: ' + (b.className||'').slice(0,60))"""))

    page.screenshot(path=SHOT, full_page=True)
    print("\n截图:", SHOT)
    b.close()
