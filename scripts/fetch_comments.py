# -*- coding: utf-8 -*-
"""抓取头条「评论管理」页的评论列表，判定哪些还没回复过。

判定「已回复」用两道闸，任一命中就跳过：
  1) 本地台账 `replied_comments.json`（key = 作者 + 评论正文的哈希）—— 主力防线
  2) 页面上该评论的回复数 > 0（详情区「全部 N 条回复」）

用法：
    python scripts/fetch_comments.py                     # 打印全部评论 + 待回复清单
    python scripts/fetch_comments.py --out pending_comments.json
    python scripts/fetch_comments.py --debug             # 打印第一条的原始 innerText，便于校准解析
只读页面，不输入、不发布。
"""
import argparse
import hashlib
import json
import os
import re
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
AUTH = json.load(open(os.path.join(ROOT, cfg["auth_file"]), encoding="utf-8"))
if isinstance(AUTH, dict):
    AUTH = AUTH.get("cookies", [])

COMMENT_URL = ("https://mp.toutiao.com/profile_v4/manage/comment/"
               "all?enter_from=left_menu")
STORE = os.path.join(ROOT, "replied_comments.json")

TIME_RE = re.compile(r"(刚刚|今天\s*\d{1,2}:\d{2}|昨日\s*\d{1,2}:\d{2}|\d{1,2}-\d{1,2}\s*\d{1,2}:\d{2}"
                     r"|\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}|\d{1,2}分钟前|\d{1,2}小时前)")

# 列表条目里要剔掉的按钮/标签词
NOISE = {"回复", "赞", "置顶", "取消置顶", "删除", "举报", "展开", "收起", "已回复", "作者"}


def key_of(author, text):
    h = hashlib.md5((author + "||" + text).encode("utf-8")).hexdigest()[:12]
    return h


def load_store():
    if os.path.exists(STORE):
        try:
            d = json.load(open(STORE, encoding="utf-8"))
            if isinstance(d, dict):
                return d
        except Exception:  # noqa: BLE001
            pass
    return {}


def parse_item(txt):
    """把条目的 innerText 拆成 作者 / 时间 / 目标作品 / 评论正文。"""
    lines = [x.strip() for x in txt.split("\n") if x.strip()]
    author = lines[0] if lines else ""
    time_s = ""
    for ln in lines:
        m = TIME_RE.search(ln)
        if m:
            time_s = m.group(1)
            break
    # 目标作品：夹在《 》之间
    target = ""
    m = re.search(r"《\s*(.+?)\s*》", txt, re.S)
    if m:
        target = " ".join(m.group(1).split())
    # 评论正文：取时间行之后、噪声词之前的那段
    body = ""
    try:
        idx_time = next(i for i, ln in enumerate(lines) if TIME_RE.search(ln))
        head = "评论了微头条"
        idx_head = next((i for i, ln in enumerate(lines) if head in ln or "评论了文章" in ln), 0)
        after = [ln for ln in lines[idx_head + 1: idx_time] if ln not in ("《", "》") and ln not in NOISE]
        # 去掉与作品引文重复的部分：作品引文通常更长，评论在最后
        after = [ln for ln in after if not target or ln[:20] not in target]
        body = " ".join(after).strip()
        if len(body) > 160 and target:
            idx = body.rfind(target[-16:])
            if idx >= 0:
                body = body[idx + len(target[-16:]):].strip()
    except StopIteration:
        pass
    return {"author": author, "time": time_s, "target": target[:80], "text": body[:300]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="把待回复评论写到该 json")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    store = load_store()
    rows = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 1100})
        ctx.add_cookies(AUTH)
        page = ctx.new_page()
        page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=45000)
        time.sleep(10)

        items = page.locator(".all-comment-item-wrap")
        n = items.count()
        print(f"评论区条目数: {n}")

        if args.debug and n:
            print("\n--- 第一条原始 innerText ---")
            print(items.nth(0).inner_text()[:800])
            print("--- end ---\n")

        for i in range(n):
            try:
                it = items.nth(i)
                rec = parse_item(it.inner_text())
                # 点击该条 → 复核回复情况
                it.click()
                time.sleep(1.8)
                page_txt = page.evaluate("() => document.body ? document.body.innerText : ''")
                m = re.search(r"(全部|共)\s*(\d+)\s*条回复", page_txt)
                rec["page_reply_count"] = int(m.group(2)) if m else 0
                rec["key"] = key_of(rec["author"], rec["text"])
                prev = store.get(rec["key"]) or {}
                rec["replied_local"] = rec["key"] in store
                # 二次复核：页面正文里能否找到台账里记的那条回复原文
                prev_reply = (prev.get("reply") or "").strip()
                rec["reply_text_on_page"] = bool(
                    prev_reply and len(prev_reply) >= 8 and prev_reply[:18] in page_txt
                )
                rec["need_reply"] = (not rec["replied_local"]) and rec["page_reply_count"] == 0
                rows.append(rec)
            except Exception as e:  # noqa: BLE001
                print(f"  第 {i} 条解析异常: {str(e)[:90]}")
        b.close()

    print(f"\n{'待回':<4}{'页面回复数':<8}{'本地已回':<8}{'原文在页':<8}时间 / 作者 / 评论")
    pending = []
    for r in rows:
        flag = "★" if r["need_reply"] else " "
        print(f"{flag:<4}{r['page_reply_count']:<10}{str(r['replied_local']):<9}"
              f"{str(r.get('reply_text_on_page')):<9}{r['time']} / {r['author']} / {r['text'][:60]}")
        if r["need_reply"]:
            pending.append(r)

    print(f"\n待回复 {len(pending)} 条 / 共 {len(rows)} 条")
    if args.out:
        json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "total": len(rows), "pending": pending},
                  open(os.path.join(ROOT, args.out), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("已写", args.out)


if __name__ == "__main__":
    main()
