#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup_new_machine.py — 在另一台 Windows 机器上一键部署本技能。

解决的问题：原 DEPLOY.md / config.json / run_on_logon.ps1 里写死了
C:\\Users\\didi\\... 这类绝对路径，换机器就全废。本脚本自动探测并写回配置。

用法:
  python setup_new_machine.py                  # 探测环境 + 写 config.json（最常用）
  python setup_new_machine.py --login          # 上面 + 打开浏览器扫码登录
  python setup_new_machine.py --export         # 导出当前自动化配置 -> automation_config.json
  python setup_new_machine.py --register-task  # 注册 AtLogOn 登录兜底计划任务

换机器完整流程见 DEPLOY.md「换机器部署」一节。
"""
import argparse
import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(SKILL_ROOT, "config.json")


def log(m):
    print(f"[setup] {m}", flush=True)


def find_python():
    """优先级：托管 venv > 托管 versions > 系统 python。"""
    home = os.path.expanduser("~")
    cands = [
        os.path.join(home, ".workbuddy", "binaries", "python", "envs", "default", "Scripts", "python.exe"),
        os.path.join(home, ".workbuddy", "binaries", "python", "envs", "default", "bin", "python"),
    ]
    vdir = os.path.join(home, ".workbuddy", "binaries", "python", "versions")
    if os.path.isdir(vdir):
        for d in sorted(os.listdir(vdir), reverse=True):
            cands.append(os.path.join(vdir, d, "python.exe"))
    for w in ("python", "python3"):
        p = shutil.which(w)
        if p:
            cands.append(p)
    for c in cands:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return None


def find_workbuddy():
    local = os.environ.get("LOCALAPPDATA", "")
    cands = [
        os.path.join(local, "Programs", "WorkBuddy", "WorkBuddy.exe"),
        os.path.join(local, "WorkBuddy", "WorkBuddy.exe"),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs", "WorkBuddy", "WorkBuddy.exe"),
    ]
    for p in glob.glob(os.path.join(local, "*", "WorkBuddy.exe")):
        cands.append(p)
    for c in cands:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return None


def find_edge():
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(p):
            return p
    return None


def check_playwright(py):
    code = "import playwright, playwright.__main__"
    r = subprocess.run([py, "-c", code], capture_output=True, text=True)
    return r.returncode == 0


def step_detect_and_write():
    log("探测运行环境 ...")
    if not os.path.exists(CONFIG):
        log(f"ERROR 未找到 {CONFIG}（技能目录不完整）")
        return False
    cfg = json.load(open(CONFIG, "r", encoding="utf-8"))

    py = find_python()
    wb = find_workbuddy()
    edge = find_edge()

    log(f"  Python    : {py or '未找到'}")
    log(f"  WorkBuddy : {wb or '未找到'}")
    log(f"  Edge      : {edge or '未找到'}")

    changed = []
    if py and cfg.get("python_exe") != py:
        cfg["python_exe"] = py
        changed.append("python_exe")
    if wb and cfg.get("workbuddy_exe") != wb:
        cfg["workbuddy_exe"] = wb
        changed.append("workbuddy_exe")

    if changed:
        json.dump(cfg, open(CONFIG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        log(f"  已更新 config.json: {', '.join(changed)}")
    else:
        log("  config.json 路径已是本机值，无需改动")

    # 依赖检查
    if py:
        if check_playwright(py):
            log("  playwright: 已安装 ✓")
        else:
            log("  playwright: 未安装 ✗ —— 请执行：")
            log(f'    "{py}" -m pip install playwright')
            log(f'    "{py}" -m playwright install chromium')
    if not edge:
        log("  ⚠ 未检测到 Edge。脚本默认 channel=msedge，"
            "若无 Edge 需改脚本为 chromium 并先 playwright install chromium")

    # 登录态检查
    auth = os.path.join(SKILL_ROOT, cfg.get("auth_file", "toutiao_auth.json"))
    if os.path.exists(auth):
        log(f"  登录态: 已存在 {os.path.basename(auth)} ✓")
    else:
        log("  登录态: 缺失 ✗ —— 需执行 --login 扫码（登录态不能跨机器复制，必须重新扫）")
    return True


def step_login(cfg):
    py = cfg.get("python_exe") or find_python()
    script = os.path.join(HERE, "publish_draft.py")
    log("打开浏览器，请用手机头条扫码登录 ...")
    r = subprocess.run([py, script, "--login"], cwd=SKILL_ROOT)
    if r.returncode == 0:
        log("登录完成，toutiao_auth.json 已保存")
    else:
        log(f"登录流程返回码 {r.returncode}，请确认是否扫码成功")


def step_export():
    """从 workbuddy.db 读出当前（多个）自动化配置，导出成 json，方便新机器原样重建。

    每天 4 篇文章，分钟数不同，无法用单条 RRULE 配对，所以是 4 个独立任务。
    这里会把 config.json 里 automation_ids 全部导出，而不是只导单个 automation_id。
    """
    db = os.path.expanduser("~/.workbuddy/workbuddy.db")
    aids = []
    if os.path.exists(CONFIG):
        cfg = json.load(open(CONFIG, "r", encoding="utf-8"))
        # 优先用 automation_ids（4 个），回退到单个 automation_id
        aids = cfg.get("automation_ids") or [cfg.get("automation_id")]
    aids = [a for a in aids if a]
    if not aids:
        log("config.json 中未找到任何 automation_id / automation_ids")
        return
    if not os.path.exists(db):
        log(f"未找到 {db}，无法导出")
        return
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    tasks = []
    try:
        for aid in aids:
            cur.execute("SELECT id, name, prompt, schedule_type, rrule, valid_from, valid_until "
                        "FROM automations WHERE id=?", (aid,))
            row = cur.fetchone()
            if not row:
                log(f"  ⚠ 未找到 automation id={aid}，跳过")
                continue
            tasks.append({
                "id": row[0], "name": row[1], "prompt": row[2],
                "scheduleType": row[3], "rrule": row[4],
                "validFrom": row[5], "validUntil": row[6],
            })
    except sqlite3.OperationalError as e:
        log(f"读取 automations 失败: {e}")
        conn.close()
        return
    conn.close()
    if not tasks:
        log("没有可导出的自动化任务")
        return
    out = {
        "tasks": tasks,
        "note": "每天 4 篇，分钟数不同，故为 4 个独立 WEEKLY 任务。在新机器用 automation_update(tool)"
                "以这些参数逐个创建；每个创建后都要用 rearm_automation.py --at <ms> 直写 next_run_at"
                "（工具每次调用都会重置 next_run_at，不会自动重算到目标时间）。",
    }
    p = os.path.join(SKILL_ROOT, "automation_config.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"已导出 {len(tasks)} 个自动化配置 -> {p}")
    for t in tasks:
        log(f"  - {t['name']}  [{t['rrule']}]")


def step_register_task(cfg):
    ps = os.path.join(HERE, "run_on_logon.ps1")
    ps = os.path.abspath(ps)
    cmd = (
        "Import-Module ScheduledTasks; "
        f"Register-ScheduledTask -TaskName 'ToutiaoAutoOnLogon' "
        f"-Action (New-ScheduledTaskAction -Execute 'powershell.exe' "
        f"-Argument '-ExecutionPolicy Bypass -NoProfile -File \"{ps}\"') "
        f"-Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) "
        f"-Principal (New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive) "
        f"-Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        f"-DontStopIfGoingOnBatteries -StartWhenAvailable) -Force"
    )
    log("注册 AtLogOn 计划任务 ...")
    r = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True)
    if r.returncode == 0:
        log("已注册 ToutiaoAutoOnLogon ✓")
    else:
        log(f"注册失败（可能需管理员）: {r.stderr[:200] or r.stdout[:200]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="探测后接着扫码登录")
    ap.add_argument("--export", action="store_true", help="导出当前自动化配置")
    ap.add_argument("--register-task", action="store_true", help="注册登录兜底计划任务")
    args = ap.parse_args()

    log(f"技能目录: {SKILL_ROOT}")

    if not step_detect_and_write():
        sys.exit(1)

    cfg = json.load(open(CONFIG, "r", encoding="utf-8"))

    if args.export:
        step_export()
    if args.login:
        step_login(cfg)
    if args.register_task:
        step_register_task(cfg)

    if not (args.export or args.login or args.register_task):
        log("")
        log("下一步：")
        log("  1) 若登录态缺失：python setup_new_machine.py --login")
        log("  2) 建自动化任务：python setup_new_machine.py --export 拿到配置，"
            "在新机器让 agent 用 automation_update 创建")
        log("  3) 可选兜底：python setup_new_machine.py --register-task")


if __name__ == "__main__":
    main()
