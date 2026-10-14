#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debug_inline_then_cover.py — 插1张正文图后，检查封面按钮为何点不开。"""
import json, os, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
cfg = json.load(open(os.path.join(SKILL_ROOT, "config.json"), "r", encoding="utf-8"))
auth = json.load(open(os.path.join(SKILL_ROOT, cfg["auth_file"]), "r", encoding="utf-8"))
images_dir = os.path.join(SKILL_ROOT, cfg.get("images_dir", "images"))

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="msedge", headless=True)
    ctx = browser.new_context()
    ctx.add_cookies(auth)
    page = ctx.new_page()
    page.set_default_timeout(25000)
    page.goto("https://mp.toutiao.com/profile_v4/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(6)
    page.locator("text=文章").first.click()
    page.wait_for_selector("[contenteditable='true']", timeout=30000); time.sleep(2)
    for sel in [".byte-drawer-close", ".ai-assistant-drawer [class*='close']"]:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click(force=True, timeout=2000); time.sleep(1); break
        except Exception:
            pass

    # 填一点正文
    ed = page.locator(".ProseMirror").first
    ed.click(force=True)
    page.keyboard.insert_text("测试段落一。")
    time.sleep(0.5)

    # 插 1 张正文图
    fname = sorted([f for f in os.listdir(os.path.join(images_dir, "article_inline")) if f.lower().endswith((".png", ".jpg", ".jpeg"))])[0]
    abs_path = os.path.join(images_dir, "article_inline", fname)
    print("[dbg] 插正文图:", fname)
    page.locator(".syl-toolbar-tool.image").first.click(force=True, timeout=6000); time.sleep(2.5)
    panel = page.locator(".upload-image-panel")
    if panel.locator("text=本地上传").count() > 0:
        panel.locator("text=本地上传").last.click(force=True, timeout=5000); time.sleep(1)
    fi = panel.locator("input[type='file']").first
    fi.wait_for(state="attached", timeout=8000)
    fi.set_input_files(abs_path, timeout=15000); time.sleep(7)
    panel.locator(".img-wrap img").last.wait_for(state="visible", timeout=15000)
    panel.locator(".img-wrap img").last.click(force=True); time.sleep(1)
    ok = page.locator("button:has-text('确定')").last
    if ok.count() > 0: ok.click(force=True, timeout=8000)
    time.sleep(3)

    # ===== 诊断 =====
    print("[dbg] 正文img数:", page.locator(".ProseMirror img").count())
    print("[dbg] 残留 .upload-image-panel 数:", page.locator(".upload-image-panel").count())
    print("[dbg] .article-cover-add 数:", page.locator(".article-cover-add").count())
    print("[dbg] .article-cover-images-wrap 数:", page.locator(".article-cover-images-wrap").count())

    # 尝试点封面
    try:
        page.locator(".article-cover-images-wrap").first.scroll_into_view_if_needed(timeout=5000)
    except Exception as e:
        print("[dbg] scroll封面区异常:", str(e)[:60])
    time.sleep(1)
    try:
        page.locator(".article-cover-add").first.click(force=True, timeout=6000)
    except Exception as e:
        print("[dbg] 点击封面异常:", str(e)[:120])
    time.sleep(3)
    print("[dbg] 点击后 .upload-image-panel 数:", page.locator(".upload-image-panel").count())
    print("[dbg] 点击后 本地上传 数:", page.locator("text=本地上传").count())

    # dump 封面区 HTML
    try:
        ch = page.evaluate("""() => {
            const w = document.querySelector('.article-cover-images-wrap');
            if (!w) return 'NO_WRAP';
            return w.outerHTML.slice(0, 2500);
        }""")
        open(os.path.join(SKILL_ROOT, "cover_area_debug.html"), "w", encoding="utf-8").write(ch)
        print("[dbg] 封面区HTML -> cover_area_debug.html")
    except Exception as e:
        print("[dbg] dump封面区失败:", e)
    page.screenshot(path=os.path.join(SKILL_ROOT, "cover_area_debug.png"), full_page=False)
    browser.close()
    print("[dbg] done")
