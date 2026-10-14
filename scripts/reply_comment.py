# -*- coding: utf-8 -*-
"""按计划文件回复头条评论（幂等：回复过的不再二次回复）。

输入计划文件格式（json 数组）：
    [{"key": "<fetch_comments.py 给的 key>", "author": "阿尔卑斯",
      "text": "<评论原文前若干字，用于定位>", "reply": "<回复正文>"}, ...]

用法：
    python scripts/reply_comment.py --plan replies.json              # 只预演，不发送
    python scripts/reply_comment.py --plan replies.json --send        # 真发送
    python scripts/reply_comment.py --plan replies.json --send --limit 3

幂等两道闸：
  1) `replied_comments.json` 台账里已有该 key → 跳过
  2) 页面上该评论已有回复（全部 N 条回复 >= 1）→ 跳过并补记台账
对齐用户 2026-09-24 指令：回复过的评论不进行二次回复。
"""
import argparse
import json
import os
import re
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
STORE = os.path.join(ROOT, "replied_comments.json")
COMMENT_URL = ("https://mp.toutiao.com/profile_v4/manage/comment/"
               "all?enter_from=left_menu")
MAX_REPLY_CHARS = 300


def log(m):
    print(m, flush=True)


def load_store():
    if os.path.exists(STORE):
        try:
            d = json.load(open(STORE, encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:  # noqa: BLE001
            pass
    return {}


def save_store(d):
    json.dump(d, open(STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def _norm(s):
    """定位用归一化：剥离空白、emoji 与标点，只留中日韩文字和字母数字。

    评论正文常带 emoji（如「👍」「🤖💼」），原样截前 12 字会因 emoji
    在页面 innerText 里形态不一致而匹配失败，故先剔除非文字字符。
    """
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", s or "", flags=re.UNICODE)


def find_item(page, plan_item):
    """按 作者 + 评论前 12 字 定位列表条目下标（忽略 emoji 与标点）。"""
    items = page.locator(".all-comment-item-wrap")
    n = items.count()
    snippet = _norm(plan_item["text"])[:12]
    author = _norm(plan_item["author"])
    for i in range(n):
        t = _norm(items.nth(i).inner_text())
        if author in t and (not snippet or snippet in t):
            return i
    return -1


def page_reply_count(page):
    d = page.evaluate(
        """() => {
            const el = document.querySelector('.comment-detail, .comment-reply-list, .all-reply-list');
            return el ? el.innerText : (document.body.innerText || '');
        }"""
    )
    m = re.search(r"(全部|共)\s*(\d+)\s*条回复", d)
    return int(m.group(2)) if m else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--send", action="store_true", help="真发送；不加则只预演")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    plan = json.load(open(os.path.join(ROOT, args.plan), encoding="utf-8"))
    if isinstance(plan, dict):
        plan = plan.get("pending", [])
    store = load_store()
    log(f"计划 {len(plan)} 条 / 台账已记 {len(store)} 条 / 模式={'真发送' if args.send else '预演'}")

    todo = []
    for p in plan:
        if not p.get("reply"):
            log(f"  -- 跳过（无回复正文）: {p.get('author')}")
            continue
        if len(p["reply"]) > MAX_REPLY_CHARS:
            log(f"  -- 截断（>{MAX_REPLY_CHARS} 字）: {p.get('author')}")
            p["reply"] = p["reply"][:MAX_REPLY_CHARS]
        if p.get("key") and p["key"] in store:
            log(f"  -- 跳过（台账已回复）: {p.get('author')} / {p['reply'][:16]}")
            continue
        todo.append(p)
    todo = todo[: args.limit]
    log(f"本次待发 {len(todo)} 条")

    if not args.send:
        for p in todo:
            log(f"  [预演] {p['author']} <- {p['reply']}")
        return

    ok, fail = 0, 0
    auth = json.load(open(os.path.join(ROOT, cfg["auth_file"]), encoding="utf-8"))
    if isinstance(auth, dict):
        auth = auth.get("cookies", [])
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 1100})
        ctx.add_cookies(auth)
        page = ctx.new_page()
        page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=45000)
        time.sleep(10)

        for p in todo:
            who = f"{p['author']} / {p['text'][:20]}"
            try:
                idx = find_item(page, p)
                if idx < 0:
                    log(f"  ✗ 页面上找不到该评论，跳过: {who}")
                    fail += 1
                    continue
                page.locator(".all-comment-item-wrap").nth(idx).click()
                time.sleep(2)
                cnt = page_reply_count(page)
                if cnt > 0:
                    log(f"  -- 页面已存在 {cnt} 条回复，跳过并补记台账: {who}")
                    if p.get("key"):
                        store[p["key"]] = {"author": p["author"], "text": p["text"],
                                           "reply": "", "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                           "note": f"页面已有{cnt}条回复"}
                    save_store(store)
                    continue

                box = page.locator("textarea.byte-textarea:visible").last
                box.click()
                box.fill(p["reply"])
                time.sleep(1)
                btn = page.locator("button.byte-btn-primary:visible",
                                   has_text="发布").last
                if btn.is_disabled():
                    log(f"  ✗ 发布按钮仍禁用，回复可能没填进去: {who}")
                    fail += 1
                    continue
                btn.click()
                time.sleep(4)

                after = page_reply_count(page)
                toast = page.evaluate(
                    "() => { const e = document.querySelector('.byte-toast'); return e ? e.innerText : ''; }"
                )
                if after > 0:
                    log(f"  ✓ 已回复 {who}（页面回复数 {after}）toast={toast[:20]}")
                    ok += 1
                    if p.get("key"):
                        store[p["key"]] = {"author": p["author"], "text": p["text"],
                                           "reply": p["reply"],
                                           "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
                    save_store(store)
                else:
                    log(f"  ✗ 回复未生效（页面回复数仍 0）toast={toast[:40]}: {who}")
                    fail += 1
            except Exception as e:  # noqa: BLE001
                log(f"  ✗ 异常 {str(e)[:90]}: {who}")
                fail += 1
        b.close()

    log(f"\n结果：成功 {ok} / 失败 {fail} / 台账累计 {len(store)}")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
