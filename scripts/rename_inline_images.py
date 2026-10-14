#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 article_inline 里新生成的图片按时间顺序重命名为 s{N}_x.png，并裁掉底部水印条。

用法: python rename_inline_images.py
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INLINE = os.path.join(ROOT, "images", "article_inline")
CROP_BOTTOM = 172  # 右下角 AI 生成水印条高度

SLOTS = [f"s{n}_{c}" for n in range(4) for c in ("a", "b", "c")]


def main():
    if not os.path.isdir(INLINE):
        print("NO_INLINE_DIR")
        return 1

    # 只挑今天新生成的、非目标命名、非 post*.png 的文件
    files = []
    for name in os.listdir(INLINE):
        low = name.lower()
        if not low.endswith(".png"):
            continue
        if low.startswith(("s0_", "s1_", "s2_", "s3_")):
            continue
        if low.startswith("post"):
            continue
        path = os.path.join(INLINE, name)
        files.append((os.path.getmtime(path), path, name))

    files.sort(key=lambda x: x[0])

    if len(files) < len(SLOTS):
        print(f"NOT_ENOUGH_IMAGES: got {len(files)}, need {len(SLOTS)}")
        for _, _, n in files:
            print("  ", n)
        return 2

    mapping = list(zip(SLOTS, files[: len(SLOTS)]))
    for slot, (_, src, name) in mapping:
        dst = os.path.join(INLINE, slot + ".png")
        with Image.open(src) as im:
            im = im.convert("RGB")
            w, h = im.size
            im = im.crop((0, 0, w, max(1, h - CROP_BOTTOM)))
            im.save(dst, "PNG")
        os.remove(src)
        print(f"{slot}.png  <-  {name}")

    # 清理多余的孤儿文件（超出 12 张的）
    for _, src, name in files[len(SLOTS):]:
        os.remove(src)
        print(f"remove orphan: {name}")

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
