#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_one_slot.py — 11:00 生成 N 组内容后，按 slot 发布【文章 + 同组微头条】。

每个 slot = 1 篇文章 + 1 条微头条（微头条读根目录 wtt_batch.json 里同 slot 的条目）：

  python scripts/run_one_slot.py --slot 0   # 12:00（先发微头条，再发文章）
  python scripts/run_one_slot.py --slot 1   # 14:00
  python scripts/run_one_slot.py --slot 2   # 15:00
  python scripts/run_one_slot.py --slot 5   # 16:00
  python scripts/run_one_slot.py --slot 4   # 17:00
  python scripts/run_one_slot.py --slot 3   # 18:00

⚠️ 用户指定顺序：**先发微头条，再发文章**。slot 编号与时间点无关，以各发布任务为准。

微头条编辑器只有「存草稿 / 发布」，没有定时发布，所以微头条只能在同一时刻立即发；
文章同理走立即发布（`--schedule` 的定时模式会跳过同组微头条）。

用法:
  python scripts/run_one_slot.py --slot 0                     # 立即发布文章 + 微头条
  python scripts/run_one_slot.py --slot 1 --schedule 14:00    # 仅定时排文章（跳过微头条）
  python scripts/run_one_slot.py --slot 2 --dry-run           # 只写 payload 不发布
  python scripts/run_one_slot.py --slot 3 --skip-wtt          # 只发文章，不发微头条

隔日批次硬闸（2026-10-12 新增）：
  发布前校验「文章批次的 generated_at 日期」与「同目录 wtt_batch.json 的 mtime 日期」
  是否都等于今天；不满足则**拒绝发布并 exit 3**，杜绝「今天发出隔日旧内容」。
  确认要人工补发历史批次时，显式加 `--allow-stale` 放行。

清理策略：只删本 slot 的图（s{N}_*.png）与本 slot 临时文件，
不动其他 slot、封面图、articles_batch.json、wtt_batch.json、published_topics.json。
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH = os.path.join(SKILL_ROOT, "articles_batch.json")
WTT_BATCH = os.path.join(SKILL_ROOT, "wtt_batch.json")
ARTICLE_POST = os.path.join(SKILL_ROOT, "article_post.json")
SCRIPTS = os.path.join(SKILL_ROOT, "scripts")

TEMP_FILES = [
    "article_post.json", "wtt_post.json", "article_capture.json",
    "article_published.png", "article_scheduled.png",
]


def log(m):
    print(f"[run_one_slot] {m}", flush=True)


def resolve_schedule(raw):
    """'HH:MM' → 补全为今天 'YYYY-MM-DD HH:MM'；已是完整格式则原样返回。"""
    if not raw:
        return None
    raw = str(raw).strip()
    if len(raw) == 5 and raw[2] == ":":
        return f"{datetime.date.today().isoformat()} {raw}"
    return raw


def find_entry(batch, slot):
    for a in batch.get("articles", []):
        if a.get("slot") == slot:
            return a
    return None


def cleanup_slot(slot):
    """只清本 slot 的图（s{N}_*.png），不动其他 slot 与封面。"""
    d = os.path.join(SKILL_ROOT, "images", "article_inline")
    if os.path.isdir(d):
        prefix = f"s{slot}_"
        n = 0
        for f in os.listdir(d):
            if f.startswith(prefix) and f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                try:
                    os.remove(os.path.join(d, f))
                    n += 1
                except Exception:
                    pass
        if n:
            log(f"  删 slot {slot} 的 {n} 张本地图（已上传头条，删本地无碍）")
    for tmp in TEMP_FILES:
        p = os.path.join(SKILL_ROOT, tmp)
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


def publish_linked_wtt(slot, wtt_path=None):
    """发布与 slot 对应的微头条（默认读根 wtt_batch.json）。

    微头条编辑器只有「存草稿 / 发布」，没有定时发布，所以由本机在排定时刻当场发布。
    返回 ok: bool。软失败：文件缺失 / 无对应条目时不算失败（文章已发成功）。
    """
    wtt_path = wtt_path or WTT_BATCH
    if not os.path.exists(wtt_path):
        log(f"  微头条: 无 {os.path.basename(wtt_path)}，跳过")
        return True
    try:
        batch = json.load(open(wtt_path, encoding="utf-8"))
    except Exception as e:
        log(f"  微头条: 读 wtt_batch.json 失败 {str(e)[:60]}")
        return False
    post = None
    for p in batch:
        if p.get("slot") == slot:
            post = p
            break
    if post is None:
        log(f"  微头条: wtt_batch.json 无 slot={slot}，跳过")
        return True
    tmp = os.path.join(SKILL_ROOT, f"wtt_slot{slot}.json")
    json.dump([{"body": post.get("body", ""), "images": post.get("images") or []}],
              open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"  发布微头条 slot {slot}（{len(post.get('body', ''))} 字，{len(post.get('images') or [])} 图）")
    cmd = [sys.executable, os.path.join(SCRIPTS, "publish_draft.py"),
           "--publish", "--posts", tmp, "--force"]
    rc = subprocess.run(cmd, cwd=SKILL_ROOT).returncode
    try:
        os.remove(tmp)
    except Exception:
        pass
    if rc != 0:
        log(f"  ⚠️ 微头条发布失败 rc={rc}（文章已发出，不重试整组）")
        return False
    log(f"  ok 微头条已发布（slot {slot}）")
    return True


def stale_guard(article_batch_path, wtt_batch_path, allow_stale):
    """隔日批次硬闸：保证「今天发布的是今日生成的」。

    规则：
      1) 文章批次的 generated_at 日期必须 == 今天；
      2) 微头条批次文件（跟随文章批次同目录）的最后修改日期必须 == 今天。
    allow_stale=True（人工补发历史批次）时只告警、不拦截。

    返回 (problems: list[str], allowed: bool)
    """
    today = datetime.date.today().isoformat()
    problems = []

    # 1) 文章批次 generated_at
    try:
        ab = json.load(open(article_batch_path, encoding="utf-8"))
        gen = ab.get("generated_at", "") if isinstance(ab, dict) else ""
    except Exception as e:
        gen = ""
        problems.append(f"读文章批次失败: {str(e)[:50]}")
    if not gen:
        problems.append(f"{os.path.basename(article_batch_path)} 缺少 generated_at 字段")
    elif not str(gen).startswith(today):
        problems.append(f"文章批次生成于 {str(gen)[:10]}，不是今天({today})")

    # 2) 微头条批次文件 mtime
    if os.path.exists(wtt_batch_path):
        m = datetime.date.fromtimestamp(os.path.getmtime(wtt_batch_path)).isoformat()
        if m != today:
            problems.append(f"{os.path.basename(wtt_batch_path)} 最后修改于 {m}，不是今天({today})")
    else:
        problems.append(f"{os.path.basename(wtt_batch_path)} 不存在")

    return problems, (allow_stale or not problems)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=int, required=True, help="0=12:00立即 / 1,2,3=定时")
    ap.add_argument("--schedule", default=None,
                    help="定时发布时间 'HH:MM' 或 'YYYY-MM-DD HH:MM'；不给则立即发布")
    ap.add_argument("--batch", default=BATCH, help="批次文件路径")
    ap.add_argument("--dry-run", action="store_true", help="只写 payload，不发布")
    ap.add_argument("--skip-cleanup", action="store_true")
    ap.add_argument("--skip-wtt", action="store_true", help="只发文章，不发同组微头条")
    ap.add_argument("--allow-stale", action="store_true",
                    help="放行非今日批次（仅供人工补发历史批次时显式使用）")
    args = ap.parse_args()

    if not os.path.exists(args.batch):
        log(f"❌ {args.batch} 不存在；今天 11:00 还没生成批次，或生成失败。")
        sys.exit(2)

    batch = json.load(open(args.batch, encoding="utf-8"))
    entry = find_entry(batch, args.slot)
    if not entry:
        log(f"❌ slot={args.slot} 在批次中找不到")
        sys.exit(2)

    # 仅当已成功（scheduled/published）才跳过；failed 允许补一次重试，避免重复提交同样被拦死
    if entry.get("publish_status") in ("scheduled", "published") and not args.dry_run:
        log(f"slot {args.slot} 已于 {entry.get('published_at')} 处理过（{entry.get('publish_status')}），跳过")
        return

    # 「微头条批次」跟随文章批次所在目录：根批次→根 wtt_batch.json；
    #  显式 --batch 指向历史批次→用同目录的 wtt_batch.json，避免张冠李戴
    wtt_path = os.path.join(os.path.dirname(os.path.abspath(args.batch)), "wtt_batch.json")

    # ===== 隔日批次硬闸：今天只发今天生成的 =====
    problems, allowed = stale_guard(args.batch, wtt_path, args.allow_stale)
    for pb in problems:
        log(f"⚠️ 批次新鲜度: {pb}")
    if not allowed:
        log("❌ 拒绝发布：当前批次不是今日生成（防止今天发出隔日旧内容）。")
        log("   确需人工补发历史批次时，请显式加 --allow-stale。")
        sys.exit(3)
    if problems and args.allow_stale:
        log("⚠️ 已用 --allow-stale 放行非今日批次（人工补发模式）")

    # 命令行 --schedule 优先，其次条目自带的 schedule_time
    sched = resolve_schedule(args.schedule or entry.get("schedule_time"))
    mode = f"定时 {sched}" if sched else "立即发布"
    log(f"slot {args.slot} [{mode}] -> {entry['title'][:40]}")

    post = {
        "type": "article",
        "title": entry["title"],
        "body": entry["body"],
        "cover": entry.get("cover"),
        "inline_images": entry.get("inline_images", []) or [],
        "settings": entry.get("settings") or {
            "first_release": "头条首发",
            "work_declare": "引用AI",
        },
        # 溯源戳：记录稿件来自哪个批次的 generated_at（供事后核对是否隔日内容）
        "source_generated_at": batch.get("generated_at"),
    }
    if sched:
        post["schedule_time"] = sched
    json.dump(post, open(ARTICLE_POST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"  写 article_post.json（{len(entry['body'])} 字，{len(post['inline_images'])} 图）")

    if args.dry_run:
        log("[DRY RUN] 已写 payload，未发布")
        return

    # ===== 用户指定顺序：先发微头条，再发文章 =====
    if not sched and not args.skip_wtt:
        wtt_ok = publish_linked_wtt(args.slot, wtt_path)
        entry["wtt_status"] = "published" if wtt_ok else "failed"
        json.dump(batch, open(args.batch, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    elif sched:
        log("  定时模式：微头条没有定时发布功能，已跳过同组微头条")

    # 再发文章
    cmd = [sys.executable, os.path.join(SCRIPTS, "publish_article_draft.py"), ARTICLE_POST]
    log("$ " + " ".join(cmd))
    rc = subprocess.run(cmd, cwd=SKILL_ROOT).returncode

    entry["published_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    if rc != 0:
        entry["publish_status"] = "failed"
        entry["error"] = f"rc={rc}"
        json.dump(batch, open(args.batch, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        log(f"❌ 文章发布失败 rc={rc}；已标记，避免重复提交")
        sys.exit(1)

    entry["publish_status"] = "scheduled" if sched else "published"
    if sched:
        entry["scheduled_for"] = sched
    json.dump(batch, open(args.batch, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if not args.skip_cleanup:
        cleanup_slot(args.slot)

    log(f"[DONE] slot {args.slot} " + (f"已排程 → {sched}" if sched else "已发布上线"))


if __name__ == "__main__":
    main()
