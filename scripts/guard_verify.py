# -*- coding: utf-8 -*-
"""兜底守护专用附加校验：标题去重 / 话题来源 / 图片存在性"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

ab = load("articles_batch.json")
wb = load("wtt_batch.json")
ht = load("hot_topics_today.json")

pool = set(ht.get("trending", [])) | set(ht.get("positioning", [])) | set(ht.get("fresh_topics_from_platform", []))

arts = ab["articles"]
print("date =", ht.get("date"))
print("articles =", len(arts), "slots =", sorted(a["slot"] for a in arts))
print("wtt =", len(wb), "slots =", sorted(w["slot"] for w in wb))

# 1) 标题长度 + 重复
titles = [a["title"] for a in arts]
for a in arts:
    t = a["title"]
    flag = "OK" if 2 <= len(t) <= 30 else "BAD"
    print(f"[title] slot={a['slot']} len={len(t)} {flag} {t}")
print("titles unique:", len(set(titles)) == len(titles))

# 2) 近 7 天重复
try:
    pt = load("published_topics.json")
    if isinstance(pt, dict):
        pt = pt.get("titles") or pt.get("topics") or list(pt.values())[0]
    seen = set()
    for x in pt:
        if isinstance(x, str):
            seen.add(x)
        elif isinstance(x, dict):
            for k in ("title", "topic", "name"):
                if x.get(k):
                    seen.add(x[k]); break
    dup = [t for t in titles if t in seen]
    print("published_topics count =", len(seen), "| dup with recent:", dup)
except Exception as e:
    print("published_topics check skipped:", e)

# 3) 话题来源
bad_tags = []
for a in arts:
    for tag in re.findall(r"#([^#\s]+)#", a["body"]):
        if f"#{tag}#" not in pool:
            bad_tags.append((a["slot"], tag))
for w in wb:
    for tag in re.findall(r"#([^#\s]+)#", w["body"]):
        if f"#{tag}#" not in pool:
            bad_tags.append(("wtt%d" % w["slot"], tag))
print("tags not in today's pool:", bad_tags if bad_tags else "NONE")

# 4) 图片存在性
missing = []
for a in arts:
    for im in a["inline_images"]:
        p = os.path.join("images", "article_inline", im)
        if not os.path.exists(p):
            missing.append(p)
for w in wb:
    for im in w["images"]:
        p = os.path.join("images", im)
        if not os.path.exists(p):
            missing.append(p)
print("missing images:", missing if missing else "NONE")

# 5) 状态
print("publish_status all null:", all(a.get("publish_status") is None for a in arts))
print("published_at all null:", all(a.get("published_at") is None for a in arts))

# 6) 前200字含「你」
for a in arts:
    print(f"[你] slot={a['slot']} in first200:", "你" in a["body"][:200])
