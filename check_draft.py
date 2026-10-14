#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_draft.py — 列出头条草稿箱当前所有条目（含类型/标题/时间），用于核对存草稿结果。"""
import json, os, re, time
from playwright.sync_api import sync_playwright

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SKILL_ROOT, "config.json")
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

def log(m): print(f"[check_draft] {m}", flush=True)

def main():
    cfg = json.load(open(DEFAULT_CONFIG, "r", encoding="utf-8"))
    auth = json.load(open(os.path.join(SKILL_ROOT, cfg["auth_file"]), "r", encoding="utf-8"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context()
        ctx.add_cookies(auth)
        page = ctx.new_page()
        page.set_default_timeout(25000)
        page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(9)
        flat = re.sub(r"\s+", " ", page.evaluate("() => (document.body.innerText||'')"))
        m = re.search(r"共\s*(\d+)\s*条", flat)
        log(f"草稿箱共 {m.group(1) if m else '?'} 条")
        # 抓条目（含「编辑」「删除」的行）
        items = page.evaluate("""() => {
            const out = [];
            const rows = Array.from(document.querySelectorAll('[class*="item"], tr, li, [class*="card"]'));
            for (const r of rows) {
                const t = (r.innerText||'').replace(/\\s+/g,' ').trim();
                if (t && t.length < 150 && (t.includes('编辑') || t.includes('删除'))) out.push(t);
            }
            return out.slice(0, 15);
        }""")
        for i, it in enumerate(items):
            log(f"  [{i+1}] {it}")
        if not items:
            log(f"  未解析到条目，页面文本: {flat[:300]}")
        browser.close()

if __name__ == "__main__":
    main()
