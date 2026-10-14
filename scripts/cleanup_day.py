#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cleanup_day.py — 当天全部组（文章 + 微头条）都发完后，清理本地产物。

安全闸（默认开启）：读 `articles_batch.json`，若还有 slot 的 `publish_status`
不在 (published, scheduled)，或任一 slot 的 `wtt_status` 为 failed，
则视为「今天没发完」→ **不清理**并返回 1（保留文件以便排查/重试）。

清理动作复用 `cleanup_after_publish.py`：
  删 articles_batch.json / wtt_batch.json / images/article_inline/** / 调试截图与诊断文件
  保留 config.json、toutiao_auth.json、published_topics.json（去重）、封面 post*.png、所有脚本

用法：
  python scripts/cleanup_day.py            # 检查 + dry run（只列清单）
  python scripts/cleanup_day.py --yes      # 检查通过后真删
  python scripts/cleanup_day.py --force --yes   # 跳过安全闸强删（慎用）
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
BATCH = os.path.join(SKILL_ROOT, "articles_batch.json")


def log(m):
    print(f"[cleanup_day] {m}", flush=True)


def main():
    force = "--force" in sys.argv
    yes = "--yes" in sys.argv

    if not force:
        if not os.path.exists(BATCH):
            log("无 articles_batch.json（可能已清理过）→ 继续执行总清理")
        else:
            try:
                arts = json.load(open(BATCH, encoding="utf-8")).get("articles", [])
            except Exception as e:
                log(f"⚠️ 读 articles_batch.json 失败（{str(e)[:50]}）→ 不清理")
                return 1
            if not arts:
                log("⚠️ articles_batch.json 里没有 articles → 不清理")
                return 1
            pending = [a.get("slot") for a in arts
                       if a.get("publish_status") not in ("published", "scheduled")]
            wtt_failed = [a.get("slot") for a in arts if a.get("wtt_status") == "failed"]
            if pending:
                log(f"⚠️ 尚有 slot 未发布完成: {pending} → 不清理（保留文件以便重试）")
                return 1
            if wtt_failed:
                log(f"⚠️ 微头条发布失败: {wtt_failed} → 不清理（保留文件以便排查）")
                return 1
            log(f"✅ {len(arts)} 组均已发布完成 slot={[a.get('slot') for a in arts]}，开始清理")

    cmd = [sys.executable, os.path.join(HERE, "cleanup_after_publish.py")]
    if yes:
        cmd.append("--yes")
    rc = subprocess.run(cmd, cwd=SKILL_ROOT).returncode
    return rc


if __name__ == "__main__":
    sys.exit(main())
