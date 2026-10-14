#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本次生成的图重命名为 s{N}_{a,b,c}.png，并裁掉底部 172px 水印条。

两种模式，优先清单模式：

1) 清单模式（推荐，最稳）
   生成器落图后写一份清单 `images/article_inline/_rename_manifest.json`：
       { "文件名片段或完整文件名": "s0_a.png", "另一张": "s0_b.png", ... }
   脚本按清单精确重命名 —— 不依赖 mtime，也不怕并发生成撞秒（文件名只到秒，
   同秒的多张图会被覆盖/错位，这是 mtime 排序的根本不可靠处）。

2) 回退模式（无清单时）
   把「文件名含今天日期戳」的新增图片按 mtime 升序，依次命名为 s0_a/s0_b/... ，
   期望张数由 --expect 指定（默认 18 = 6 组 × 3 张）。⚠️ mtime 同秒会错位，
   只作为应急兜底。

无论哪种模式，只要处理后仍有「非 s 开头」的残留 png，就以非 0 退出（避免静默漏图）。

用法：
    python scripts/rename_today_images.py                 # 有清单走清单；无清单按 mtime，期望 18 张
    python scripts/rename_today_images.py --expect 18
    python scripts/rename_today_images.py --dry-run
"""
import argparse
import json
import os
import sys
from datetime import date

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMGDIR = os.path.join(ROOT, "images", "article_inline")
MANIFEST = os.path.join(IMGDIR, "_rename_manifest.json")
CROP_BOTTOM = 172
TODAY = date.today().isoformat()


def _is_target(name: str) -> bool:
    return name.startswith("s") and name.lower().endswith(".png")


def rename_and_crop(src: str, dst: str) -> bool:
    try:
        im = Image.open(src)
        w, h = im.size
        if h > CROP_BOTTOM + 100:
            im = im.crop((0, 0, w, h - CROP_BOTTOM))
        im.save(os.path.join(IMGDIR, dst), "PNG")
        os.remove(src)
        print(f"  OK {dst}  {w}x{h} -> {im.size[0]}x{im.size[1]}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  ERR {dst}: {e}")
        return False


def build_from_manifest(files):
    """返回 [(src_basename, dst)]；清单里的 key 可以是完整文件名或唯一片段。"""
    man = json.load(open(MANIFEST, encoding="utf-8"))
    pairs, used = [], set()
    for key, dst in man.items():
        if key in files and key not in used:
            pairs.append((key, dst))
            used.add(key)
            continue
        hits = [f for f in files if key in f and f not in used]
        if not hits:
            print(f"  !! 清单项未匹配: {dst}  (key={key})")
            continue
        if len(hits) > 1:
            print(f"  !! {dst} 多个候选，取第一个: {hits}")
        pairs.append((hits[0], dst))
        used.add(hits[0])
    return pairs


def build_from_mtime(files, expect):
    """按 mtime 升序配对 s{i}_{a,b,c}.png。"""
    ordered = sorted(files, key=lambda f: os.path.getmtime(os.path.join(IMGDIR, f)))
    letters = ["a", "b", "c"]
    pairs = []
    for i, f in enumerate(ordered):
        if i >= expect:
            break
        dst = f"s{i // 3}_{letters[i % 3]}.png"
        pairs.append((f, dst))
    if len(ordered) != expect:
        print(f"  !! 今日新增 {len(ordered)} 张，期望 {expect} 张")
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", type=int, default=18,
                    help="回退模式下期望的图片张数（默认 18 = 6 组 × 3 张）")
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(IMGDIR):
        print(f"FAIL: 目录不存在 {IMGDIR}")
        sys.exit(1)

    files = [f for f in os.listdir(IMGDIR)
             if f.lower().endswith(".png") and not _is_target(f)]
    today = [f for f in files if TODAY in f] or files
    print(f"待处理图片 {len(today)} 张（今日戳 {TODAY}）")

    if os.path.exists(args.manifest):
        print(f"模式：清单 {os.path.basename(args.manifest)}")
        pairs = build_from_manifest(today)
    else:
        print(f"模式：mtime 回退（无清单，expect={args.expect}）")
        pairs = build_from_mtime(today, args.expect)

    if not pairs:
        print("FAIL: 没有可处理的图片")
        sys.exit(1)

    if args.dry_run:
        for src, dst in pairs:
            print(f"  [dry] {src[:34]} -> {dst}")
        return

    for src, dst in pairs:
        rename_and_crop(os.path.join(IMGDIR, src), dst)

    left = [f for f in os.listdir(IMGDIR)
            if f.lower().endswith(".png") and not _is_target(f)]
    got = sorted(f for f in os.listdir(IMGDIR) if _is_target(f))
    print("残留未处理:", left if left else "无")
    print(f"最终 s 图 {len(got)} 张:", got)
    if left:
        print("FAIL: 仍有未处理的图片，请检查清单/数量（避免漏图导致发布缺图）")
        sys.exit(1)


if __name__ == "__main__":
    main()
