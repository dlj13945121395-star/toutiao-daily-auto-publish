# -*- coding: utf-8 -*-
"""抓取头条「站内话题」+ 讨论数（官方话题池）。

原理：微头条发布页的正文编辑器输入 `#关键词` 会实时弹出话题联想下拉，
      下拉里就是站内真实话题和它的讨论数，形如 `#Token经济会成为下一个风口吗# 60讨论`。
      比 WebSearch 抓的热榜更准 —— 这是平台自己的话题，能直接挂到微头条末尾。

用法：
    python scripts/fetch_topics.py                                  # 用默认关键词
    python scripts/fetch_topics.py --keywords "Token,AI,副业" --top 15
    python scripts/fetch_topics.py --keywords "AI漫剧,爱奇艺AI剧场" --write-hot   # 合并写入 hot_topics_today.json
只读发布页的话题联想，**不发布、不存草稿**，读完会清空编辑器内容。
"""
import argparse
import json
import os
import re
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))

# 截图里官方推荐的 8 个话题 + 账号定位关键词
DEFAULT_KEYWORDS = [
    "Token经济", "Token", "如果不缺钱", "AI长剧", "AI剧场",
    "AI医疗", "AI漫剧", "谷歌AI摘要",
]
POSITIONING_KEYWORDS = ["AI工具", "人工智能", "副业", "职场效率"]

ROW_RE = re.compile(r"#([^#\n]{2,40})#\s*(\d+)\s*讨论")


def grab(page, keyword):
    """重载发布页 → 输入 #关键词 → 解析话题联想。返回 [(话题, 讨论数)]。

    每条关键词都重新 reload：编辑器在清空/失焦后会从 DOM 摘掉，
    复用同一个页面再点会 Timeout，重载最稳。
    """
    page.goto(cfg["publish_url"], wait_until="domcontentloaded", timeout=45000)
    time.sleep(7)
    box = page.locator("[contenteditable='true']").first
    box.click()
    box.type("#" + keyword, delay=80)
    time.sleep(4.5)
    txt = page.evaluate("() => document.body ? document.body.innerText : ''")
    rows = ROW_RE.findall(txt)
    out, seen = [], set()
    for name, cnt in rows:
        if name in seen:
            continue
        seen.add(name)
        out.append((name, int(cnt)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", default="", help="逗号分隔；留空用默认（截图里的官方话题 + 定位词）")
    ap.add_argument("--top", type=int, default=20, help="每个关键词最多保留多少条")
    ap.add_argument("--write-hot", action="store_true", help="把结果并入 hot_topics_today.json 的 trending")
    ap.add_argument("--out", default="topics_probe.json")
    args = ap.parse_args()

    kws = [k.strip() for k in args.keywords.split(",") if k.strip()] or DEFAULT_KEYWORDS
    auth = json.load(open(os.path.join(ROOT, cfg["auth_file"]), encoding="utf-8"))
    if isinstance(auth, dict):
        auth = auth.get("cookies", [])

    result = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        ctx.add_cookies(auth)
        page = ctx.new_page()
        page.goto(cfg["publish_url"], wait_until="domcontentloaded", timeout=45000)
        time.sleep(7)

        for kw in kws:
            try:
                rows = grab(page, kw)[: args.top]
            except Exception as e:  # noqa: BLE001
                print(f"[{kw}] 抓取异常: {str(e)[:100]}")
                continue
            result[kw] = [{"topic": f"#{n}#", "discuss": c} for n, c in rows]
            print(f"\n=== 关键词「{kw}」命中 {len(rows)} 个站内话题 ===")
            for n, c in rows[:8]:
                print(f"   #{n}#  {c} 讨论")

        b.close()

    with open(os.path.join(ROOT, args.out), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    total = sum(len(v) for v in result.values())
    print(f"\n共 {len(result)} 个关键词 / {total} 条话题，已写 {args.out}")

    if args.write_hot:
        hp = os.path.join(ROOT, cfg["hot_topics_file"])
        hot = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else {}
        hot.setdefault("positioning", ["#AI工具#", "#人工智能#", "#副业#", "#职场效率#"])
        merged = list(hot.get("fresh_topics_from_platform", []))
        for kw, rows in result.items():
            for r in rows:
                if r["topic"] not in merged:
                    merged.append(r["topic"])
        hot["fresh_topics_from_platform"] = merged[:40]
        with open(hp, "w", encoding="utf-8") as f:
            json.dump(hot, f, ensure_ascii=False, indent=2)
        print(f"已并入 {cfg['hot_topics_file']}，新增字段 fresh_topics_from_platform（{len(hot['fresh_topics_from_platform'])} 条）")


if __name__ == "__main__":
    main()
