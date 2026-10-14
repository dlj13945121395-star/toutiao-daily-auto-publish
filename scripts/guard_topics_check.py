# -*- coding: utf-8 -*-
"""guard: 末段话题数 / 全文 # 数 / 微头条话题数 / 图片清单 / 禁标点 一次性核查"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

pool = json.load(open("hot_topics_today.json", encoding="utf-8"))
pool_tags = set(pool.get("trending", []) + pool.get("positioning", []) + pool.get("fresh_topics_from_platform", []))

arts = json.load(open("articles_batch.json", encoding="utf-8"))["articles"]
wtt = json.load(open("wtt_batch.json", encoding="utf-8"))

BAD = []
WARN = []

BAN = ["：", "——", "「", "」", "“", "”"]

print("=== 文章末段话题 ===")
for a in arts:
    body = a.get("body", "")
    paras = [p for p in body.split("\n") if p.strip()]
    last = paras[-1] if paras else ""
    n_last = len(re.findall(r"#[^#\n]+#", last))
    n_all = body.count("#")
    ok = 4 <= n_last <= 5
    if not ok:
        BAD.append("slot%s 末段话题数=%s (要求 4~5)" % (a["slot"], n_last))
    if n_all < 1:
        BAD.append("slot%s 全文 # 数=0" % a["slot"])
    print("slot%s 末段话题=%s 全文#=%s imgs=%s status=%s at=%s | %s" % (
        a["slot"], n_last, n_all, len(a.get("inline_images", [])),
        a.get("publish_status"), a.get("published_at"), last[:70]))

print("=== 微头条话题 ===")
for w in wtt:
    body = w.get("body", "")
    paras = [p for p in body.split("\n") if p.strip()]
    last = paras[-1] if paras else ""
    n_last = len(re.findall(r"#[^#\n]+#", last))
    if not (4 <= n_last <= 5):
        WARN.append("wtt slot%s 话题数=%s (规范 4~5)" % (w.get("slot"), n_last))
    print("wtt slot%s 话题数=%s len=%s imgs=%s" % (w.get("slot"), n_last, len(body), w.get("images")))

print("=== 话题归属今日池 ===")
for a in arts:
    for t in re.findall(r"#[^#\n]+#", a.get("body", "")):
        if t not in pool_tags:
            BAD.append("slot%s tag 不在今日池: %s" % (a["slot"], t))
for w in wtt:
    for t in re.findall(r"#[^#\n]+#", w.get("body", "")):
        if t not in pool_tags:
            BAD.append("wtt slot%s tag 不在今日池: %s" % (w.get("slot"), t))
print("tag 池校验完成")

# ---- 可点性预警（2026-10-14 新增）----
# 「在池里」≠「点得开」：merge_topics.py 的 SHOT 基线（App 创作邀请口号式标题）
# 与历史遗留话题可能混入 hot_topics_today.json，但它们不在编辑器联想索引里，
# 发布时走选择器会搜不到候选 → 退化成不可点的纯文本。
# 只有今日 topics_probe*.json 真实联想抓到的 tag 才保险。
probe_tags = set()
for pf in ("topics_probe.json", "topics_probe2.json", "topics_probe3.json"):
    if os.path.exists(pf):
        try:
            for _kw, rows in json.load(open(pf, encoding="utf-8")).items():
                for r in rows:
                    probe_tags.add(r["topic"])
        except Exception:
            pass
if probe_tags:
    print("=== 话题可点性（对照今日联想抓取 %d 条）===" % len(probe_tags))
    _seen_warn = set()
    for a in arts:
        for t in re.findall(r"#[^#\n]+#", a.get("body", "")):
            if t not in probe_tags and t not in _seen_warn:
                _seen_warn.add(t)
                WARN.append("文章话题疑似不可点(不在今日联想结果): %s" % t)
    for w in wtt:
        for t in re.findall(r"#[^#\n]+#", w.get("body", "")):
            if t not in probe_tags and t not in _seen_warn:
                _seen_warn.add(t)
                WARN.append("微头条话题疑似不可点(不在今日联想结果): %s" % t)
    print("可点性预警 %d 条" % len(_seen_warn))

print("=== 禁标点 & 加粗 ===")
for a in arts:
    b = a.get("body", "")
    for ch in BAN:
        if ch in b:
            BAD.append("slot%s 含禁标点 %s" % (a["slot"], ch))
    if "**" in b:
        BAD.append("slot%s 含 **" % a["slot"])
print("标点校验完成")

print("=== 图片清单 ===")
d = os.path.join("images", "article_inline")
if os.path.isdir(d):
    pngs = sorted([f for f in os.listdir(d) if f.lower().endswith(".png")])
    expect = ["s%d_%s.png" % (i, c) for i in range(6) for c in "abc"]
    print("png 数量=%s" % len(pngs))
    missing = [e for e in expect if e not in pngs]
    extra = [p for p in pngs if p not in expect]
    if missing:
        BAD.append("缺图: %s" % missing)
    if extra:
        WARN.append("多余图: %s" % extra)
    print("缺图=%s 多余=%s" % (missing or "无", extra or "无"))
else:
    BAD.append("目录不存在: %s" % d)

print()
print("BAD:", BAD or "无")
print("WARN:", WARN or "无")
print("GUARD:", "PASS" if not BAD else "FAIL")
