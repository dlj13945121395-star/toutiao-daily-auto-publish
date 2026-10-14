#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inspect_article_editor.py — 只读探测：打开头条文章编辑器，把工具栏/可点击元素
导出来，用于校准「正文插图」按钮的真实选择器。不发布、不填稿。"""
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

    # 1) 全页保存（便于细查）
    html = page.content()
    out = os.path.join(SKILL_ROOT, "article_editor_inspect.html")
    open(out, "w", encoding="utf-8").write(html)
    print(f"[inspect] 全页 HTML -> {out} ({len(html)} bytes)")

    # 2) 打印所有文本含「图片」的可点击元素及其选择器线索
    print("\n=== 文本含「图片」的元素 ===")
    nodes = page.evaluate("""() => {
        const out = [];
        const all = Array.from(document.querySelectorAll('*'));
        for (const e of all) {
            const t = (e.innerText || '').trim();
            if (t.includes('图片') && t.length < 20) {
                out.push({tag: e.tagName, cls: e.className, text: t,
                          xpath_hint: e.tagName.toLowerCase() + (e.id?('#'+e.id):'') + (typeof e.className==='string'&&e.className?('.'+e.className.trim().split(/\\s+/).join('.')):'')});
            }
        }
        return out.slice(0, 40);
    }""")
    for n in nodes:
        print(f"  <{n['tag']} class='{n['cls']}'> {n['text']}")

    # 3) 打印 ProseMirror 上方的工具栏按钮（常见容器）
    print("\n=== .ProseMirror 附近工具栏按钮 ===")
    btns = page.evaluate("""() => {
        const pm = document.querySelector('.ProseMirror');
        if (!pm) return ['NO .ProseMirror'];
        // 向上找最近的若干兄弟/父级里的 button
        const res = [];
        let node = pm;
        for (let i=0;i<6 && node; i++) {
            const bs = Array.from(node.querySelectorAll('button, [role=button], span, i'))
                       .filter(b => (b.innerText||'').trim().length>0 && (b.innerText||'').trim().length<12);
            for (const b of bs) res.push((b.tagName)+'|'+(b.className||'')+'|'+(b.innerText||'').trim());
            node = node.parentElement;
        }
        return res.slice(0, 60);
    }""")
    for b in btns:
        print("  ", b)

    browser.close()
    print("\n[inspect] done.")
