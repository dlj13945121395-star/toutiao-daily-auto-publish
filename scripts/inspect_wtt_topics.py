#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inspect_wtt_topics.py — 只读探测：微头条编辑器的「话题联想」DOM 结构。

背景：微头条正文里的 `#话题#` 若按纯文本插入，会变成不可点击的普通文字。
需要像文章那样走「输 `#` → 弹候选 → 点选」才能挂成真话题（可点击跳转）。
本脚本只读探测候选面板的 DOM（class / 文本），用于校准选择器。
不填稿、不发布、不存草稿；跑完清空并关闭。

用法：
    python scripts/inspect_wtt_topics.py                # 默认用 #AI工具
    python scripts/inspect_wtt_topics.py --kw Token经济
"""
import argparse
import json
import os
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
auth = json.load(open(os.path.join(ROOT, cfg["auth_file"]), encoding="utf-8"))
if isinstance(auth, dict):
    auth = auth.get("cookies", [])

ap = argparse.ArgumentParser()
ap.add_argument("--kw", default="AI工具", help="用于触发联想的词（不带 #）")
args = ap.parse_args()

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    ctx.add_cookies(auth)
    page = ctx.new_page()
    page.set_default_timeout(25000)
    page.goto(cfg["publish_url"], wait_until="domcontentloaded", timeout=45000)
    time.sleep(7)

    ed = page.locator("[contenteditable='true']").first
    ed.click()
    time.sleep(0.6)
    page.keyboard.type("#" + args.kw, delay=90)
    time.sleep(4.5)

    print("\n=== 候选元素（class 含 select/dropdown/popup/suggest/topic/panel/menu/list）===")
    pop = page.evaluate("""() => {
        const out=[];
        document.querySelectorAll('*').forEach(e=>{
            const cls=(typeof e.className==='string')?e.className:'';
            if(/select|dropdown|popup|suggest|topic|panel|menu|list|forum/i.test(cls)){
                const t=(e.innerText||'').trim();
                if(t && t.length<600) out.push({cls:cls, text:t.slice(0,200)});
            }
        });
        return out.slice(0,40);
    }""")
    print("候选元素数:", len(pop))
    for p in pop:
        print(f"  [{p['cls'][:70]}] {p['text']!r}")

    print("\n=== 含「讨论」字样的元素（话题候选项特征）===")
    rows = page.evaluate("""() => {
        const out=[];
        document.querySelectorAll('*').forEach(e=>{
            const t=(e.innerText||'').trim();
            if(/^#.{1,40}#\\s*\\d+\\s*讨论$/.test(t)){
                const cls=(typeof e.className==='string')?e.className:'';
                const pcls=(e.parentElement && typeof e.parentElement.className==='string')?e.parentElement.className:'';
                out.push({tag:e.tagName, cls:cls, ptag:e.parentElement?e.parentElement.tagName:'', pcls:pcls, text:t});
            }
        });
        return out.slice(0,40);
    }""")
    print("命中条数:", len(rows))
    for r in rows:
        print(f"  {r['tag']}[{r['cls'][:45]}] <- {r['ptag']}[{r['pcls'][:45]}]  {r['text']!r}")

    out_html = os.path.join(ROOT, "wtt_topic_inspect.html")

    # ---- 点选验证：点第一个候选，看编辑器里有没有出现真话题节点 ----
    print("\n=== 点选验证 ===")
    try:
        items = page.locator(".mention-selector-modal .forum-list-item")
        n = items.count()
        clicked = False
        for k in range(n):
            it = items.nth(k)
            cls = it.get_attribute("class") or ""
            if "create-forum-button" in cls:
                continue
            print("  点击候选:", (it.inner_text() or "")[:40].replace("\n", " "))
            it.click(force=True)
            time.sleep(1.0)
            clicked = True
            break
        if not clicked:
            print("  !! 未找到可点候选")
        else:
            info = page.evaluate("""() => {
                const ed = document.querySelector("[contenteditable='true']");
                if (!ed) return {html:'', nodes:0};
                const as = ed.querySelectorAll('a[class*=tteditor-forum], a[data-concern-id]');
                return {nodes: as.length,
                        html: as.length ? as[0].outerHTML.slice(0,240) : ed.innerHTML.slice(0,240)};
            }""")
            print("  可点击话题节点数 =", info["nodes"])
            print("  节点HTML =", info["html"])
            print("  判定：", "✅ 已挂成可点击话题" if info["nodes"] > 0 else "❌ 仍是纯文本")
    except Exception as e:
        print("  点选验证异常:", str(e)[:120])

    open(out_html, "w", encoding="utf-8").write(page.content())
    print(f"\n[saved] {out_html}")

    # 清空编辑器，避免留下残稿
    try:
        ed.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
    except Exception:
        pass
    browser.close()
    print("[inspect] done.")
