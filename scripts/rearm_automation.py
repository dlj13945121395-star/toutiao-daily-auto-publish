#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rearm_automation.py — 把 workbuddy.db 中指定自动化的 next_run_at 直写拉回，触发补跑。

背景: WorkBuddy 的 automation_update 改完 recurring 排程后，next_run_at 仍沿用旧值
（曾卡 2030 永不触发）。本脚本直接 UPDATE automations 表拉回触发时间。

用法:
    python rearm_automation.py --id <AUTOMATION_ID>            # 设为 now+45s（登录兜底补跑）
    python rearm_automation.py --id <AUTOMATION_ID> --next9    # 设为次日 09:00 本地（改完排程后手动拉回）

仅更新 next_run_at 字段，不改动其他配置。
"""
import argparse
import os
import sqlite3
import sys
import time
import datetime

DB_PATH = os.path.expanduser("~/.workbuddy/workbuddy.db")


def now_ms():
    return int(time.time() * 1000)


def next_9am_ms():
    now = datetime.datetime.now()
    nxt = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += datetime.timedelta(days=1)
    return int(nxt.timestamp() * 1000)


def rearm(aid, target_ms):
    if not os.path.exists(DB_PATH):
        print("ERROR: 未找到", DB_PATH)
        return False
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, next_run_at FROM automations WHERE id=?", (aid,))
    row = cur.fetchone()
    if not row:
        print("ERROR: 未找到自动化 id =", aid, "| 请在 WorkBuddy 自动化列表确认 ID")
        conn.close()
        return False
    print(f"更新前 next_run_at={row[1]} -> {target_ms}")
    cur.execute("UPDATE automations SET next_run_at=? WHERE id=?", (target_ms, aid))
    conn.commit()
    conn.close()
    print("OK 已直写 next_run_at")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="automation_update 得到的自动化 ID")
    ap.add_argument("--next9", action="store_true", help="设为次日 09:00 本地时间；否则 now+45s")
    ap.add_argument("--at", type=int, default=None,
                    help="直接指定 next_run_at（epoch 毫秒），优先级最高")
    args = ap.parse_args()
    if args.at is not None:
        target = args.at
    elif args.next9:
        target = next_9am_ms()
    else:
        target = now_ms() + 45000
    ok = rearm(args.id, target)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
