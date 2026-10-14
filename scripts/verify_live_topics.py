#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_live_topics.py — 只读探测：今天批次里每个话题在站内「话题联想」里是否真搜得到。

背景：话题只有走选择器点选才会变成可点击链接；而选择器只认站内真话题。
     若话题名不在站内话题库里 → 搜不到候选 → 脚本退化为纯文本 → 点不动。
      本脚本把「今天还没发布」的各个 slot 的话题逐个拿到发布页实测，输出 HIT/MISS。

不填稿、不发布、不存草稿；每个关键词都重载发布页（与 fetch_topics.py 同法）。

用法：
    python scripts/verify_live_topics.py                # 检查未发布 slot 的全部话题
    python scripts/verify_live_topics.py --slots 1,2,3  # 指定 slot
"""
import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
ROW_RE = re.compile(r"#([^#\n]{2,40})#\s*(\d+)\s*讨论")
cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))


def norm(s):
    return re.sub(r"[\s#\u200b\u200c\u200d]+", "", s or "")


_TOPIC_SPLIT = re.compile(r"[，,。.、！!？?；;：:（）()【】\[\]]")


def topic_queries(name):
    """与 publish_draft.py / publish_article_draft.py 完全一致的多查询词策略：
    全名 → 首个标点前 → 前8/6/4 字。站内联想按短关键词匹配，全名常常搜不到。"""
    qs = [name]
    head = _TOPIC_SPLIT.split(name)[0].strip()
    if head and head != name:
        qs.append(head)
    for n in (8, 6, 4):
        if len(name) > n:
            qs.append(name[:n])
    seen, out = set(), []
    for q in qs:
        q = (q or "").strip()
        if len(q) >= 2 and q not in seen:
            seen.add(q)
            out.append(q)
    return out


def trailing_topics_article(body):
    tail = body.strip().split(NL * 2)[-1]
    return [t.strip("#") for t in tail.split() if t.startswith("#")]


def trailing_topics_wtt(body):
    lines = [x for x in body.split(NL) if x.strip()]
    if not lines:
        return []
    return [t.strip("#") for t in lines[-1].split() if t.startswith("#")]


def collect(slots):
    """返回 {slot: {'article': [话题], 'wtt': [话题]}}"""
    out = {}
    ab = json.load(open(os.path.join(ROOT, "articles_batch.json"), encoding="utf-8"))
    wb = json.load(open(os.path.join(ROOT, "wtt_batch.json"), encoding="utf-8"))
    for a in ab["articles"]:
        if a.get("publish_status") in ("published", "scheduled"):
            continue
        if slots and a.get("slot") not in slots:
            continue
        out.setdefault(a["slot"], {})["article"] = trailing_topics_article(a["body"])
    for w in wb:
        if slots and w.get("slot") not in slots:
            continue
        out.setdefault(w["slot"], {})["wtt"] = trailing_topics_wtt(w["body"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slots", default="", help="逗号分隔；留空=所有未发布 slot")
    ap.add_argument("--only", default="", help="只测这些话题（逗号分隔），用于复测疑似假阴性")
    ap.add_argument("--wait", type=float, default=4.5, help="输完后的等待秒数（默认 4.5）")
    ap.add_argument("--out", default="live_topics_report.json")
    args = ap.parse_args()
    slots = {int(x) for x in args.slots.split(",") if x.strip().isdigit()}

    if args.only:
        plan = {}
        uniq = [t.strip() for t in args.only.split(",") if t.strip()]
    else:
        plan = collect(slots)
        uniq = []
        for s in sorted(plan):
            for kind in ("article", "wtt"):
                for t in plan[s].get(kind, []):
                    if t not in uniq:
                        uniq.append(t)

    print(f"[verify_live_topics] 待测 slot = {sorted(plan)}，去重后话题 {len(uniq)} 个")
    for t in uniq:
        print("   -", t)

    auth = json.load(open(os.path.join(ROOT, cfg["auth_file"]), encoding="utf-8"))
    if isinstance(auth, dict):
        auth = auth.get("cookies", [])

    from playwright.sync_api import sync_playwright

    result = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        ctx.add_cookies(auth)
        page = ctx.new_page()

        for topic in uniq:
            target = norm(topic)
            cands, probe_log, hit, near = [], [], False, []
            page.goto(cfg["publish_url"], wait_until="domcontentloaded", timeout=45000)
            time.sleep(9)
            box = page.locator("[contenteditable='true']").first
            box.click()
            time.sleep(0.6)
            for q in topic_queries(topic):
                try:
                    box.click()
                    page.keyboard.type("#" + q, delay=90)
                    time.sleep(args.wait)
                    txt = page.evaluate("() => document.body ? document.body.innerText : ''")
                    cs, seen = [], set()
                    for name, cnt in ROW_RE.findall(txt):
                        if name not in seen:
                            seen.add(name)
                            cs.append(name)
                    probe_log.append({"q": q, "cands": cs[:8]})
                    if cs:
                        cands = cs
                        for c in cs:
                            if norm(c) == target:
                                hit = True
                                break
                        if not hit:
                            near = [c for c in cs if target in norm(c) or norm(c) in target]
                        if hit:
                            break
                        # 有候选但都不匹配 → 继续用更短的查询词试
                except Exception as e:
                    probe_log.append({"q": q, "error": str(e)[:80]})
                # 清空编辑器，为下一个查询词重置
                try:
                    box.click()
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    time.sleep(0.5)
                except Exception:
                    pass
            result[topic] = {"hit": hit, "near": near[:5], "probes": probe_log}
            flag = "HIT " if hit else ("NEAR" if near else "MISS")
            qs = [p.get("q") for p in probe_log if p.get("cands")]
            print(f"  [{flag}] {topic}  -> 命中查询词 {qs if qs else '无'}  "
                  f"{'节点候选:' + str(near[:3]) if near and not hit else ''}", flush=True)

        b.close()

    json.dump(result, open(os.path.join(ROOT, args.out), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    hits = [t for t, v in result.items() if v.get("hit")]
    nears = [t for t, v in result.items() if not v.get("hit") and v.get("near")]
    miss = [t for t, v in result.items() if not v.get("hit") and not v.get("near")]
    print()
    print(f"命中 {len(hits)} / 近似 {len(nears)} / 搜不到 {len(miss)}")
    if miss:
        print("❌ 搜不到（会退化为纯文本）:", miss)
    if nears:
        print("⚠️ 只有近似候选:", nears)
    print("报告已写", args.out)
    return 0 if not miss else 1


if __name__ == "__main__":
    sys.exit(main())
