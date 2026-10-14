# -*- coding: utf-8 -*-
"""把 fetch_topics.py 的三批探测结果合并成一份「站内话题池」。
输出：topics_platform_<日期>.json —— 按讨论数排序，并标注截图里官方推荐话题的命中情况。
"""
import json
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRCS = ["topics_probe.json", "topics_probe2.json", "topics_probe3.json"]

# 老板截图里 App「创作邀请 → 话题」的 8 条官方推荐
SHOT = [
    "Token经济会成为下一个风口吗",
    "如果不缺钱，你还会工作吗",
    "Token最终会发展成什么样",
    "未来真人AI出演唱长剧会成为主流吗",
    "直击爱奇艺AI剧场创作营",
    "ai建议引发医疗事故谁担责",
    "第一批做AI漫剧的人财务自由了吗",
    "谷歌AI摘要正在“杀死”网页吗",
]

pool = {}
for s in SRCS:
    p = os.path.join(ROOT, s)
    if not os.path.exists(p):
        continue
    for kw, rows in json.load(open(p, encoding="utf-8")).items():
        for r in rows:
            t = r["topic"]
            if t not in pool or r["discuss"] > pool[t]["discuss"]:
                pool[t] = {"topic": t, "discuss": r["discuss"], "kw": kw}

items = sorted(pool.values(), key=lambda x: -x["discuss"])
bare = {k.strip("#"): k for k in pool}
matched = [f"#{t}# → {pool[bare[t]]['discuss']} 讨论" for t in SHOT if t in bare]
near = {t: [k for k in bare if t[:3] in k or k[:3] in t][:3] for t in SHOT if t not in bare}

out = {
    "date": date.today().isoformat(),
    "source": "头条微头条发布页话题联想（站内真实话题 + 讨论数）",
    "total": len(items),
    "screenshot_topics_exact_match": matched,
    "screenshot_topics_near": near,
    "topics": items,
}
dst = os.path.join(ROOT, f"topics_platform_{out['date']}.json")
json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print(f"合并 {len(items)} 条站内话题 → {os.path.basename(dst)}")
print("\n截图官方话题精确命中:", matched if matched else "无")
print("\n截图 8 条的近似话题:")
for t, ks in near.items():
    print(f"   · {t}  →  {ks}")
print("\n讨论数前 20 的站内话题:")
for it in items[:20]:
    print(f"   {it['discuss']:>5} 讨论  {it['topic']}")
print("\n截图 8 条里未在本次探测中出现的:")
for t in SHOT:
    if t not in pool:
        print("   ·", t)
