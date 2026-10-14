#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_batch.py — 校验当天批次的正文字数硬要求（用户 2026-09-14 指定，2026-09-15 更新为区间）。

  articles_batch.json  每篇文章 body 在 1200~2500 字符之间
  wtt_batch.json       每条微头条 body 在 200~500 字符之间

全部达标 → 返回码 0（打印 RESULT: PASS）；有任一不达标 → 返回码 1。
生成器落盘后应先跑本脚本，FAIL 就必须重写对应内容再跑，直到 PASS。
"""
import json
import os
import sys

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))
ART_MIN = 1200  # 文章：1200 字符下限
ART_MAX = 2500  # 文章：2500 字符上限
WTT_MIN = 200   # 微头条：200 字符下限
WTT_MAX = 500   # 微头条：500 字符上限


def main():
    ok = True
    ap = os.path.join(SKILL_ROOT, "articles_batch.json")
    wp = os.path.join(SKILL_ROOT, "wtt_batch.json")

    if os.path.exists(ap):
        data = json.load(open(ap, encoding="utf-8"))
        arts = data.get("articles", []) if isinstance(data, dict) else data
        if not arts:
            print("FAIL: articles_batch.json 里没有 articles")
            ok = False
        for a in arts:
            n = len((a.get("body") or "").strip())
            good = ART_MIN <= n <= ART_MAX
            ok = ok and good
            print(f"[article] slot={a.get('slot')} {n} 字符 (要求 {ART_MIN}~{ART_MAX}) "
                  f"[{'OK' if good else 'FAIL'}] {str(a.get('title',''))[:24]}")
    else:
        print("FAIL: 缺少 articles_batch.json")
        ok = False

    if os.path.exists(wp):
        data = json.load(open(wp, encoding="utf-8"))
        posts = data.get("posts", []) if isinstance(data, dict) else data
        if not posts:
            print("FAIL: wtt_batch.json 里没有条目")
            ok = False
        for w in posts:
            n = len((w.get("body") or "").strip())
            good = WTT_MIN <= n <= WTT_MAX
            ok = ok and good
            print(f"[wtt]     slot={w.get('slot')} {n} 字符 (要求 {WTT_MIN}~{WTT_MAX}) "
                  f"[{'OK' if good else 'FAIL'}]")
    else:
        print("FAIL: 缺少 wtt_batch.json")
        ok = False

    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
