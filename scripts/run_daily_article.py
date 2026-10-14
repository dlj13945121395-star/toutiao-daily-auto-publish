#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_daily_article.py — 一篇文章 + 一条引流微头条 的一键流水线。

前置（由自动化 agent 完成）：
  1) 用 ContentCreator 专家 + humanizer / humanizer-zh 技能，写一篇去 AI 味的文章；
  2) 用 ImageGen 生成 2-3 张无文字插图，存到 images/article_inline/；
  3) 写 article_post.json（type=article, title, body(用\\n\\n分段),
     cover 用 post1/post2/post3.png 之一, inline_images=[3个图文件名],
     settings: first_release=头条首发, work_declare=引用AI）。

本脚本负责：发布文章(含正文插图+自动封面+两个声明) → 生成并发布引流微头条
  → 自检是否上线 → 清理本地生成的图与临时文件（已发到服务器，删本地无碍）。
全程不询问用户，直接发布。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(script, *args):
    cmd = [PY, os.path.join(HERE, script)] + list(args)
    print(f"\n>>> 运行 {script} {' '.join(args)}")
    return subprocess.run(cmd).returncode


def main():
    # 1) 发布文章（脚本会自动插图 + 复用自动封面 + 勾选两个声明）
    rc = run("publish_article_draft.py")
    if rc != 0:
        print("[FATAL] 文章发布失败，终止流水线（引流微头条也不发，避免只发半截）")
        sys.exit(rc)

    # 2) 生成引流微头条并直接发布（带图、勾选头条首发）
    run("gen_wtt_from_article.py")
    rc = run("publish_draft.py", "--publish", "--posts", "wtt_post.json", "--force")
    if rc != 0:
        print("[WARN] 引流微头条发布失败，继续自检与清理")

    # 3) 自检是否真的上线（读首页最近作品）
    run("verify_published.py")

    # 4) 清理本地生成的图与临时文件（已发到服务器，删本地无碍）
    run("cleanup_after_publish.py", "--yes")

    print("\n[DONE] 文章 + 引流微头条 流水线结束。")


if __name__ == "__main__":
    main()
