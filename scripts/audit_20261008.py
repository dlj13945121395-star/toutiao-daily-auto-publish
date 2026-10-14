#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-10-08 落盘后合规自查（比 check_batch 更细）。"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)

hot = json.load(open(os.path.join(ROOT, "hot_topics_today.json"), encoding="utf-8"))
allowed = set(hot["trending"]) | set(hot["positioning"]) | set(hot["fresh_topics_from_platform"])
ab = json.load(open(os.path.join(ROOT, "articles_batch.json"), encoding="utf-8"))
arts = ab["articles"]
wtt = json.load(open(os.path.join(ROOT, "wtt_batch.json"), encoding="utf-8"))

banned = ["首先", "其次", "综上所述", "值得注意的是", "毋庸置疑", "因此", "此外",
          "然而", "从某种程度上说", "众所周知", "**", "震惊", "绝了", "重磅"]
punct = ["：", "——", "「", "」", "“", "”"]
bad = []
warn = []

for a in arts:
    s = a["slot"]
    b = a["body"]
    if a["published_at"] is not None or a["publish_status"] is not None:
        bad.append(f"slot{s} 已带发布状态")
    if not (18 <= len(a["title"]) <= 30):
        bad.append(f"slot{s} 标题长度 {len(a['title'])}")
    if "你" not in b[:200]:
        bad.append(f"slot{s} 前200字无'你'")
    if not (1200 <= len(b) <= 2500):
        bad.append(f"slot{s} 正文字数 {len(b)}")
    for w in banned:
        if w in b:
            bad.append(f"slot{s} 禁词 {w}")
    for p in punct:
        if p in b:
            bad.append(f"slot{s} 禁标点 {p}")
    # 末尾话题段
    tail = b.strip().split(NL * 2)[-1]
    tags = [t for t in tail.split() if t.startswith("#")]
    if not (4 <= len(tags) <= 5):
        bad.append(f"slot{s} 末尾话题数 {len(tags)}（要求 4~5）")
    for t in tags:
        if t not in allowed:
            bad.append(f"slot{s} 非法话题 {t}")
    if "评论" not in b[-120:]:
        warn.append(f"slot{s} 结尾未见互动引导")
    # 图片存在
    for im in a["inline_images"]:
        p = os.path.join(ROOT, "images", "article_inline", im)
        if not os.path.exists(p):
            bad.append(f"slot{s} 缺图 {im}")
    print(f"slot{s} len={len(b)} title={len(a['title'])} tags={len(tags)} "
          f"imgs={len(a['inline_images'])}")

print("--- 微头条 ---")
for w in wtt:
    s = w["slot"]
    b = w["body"]
    if not (200 <= len(b) <= 500):
        bad.append(f"wtt slot{s} 字数 {len(b)}")
    for x in banned:
        if x in b:
            bad.append(f"wtt slot{s} 禁词 {x}")
    for p in punct:
        if p in b:
            bad.append(f"wtt slot{s} 禁标点 {p}")
    tail = b.strip().split(NL * 2)[-1]
    tags = [t for t in tail.split() if t.startswith("#")]
    if not (4 <= len(tags) <= 5):
        bad.append(f"wtt slot{s} 话题数 {len(tags)}（要求 4~5）")
    for t in tags:
        if t not in allowed:
            bad.append(f"wtt slot{s} 非法话题 {t}")
    if "主页" not in b:
        warn.append(f"wtt slot{s} 缺引流句")
    for im in w["images"]:
        p = os.path.join(ROOT, "images", im)
        if not os.path.exists(p):
            bad.append(f"wtt slot{s} 缺图 {im}")
    print(f"wtt slot{s} len={len(b)} tags={len(tags)} imgs={len(w['images'])}")

print()
print("BAD:", bad if bad else "无")
print("WARN:", warn if warn else "无")
print("AUDIT:", "PASS" if not bad else "FAIL")
