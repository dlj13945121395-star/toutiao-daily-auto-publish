# run_on_logon.ps1 — 登录兜底：拉起 WorkBuddy -> 等 5s -> 上膛自动化（next_run_at 设为 now+45s 补跑）
# 由 Windows AtLogOn 计划任务调用。
#
# 换机器无需手改本文件：所有路径与 automation_id 均从 ../config.json 读取，
# 而 config.json 由 scripts/setup_new_machine.py 自动生成。
#
# 注意：每天有 2 个任务（生成器 11:30 + 发布 12:00，见 config.json 的 automation_ids）。
# 这里**只对 automation_id（slot 0 = 12:00 发布器）**上膛补跑 —— 若对 2 个全部上膛，
# 生成器未跑时 articles_batch.json 不存在，发布器会直接退出，但仍避免开机后连发。
$ErrorActionPreference = "Continue"

$log      = Join-Path $PSScriptRoot "run_on_logon.log"
$rearmLog = Join-Path $PSScriptRoot "rearm.log"

$skillRoot = Split-Path -Parent $PSScriptRoot
$cfgPath   = Join-Path $skillRoot "config.json"
if (-not (Test-Path $cfgPath)) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ERROR 未找到 config.json: $cfgPath" | Tee-Object -Append $log
    exit 1
}
$cfg          = Get-Content $cfgPath -Raw | ConvertFrom-Json
$workbuddy    = $cfg.workbuddy_exe
$python       = $cfg.python_exe
$automationId = $cfg.automation_id
$rearm        = Join-Path $PSScriptRoot "rearm_automation.py"

function Stamp($msg) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Tee-Object -Append $log }

Stamp "登录兜底触发 (automation=$automationId)"

# 1) 拉起 WorkBuddy（若已在运行则跳过）
if (Test-Path $workbuddy) {
    if (-not (Get-Process -Name "WorkBuddy" -ErrorAction SilentlyContinue)) {
        Stamp "启动 WorkBuddy"
        Start-Process $workbuddy
    } else {
        Stamp "WorkBuddy 已在运行"
    }
} else {
    Stamp "WARN WorkBuddy 路径不存在，跳过启动: $workbuddy"
}

# 2) 等 5s 让引擎就绪
Start-Sleep -Seconds 5

# 3) 上膛：把 next_run_at 设为 now+45s 触发补跑
Stamp "调用 rearm_automation.py --id $automationId"
& $python $rearm --id $automationId *>> $rearmLog
Stamp "完成"
