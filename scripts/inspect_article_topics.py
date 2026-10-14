#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inspect_article_topics.py — 只读探测：文章编辑器里「话题」是怎么加进去的。

动作：打开文章编辑器 → 打印工具栏按钮文本 → 在正文里敲一个 `#` →
抓取随后弹出的候选面板 DOM（class/文本）→ 保存全页 HTML 供离线分析。
不填稿、不发布、不保存。跑完直接关闭。
"""
import json
import os
import time

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
    page.wait_for_selector("[contenteditable='true']", timeout=30000)
    time.sleep(3)
    for sel in [".byte-drawer-close", ".ai-assistant-drawer [class*='close']"]:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click(force=True, timeout=2000)
                time.sleep(1)
                break
        except Exception:
            pass

    print("\n=== 工具栏 / 编辑器附近按钮文本 ===")
    btns = page.evaluate("""() => {
        const res = [];
        document.querySelectorAll('button,[role=button],[class*=toolbar] *,[class*=tool] *').forEach(e=>{
            const t=(e.innerText||'').trim();
            if(t && t.length<=10) res.push(e.tagName+'|'+(typeof e.className==='string'?e.className:'')+'|'+t);
        });
        return Array.from(new Set(res)).slice(0,80);
    }""")
    for b in btns:
        print("  ", b)

    print("\n=== 在正文敲 `#` 触发候选 ===")
    ed = page.locator(".ProseMirror").first
    ed.click(force=True)
    page.keyboard.press("End")
    page.keyboard.press("Enter")
    snapshot0 = set()
    page.keyboard.type("#", delay=120)
    time.sleep(2.5)

    pop = page.evaluate("""() => {
        const out=[];
        document.querySelectorAll('*').forEach(e=>{
            const cls=(typeof e.className==='string')?e.className:'';
            if(/select|dropdown|popup|suggest|topic|panel|menu|list/i.test(cls)){
                const t=(e.innerText||'').trim();
                if(t && t.length<600) out.push({cls:cls, text:t.slice(0,300)});
            }
        });
        return out.slice(0,40);
    }""")
    print("候选元素数:", len(pop))
    for p in pop:
        print(f"  [{p['cls'][:60]}] {p['text']!r}")

    html = page.content()
    out = os.path.join(SKILL_ROOT, "article_topic_inspect.html")
    open(out, "w", encoding="utf-8").write(html)
    print(f"\n[saved] {out} ({len(html)} bytes)")

    page.keyboard.press("Escape")
    browser.close()
    print("[inspect] done.")
