#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_today_batch.py — 一键核验「今天要发的批次是不是今天生成的」。

只读脚本，不改动任何文件。用于发布前自检，或人工核对。
检查项：
  1. articles_batch.json 的 generated_at 日期 == 今天
  2. wtt_batch.json 的文件修改日期（mtime）== 今天
  3. hot_topics_today.json 的 date == 今天
  4. 今日各篇标题未出现在 published_topics.json（避免重复发同题）
  5. 每个 slot 的 inline_images 文件都存在于 images/article_inline/

全部通过 → 打印 PASS，exit 0；任一失败 → 打印 FAIL 明细，exit 1。

用法：
  python scripts/verify_today_batch.py
  python scripts/verify_today_batch.py --json     # 机器可读输出
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ART = os.path.join(ROOT, "articles_batch.json")
WTT = os.path.join(ROOT, "wtt_batch.json")
HOT = os.path.join(ROOT, "hot_topics_today.json")
PT = os.path.join(ROOT, "published_topics.json")
IMG_DIR = os.path.join(ROOT, "images", "article_inline")


def today():
    return datetime.date.today().isoformat()


def mdate(p):
    try:
        return datetime.date.fromtimestamp(os.path.getmtime(p)).isoformat()
    except OSError:
        return None


def check():
    t = today()
    checks = []

    # 1) articles_batch.json generated_at
    gen = ""
    try:
        b = json.load(open(ART, encoding="utf-8"))
        gen = str(b.get("generated_at", "") or "")
        arts = b.get("articles", []) if isinstance(b, dict) else []
    except Exception as e:
        arts = []
        checks.append(("articles_batch.generated_at", False, f"读取失败 {str(e)[:60]}"))
    else:
        ok = gen.startswith(t)
        checks.append(("articles_batch.generated_at", ok,
                       f"{gen[:19] or '(空)'} {'==' if ok else '!='} {t}"))

    # 2) wtt_batch.json mtime
    md = mdate(WTT)
    checks.append(("wtt_batch.mtime", md == t, f"{md} {'==' if md == t else '!='} {t}"))

    # 3) hot_topics_today.json date
    hd = ""
    try:
        hd = str(json.load(open(HOT, encoding="utf-8")).get("date", ""))
    except Exception as e:
        checks.append(("hot_topics_today.date", False, f"读取失败 {str(e)[:60]}"))
    else:
        checks.append(("hot_topics_today.date", hd == t, f"{hd or '(空)'} {'==' if hd == t else '!='} {t}"))

    # 4) 标题不重复（只查**还没发布**的 slot —— slot0 发布后其标题本就会进 published_topics）
    titles = [a.get("title", "") for a in arts
              if a.get("publish_status") not in ("published", "scheduled")]
    try:
        pt = json.load(open(PT, encoding="utf-8"))
        seen = {x.get("title") for x in pt if isinstance(x, dict)}
    except Exception:
        seen = set()
    dup = [x for x in titles if x and x in seen]
    checks.append(("titles.not_duplicated", not dup,
                   "零重复" if not dup else f"已存在: {dup}"))

    # 5) 图片齐备（同样只看还没发布的 slot —— 已发布的图会被 run_one_slot 清掉）
    missing = []
    for a in arts:
        if a.get("publish_status") in ("published", "scheduled"):
            continue
        for f in (a.get("inline_images") or []):
            if not os.path.exists(os.path.join(IMG_DIR, os.path.basename(str(f)))):
                missing.append(f"slot{a.get('slot')}:{f}")
    checks.append(("inline_images.present", not missing,
                   "全部存在" if not missing else f"缺失: {missing}"))

    return checks


def main():
    as_json = "--json" in sys.argv
    checks = check()
    bad = [c for c in checks if not c[1]]

    if as_json:
        print(json.dumps({
            "date": today(),
            "pass": not bad,
            "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
        }, ensure_ascii=False, indent=2))
        return 0 if not bad else 1

    print(f"[verify_today_batch] 今天 = {today()}")
    for name, ok, detail in checks:
        print(f"  {'[OK]  ' if ok else '[BAD] '}{name:<28} {detail}")
    if bad:
        print(f"RESULT: FAIL（{len(bad)} 项不通过）")
        return 1
    print("RESULT: PASS（当前批次确为今日生成，可放心发布）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
