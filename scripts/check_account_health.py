#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_account_health.py — 检查头条号健康度：有无违规/处罚/扣分/低质警告。
只读，不做任何修改。"""
import json, os, re, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
cfg = json.load(open(os.path.join(SKILL_ROOT, "config.json"), "r", encoding="utf-8"))
auth = json.load(open(os.path.join(SKILL_ROOT, cfg["auth_file"]), "r", encoding="utf-8"))

KEYWORDS = ["违规", "处罚", "封禁", "禁言", "扣分", "信用分", "低质", "警告",
            "限流", "申诉", "扣分", "权益", "整改", "异常"]

PAGES = [
    ("后台首页", "https://mp.toutiao.com/profile_v4/index"),
    ("作品管理", "https://mp.toutiao.com/profile_v4/graphic/post"),
]


def log(m):
    print(f"[health] {m}", flush=True)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context()
    ctx.add_cookies(auth)
    page = ctx.new_page()
    page.set_default_timeout(25000)

    for name, url in PAGES:
        log("=" * 50)
        log(f"{name}  {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(9)
            for _ in range(3):
                page.mouse.wheel(0, 1200)
                time.sleep(1)
            page.mouse.wheel(0, -5000)
            time.sleep(1)
            txt = page.inner_text("body")
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            hits = [(i, l) for i, l in enumerate(lines) if any(k in l for k in KEYWORDS)]
            log(f"  命中关键词行数: {len(hits)}")
            for i, l in hits[:25]:
                log(f"   [{i}] {l[:120]}")
            if not hits:
                log("   未发现违规相关字样")
            # 顺便看看有没有未读消息数
            m = re.search(r"消息\s*\n?\s*(\d+)", txt)
            if m:
                log(f"  ※ 消息数: {m.group(1)}")
        except Exception as e:
            log(f"  ERROR {str(e)[:120]}")
    b.close()
log("DONE")
