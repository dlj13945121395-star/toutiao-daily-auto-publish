# -*- coding: utf-8 -*-
"""只读探针 5：摸清「评论管理」页的 DOM 结构，为自动化回复做准备。
目标：
  1) 评论列表条目怎么定位（作者 / 时间 / 正文 / 是否已回复）
  2) 右侧回复区：输入框与「发布」按钮的选择器
不输入、不发布。
"""
import json
import os
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
auth = json.load(open(os.path.join(ROOT, cfg["auth_file"]), encoding="utf-8"))
if isinstance(auth, dict):
    auth = auth.get("cookies", [])

URL = "https://mp.toutiao.com/profile_v4/manage/comment/all?enter_from=left_menu"
SHOT = os.path.join(ROOT, "probe_comment3.png")

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 1100})
    ctx.add_cookies(auth)
    page = ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    time.sleep(10)

    print("== 1) 找评论条目容器 ==")
    info = page.evaluate(
        """() => {
            const out = {items: [], replyAreas: [], btns: []};
            // 列表条目：包含「回复」「赞」的最近公共祖先
            const all = Array.from(document.querySelectorAll('div,li,section'));
            const cands = all.filter(e => {
                const t = (e.innerText||'');
                return t.includes('评论了') && t.length < 400;
            });
            out.items = cands.slice(0,3).map(e => ({
                cls: e.className, tag: e.tagName,
                text: (e.innerText||'').replace(/\\n+/g,' | ').slice(0,220)
            }));
            // 回复输入区
            const ta = Array.from(document.querySelectorAll("textarea,[contenteditable='true']"));
            out.replyAreas = ta.slice(0,4).map(e => ({
                tag: e.tagName, cls: e.className,
                ph: e.getAttribute('placeholder') || '',
                visible: !!(e.offsetParent)
            }));
            out.btns = Array.from(document.querySelectorAll('button')).slice(0,8)
                .map(b => ({t:(b.innerText||'').trim().slice(0,10), cls:(b.className||'').slice(0,70),
                            disabled: b.disabled}));
            return out;
        }"""
    )
    print(json.dumps(info, ensure_ascii=False, indent=2)[:3000])

    print("\n== 2) 点第一条评论，看右侧回复区 ==")
    try:
        first = page.locator("text=评论了").first
        first.click()
        time.sleep(3)
        detail = page.evaluate(
            """() => {
                const ta = Array.from(document.querySelectorAll("textarea,[contenteditable='true']"))
                    .filter(e => e.offsetParent);
                const btns = Array.from(document.querySelectorAll('button'))
                    .filter(e => e.offsetParent)
                    .map(b => ({t:(b.innerText||'').trim().slice(0,10), cls:(b.className||'').slice(0,70), disabled:b.disabled}));
                return {inputs: ta.map(e=>({tag:e.tagName, cls:e.className, ph:e.getAttribute('placeholder')||''})),
                        btns: btns};
            }"""
        )
        print(json.dumps(detail, ensure_ascii=False, indent=2)[:2000])
        page.screenshot(path=SHOT, full_page=False)
        print("截图:", SHOT)
    except Exception as e:  # noqa: BLE001
        print("点击异常:", str(e)[:200])
    b.close()
