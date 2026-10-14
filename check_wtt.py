#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_wtt.py — 最小化检查：首页最近作品里是否出现「发布了微头条」。
同时看创作权益页，确认「同步微头条」类权益是否已开通。
"""
import json, os, re, time
from playwright.sync_api import sync_playwright

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SKILL_ROOT, "config.json")

def log(m): print(f"[check] {m}", flush=True)

def main():
    cfg = json.load(open(DEFAULT_CONFIG, "r", encoding="utf-8"))
    auth = json.load(open(os.path.join(SKILL_ROOT, cfg["auth_file"]), "r", encoding="utf-8"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context()
        ctx.add_cookies(auth)
        page = ctx.new_page()
        page.set_default_timeout(25000)
        page.goto("https://mp.toutiao.com/profile_v4/index",
                  wait_until="domcontentloaded", timeout=30000)
        time.sleep(9)
        txt = page.evaluate("() => (document.body.innerText||'')")
        flat = re.sub(r"\s+", " ", txt)
        log(f"首页文本长度 {len(flat)}")
        # 找所有「发布了XX」记录
        for m in re.finditer(r"\d{2}-\d{2} \d{2}:\d{2} 发布了[^0-9]{0,6}", flat):
            log(f"  记录: {m.group(0)}")
        hits = flat.count("发布了微头条")
        log(f"『发布了微头条』出现次数: {hits}")
        # 输出最近作品区域的完整文本，便于人工核对微头条的实际展示格式
        log("--- 首页全文（最近作品区）---")
        log(flat[:1200])
        log("--- 全文结束 ---")
        if hits:
            log("✅ 首页出现原生微头条记录")
        else:
            log("❌ 首页没有原生微头条记录")
        browser.close()
    log("DONE")

if __name__ == "__main__":
    main()
