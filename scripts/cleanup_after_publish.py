#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cleanup_after_publish.py — wipe generated artifacts so nothing lingers on disk.

USER RULE (2026-09-09): "图片生成发布过后就自动删除，文章也是，不要在电脑上有留存"
  -> after an article is published, the AI-generated inline images and the produced
     Word file must be deleted automatically. No leftovers on the computer.

What gets deleted:
  1. Generated inline images   -> <skill>/images/article_inline/**   (the whole dir)
  2. Produced article docs     -> Desktop / OUT_DIR, matched by patterns
  3. Debug screenshots         -> <skill>/*.png   (diagnostic captures)
  4. Diagnostic json/txt/log   -> <skill>/*.(json|txt|log) except the KEEP list

What is ALWAYS kept (the workflow cannot run without them):
  config.json, toutiao_auth.json, article_post.json (the manuscript source —
  the docx can always be rebuilt from it), posts.json, published_topics.json(+.bak),
  cover_url_cache.json, last_run.json
  AND the cover assets  <skill>/images/post*.png  (no cover -> cannot publish)

Usage:
  python cleanup_after_publish.py            # dry run: list only
  python cleanup_after_publish.py --yes      # actually delete
"""
import os, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)

# ---- always keep (workflow-critical) ----
KEEP_FILES = {
    "config.json", "toutiao_auth.json", "article_post.json", "posts.json",
    "published_topics.json", "published_topics.json.bak",
    "cover_url_cache.json", "last_run.json",
    # 当日热门话题快照（11:30 生成器产出，兜底脚本 gen_wtt_from_article.py 与同日补发要用，保留）
    "hot_topics_today.json",
    # 评论回复幂等台账（2026-09-24 新增）：删了会导致同一评论被二次回复，务必保留
    "replied_comments.json",
    # 部署资产：换机器时要带走，被误删过一次（2026-09-10），务必保留
    "automation_config.json",
}
KEEP_EXTS = {".py", ".md", ".ps1"}          # source/config/docs live in scripts+SKILL.md
INLINE_IMG_DIR = os.path.join(SKILL_ROOT, "images", "article_inline")
COVER_GLOB = "post*.png"                     # cover assets -> keep

# docx patterns to wipe on Desktop and in the skill root
DOC_PATTERNS = ["*-带配图版-*.docx", "*article*.docx"]


def log(m):
    print(f"[cleanup] {m}", flush=True)


def collect():
    targets = []

    # 1. generated inline images (whole dir)
    if os.path.isdir(INLINE_IMG_DIR):
        for root, _dirs, files in os.walk(INLINE_IMG_DIR):
            for f in files:
                targets.append(os.path.join(root, f))

    # 2. produced article docs on Desktop + skill root
    search_dirs = [os.path.expanduser("~/Desktop"), SKILL_ROOT]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for pat in DOC_PATTERNS:
            for p in glob.glob(os.path.join(d, pat)):
                targets.append(p)

    # 3. debug screenshots in skill root
    for p in glob.glob(os.path.join(SKILL_ROOT, "*.png")):
        targets.append(p)

    # 4. diagnostic json/txt/log in skill root (minus keep list)
    for ext in ("*.json", "*.txt", "*.log"):
        for p in glob.glob(os.path.join(SKILL_ROOT, ext)):
            if os.path.basename(p) not in KEEP_FILES:
                targets.append(p)

    # de-dup + drop anything that must survive
    seen, out = set(), []
    for p in targets:
        p = os.path.abspath(p)
        if p in seen:
            continue
        seen.add(p)
        # never touch cover assets
        if os.path.dirname(p) == os.path.join(SKILL_ROOT, "images") and \
           glob.fnmatch.fnmatch(os.path.basename(p), COVER_GLOB):
            continue
        if os.path.splitext(p)[1].lower() in KEEP_EXTS:
            continue
        out.append(p)
    return out


def main():
    do_it = "--yes" in sys.argv
    targets = collect()

    if not targets:
        log("没有需要清理的留存，干净。")
        return 0

    total = 0
    for p in targets:
        if os.path.exists(p):
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
    log(f"待清理 {len(targets)} 个文件，约 {total/1024/1024:.1f} MB")
    for p in targets[:40]:
        log(f"   - {p}")
    if len(targets) > 40:
        log(f"   ... 其余 {len(targets)-40} 个")

    if not do_it:
        log("DRY RUN（未删除）。加 --yes 真正执行。")
        return 0

    n = 0
    for p in targets:
        try:
            os.remove(p)
            n += 1
        except Exception as e:
            log(f"   !! 删除失败 {p}: {str(e)[:80]}")

    # remove the now-empty inline image dir
    if os.path.isdir(INLINE_IMG_DIR):
        try:
            os.rmdir(INLINE_IMG_DIR)
            log(f"已删除目录 {INLINE_IMG_DIR}")
        except OSError:
            pass

    log(f"DONE 已删除 {n} 个留存文件。")
    log("保留：config/auth/稿件源 article_post.json/封面 post*.png（运行必需）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
