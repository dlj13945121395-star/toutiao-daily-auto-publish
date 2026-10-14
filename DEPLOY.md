# DEPLOY.md · 部署 / 换机器 指南

配套 `SKILL.md`、`scripts/`、`references/`。目标：**换台 Windows 机器也能全自动发文，全程不用人工确认。**

---

## 一、换机器部署（最常用，6 步）

### 1. 复制技能目录

把整个 `toutiao-weitoutiao-auto-publish/` 拷到新机器的
`C:\Users\<新用户名>\.workbuddy\skills\` 下。

**必须带走的**

| 文件/目录 | 说明 |
|---|---|
| `SKILL.md` | 技能说明与规范 |
| `config.json` | 配置（路径会在第 3 步自动重写） |
| `scripts/` | 全部脚本 |
| `references/` | 写作规范 + 内容策略 |
| `images/post*.png` | **封面素材，没有它发布必失败** |
| `automation_config.json` | 自动化任务配置（第 4 步用） |

**不要带 / 必须重新生成的**

| 文件 | 原因 |
|---|---|
| `toutiao_auth.json` | **登录态不能跨机器复制**，必须在新机器重新扫码 |
| `scripts/__pycache__/` | 字节码，可弃 |
| 各种 `*.png` 调试截图、`verify_*.json` | 临时产物 |

### 2. 装 Python 依赖

```powershell
& "<托管python>" -m pip install playwright
& "<托管python>" -m playwright install chromium
```

> 若用 WorkBuddy 托管运行时，通常已装好。第 3 步会检查并提示。

### 3. 跑一键部署脚本（自动消除硬编码路径）

```powershell
& "<python>" "<技能目录>\scripts\setup_new_machine.py"
```

它会：
- 探测 **Python / WorkBuddy / Edge** 的**本机真实路径**，写回 `config.json`
- 检查 `playwright` 是否安装，缺则打印安装命令
- 检查 `toutiao_auth.json` 是否存在

### 4. 登录（登录态必须重新扫）

```powershell
& "<python>" "<技能目录>\scripts\setup_new_machine.py" --login
```

→ 弹 Edge → 手机头条扫码 → 自动保存 `toutiao_auth.json`。

### 5. 建自动化任务（2 个）

每天 **4 篇文章**，但只需 **2 个独立 automation**（已合并原本分散的发布时点）：

- **① 生成器（11:30，工作日）**：只生成内容——生成 4 篇 + 12 张图 → 写 `articles_batch.json`（slot1/2/3 含 schedule_time 14/18/22:00）。**不排程、不发布**。
- **② 发布器（12:00，工作日）**：先给 slot1/2/3 在头条号内排 14:00/18:00/22:00 定时发布（到点自动发），再 `run_one_slot.py --slot 0` 立即发布第 1 篇。

`automation_config.json` 现在导出的是 `tasks` 数组（每个元素含 `id/name/prompt/rrule/
scheduleType/validFrom/validUntil`）。让 agent 用 `automation_update` **逐个创建这 2 个**，
参数照抄每个 `tasks[i]`。

建完**必须**做两件事（每个任务都要）：

1. 把 2 个新返回的 `automation_id` 全部写进 `config.json` 的 **`automation_ids`** 数组
   （`automation_id` 单数保留为 ② 的 id，供登录兜底 `run_on_logon.ps1` 使用）。
2. **逐个手动直写 `next_run_at`**（工具每次调用都会重置它，且不会重算到目标时间）：
   ```powershell
   & "<python>" "<技能目录>\scripts\rearm_automation.py" --id <新ID> --at <目标时间的epoch毫秒>
   ```
   两个时间点对应的 epoch 毫秒（以 2026-09-10 为例）：
   - 11:30 → `--at 1789011000000`（①）
   - 12:00 → `--at 1789012800000`（②）

> 创建后务必直接读 `workbuddy.db` 的 `next_run_at` 核对——工具返回值可能和实际写库的
> 不一样，引擎还会周期性覆盖。

### 6.（可选）注册登录兜底

```powershell
& "<python>" "<技能目录>\scripts\setup_new_machine.py" --register-task
```

错过定时点会在下次登录时补跑。`run_on_logon.ps1` 已从 `config.json` 读取路径与 automation_id，**换机器不用改它**。

---

## 二、验证清单

- [ ] `setup_new_machine.py` 探测全部命中（Python / WorkBuddy / Edge）
- [ ] `toutiao_auth.json` 已生成
- [ ] `python scripts/publish_draft.py --dry-run` 能跑通
- [ ] 自动化任务的 `next_run_at` 已直写为预期时间
- [ ] 到点后 `verify_published.py` 自检返回「全部发布成功」

---

## 三、每日运行（无需人工）

- 工作日 **11:30 生成器**触发一次（生成 4 篇 + 头条内排 14/18/22:00 定时发布），**12:00 发布器**触发一次（立即发第 1 篇），共 **4 篇文章/天**（周末不跑）。
- 11:30 流程：生成 4 篇 → 配 12 图 → 写 `articles_batch.json`（只产出内容，不发布）。12:00 流程：先给第 2/3/4 篇在头条号内排 14/18/22:00 定时发布（到点自动发），再 `run_one_slot.py --slot 0` 立即发布第 1 篇。
- **不需要人工确认**：内容、发布、核验、清理全自动。
- 微头条：头条编辑器默认「同时发布微头条」开关自带，无需单独渠道（此前独立微头条任务已弃用）。

---

## 四、关键路径（均自动探测，不要手写）

| 项 | 位置 |
|---|---|
| 技能目录 | `~/.workbuddy/skills/toutiao-weitoutiao-auto-publish/` |
| 配置 | 同目录 `config.json`（`python_exe` / `workbuddy_exe` / `automation_id`(② 发布器) / `automation_ids`(2个) 由 setup 脚本写） |
| 登录态 | 同目录 `toutiao_auth.json` |
| 自动化 DB | `~/.workbuddy/workbuddy.db`（automations 表） |

---

## 五、踩过的坑（换机器时尤其注意）

1. **`automation_update` 每次调用都会重置 `next_run_at`**（不只是「不重算」）→ 改排程、
   改名、改状态后都要用 `rearm_automation.py --at` 直写 DB；且工具返回值可能与实际库值不一致，
   必须直接读 `workbuddy.db` 核对。2 个任务每个都要单独 rearm。
2. **登录态不能跨机器复制** → 新机器必须重新 `--login` 扫码。
3. **封面 `images/post*.png` 必须一起拷** → 缺失则 `pgc_feed_covers` 为空，发布失败。
4. **PowerShell 计划任务需行内注册** → `schtasks /TR` 含 powershell 会被安全策略拒。
5. **`:has_text`（下划线）是无效 CSS** → 勾选复选框必须用 `:has-text`，否则静默失败。
6. **确认发布 = 真发布**，本号没有可用的「存草稿」通道（autosave 必 7050）。
7. **别把首页当草稿箱**：`/profile_v4/index` 是首页；草稿箱是 `/profile_v4/manage/draft`。
