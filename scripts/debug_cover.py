#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debug_cover.py — 隔离调试：只测「点封面按钮 → 面板是否弹出 / 是否有本地上传」。"""
import json, os, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
cfg = json.load(open(os.path.join(SKILL_ROOT, "config.json"), "r", encoding="utf-8"))
auth = json.load(open(os.path.join(SKILL_ROOT, cfg["auth_file"]), "r", encoding="utf-8"))

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="msedge", headless=True)
    ctx = browser.new_context()
    ctx.add_cookies(auth)
    page = ctx.new_page()
    page.set_default_timeout(25000)
    page.goto("https://mp.toutiao.com/profile_v4/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(6)
    page.locator("text=文章").first.click()
    page.wait_for_selector("[contenteditable='true']", timeout=30000); time.sleep(3)
    for sel in [".byte-drawer-close", ".ai-assistant-drawer [class*='close']"]:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click(force=True, timeout=2000); time.sleep(1); break
        except Exception:
            pass

    print("[dbg] 封面按钮是否存在:", page.locator(".article-cover-add").count())
    # 普通点击
    try:
        page.locator(".article-cover-add").first.click(force=True, timeout=5000)
    except Exception as e:
        print("  普通点击异常:", str(e)[:80])
    time.sleep(5)
    print("[dbg] 点击后 .upload-image-panel 数:", page.locator(".upload-image-panel").count())
    print("[dbg] 点击后 本地上传 数:", page.locator("text=本地上传").count())
    # JS 派发兜底
    if page.locator("text=本地上传").count() == 0:
        page.evaluate("() => { const e=document.querySelector('.article-cover-add'); if(e) e.click(); }")
        time.sleep(5)
        print("[dbg] JS派发后 本地上传 数:", page.locator("text=本地上传").count())
        print("[dbg] JS派发后 .upload-image-panel 数:", page.locator(".upload-image-panel").count())

    # dump 面板 HTML
    try:
        ph = page.evaluate("""() => {
            const ps = ['.upload-image-panel','.article-cover-modal','.article-cover-images-wrap','.byte-modal'];
            for (const s of ps){ const e=document.querySelector(s); if(e) return s+'::'+e.outerHTML.slice(0,3000); }
            return 'NONE_OF_PANELS';
        }""")
        open(os.path.join(SKILL_ROOT, "cover_debug.html"), "w", encoding="utf-8").write(ph)
        print("[dbg] 面板HTML -> cover_debug.html")
    except Exception as e:
        print("[dbg] dump失败:", e)
    page.screenshot(path=os.path.join(SKILL_ROOT, "cover_debug.png"), full_page=True)
    browser.close()
    print("[dbg] done")
