#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calibrate_article_image.py — 只读校准：点正文「图片」工具(.syl-toolbar-tool.image)，
看弹出的上传面板用的什么选择器（file input / 本地上传 / 确定）。不发布。"""
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

    print("[cal] 点击正文「图片」工具 ...")
    img_tool = page.locator(".syl-toolbar-tool.image").first
    print("   工具存在:", img_tool.count() > 0)
    img_tool.click(force=True, timeout=8000)
    time.sleep(3)

    checks = {
        ".upload-image-panel": page.locator(".upload-image-panel").count(),
        "input[type=file] (任意)": page.locator("input[type='file']").count(),
        "文本含「本地上传」": page.locator("text=本地上传").count(),
        "文本含「确定」": page.locator("button:has-text('确定')").count(),
        ".img-wrap img": page.locator(".img-wrap img").count(),
    }
    print("[cal] 面板元素计数:", checks)

    # 把面板 HTML 存下来细看
    try:
        panel_html = page.evaluate("""() => {
            const p = document.querySelector('.upload-image-panel') || document.querySelector('[class*=upload-image]');
            return p ? p.outerHTML.slice(0, 4000) : 'NO_PANEL';
        }""")
        open(os.path.join(SKILL_ROOT, "article_image_panel.html"), "w", encoding="utf-8").write(panel_html)
        print("[cal] 面板 HTML -> article_image_panel.html (", len(panel_html), "chars )")
    except Exception as e:
        print("[cal] 取面板HTML失败:", e)

    browser.close()
    print("[cal] done.")
