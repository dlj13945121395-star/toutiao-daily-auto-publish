# writing-spec.md · 微头条发布操作说明书

> 面向「执行层」：发布页怎么点、图怎么传、哪些信号算成功、出了错怎么查。
> 战略与钩子库见 `content-strategy.md`。

---

## 1. 定位与边界

- 本技能只做**存草稿**：填稿 → 传图 → 勾头条首发 → 存草稿箱。
- **不自动对外发布**。发布由你手机审核（裁剪右下角 AI 水印）后手动点。

> ⚠️ **复核红线（来自实战踩坑）**：AI / 免费模型（如混元）**可能谎报任务完成**——没写完、没插图、图比例奇怪时也会说"已完成"。本脚本只保证"存草稿动作执行了"，**不保证内容质量与配图比例正确**。每天必须去手机草稿箱**肉眼复核**：正文是否完整、配图是否插入且比例正常、是否勾上头条首发。发现不对就重跑或手改，不要盲信"成功"二字。
- 正文体裁：微头条（短内容，数百字，无标题）。发布页 `https://mp.toutiao.com/profile_v4/weitoutiao/publish`。
- **账号定位：AI（普通人用 AI 搞钱 / 提效 / 避坑）**（2026-09-01 由「人情世故 + 真实故事」改为 AI）。内容以普通人视角讲 AI 工具的真实玩法、踩过的坑、能落地的搞钱/提效思路，说人话、给方法、不空谈概念；人味由真人审核把关。生成链路见 SKILL.md「内容生成工作流」。

## 2. 发布页操作顺序（脚本严格按此执行）

1. 打开发布页（已带登录态 Cookie）。
2. 点击正文编辑器（`[contenteditable='true']` 的 div），清空后注入正文。
   - 注意：微头条正文是 `contenteditable`，不是 input/textarea，必须用 `insert_text` / `execCommand`，不能 `set value`。
3. 配图（可选，情感/热点类建议 1-3 张）：
   - **图片上传 4 步（最易错，必须全走）**：
     1. 点「图片」按钮 → 打开上传面板
     2. 在 `.upload-image-panel` 内 `input[type=file]` 上调 `set_input_files`
     3. **等 6 秒**（转码/上传），不要跳过
     4. 点缩略图 `.img-wrap img` 选中 → 点 `.byte-btn-primary:has-text('确定')` 确认
   - **成功校验**：正文区出现「共 N 张，还能上传 17 张」字样才算插入成功。
   - ⚠️ 只 `set files + Escape` **不会**插入图片，这是头号上传失败原因。
   - ⚠️ 图片若含可读文字 / 敏感地名会被平台过滤，ImageGen prompt 必须强调 `no readable text`。
4. 头条首发（正文 ≥100 字才可勾）：点 `label:has-text('头条首发')`（自定义 checkbox，非原生 input）。
5. 点「存草稿」按钮（`button:has-text('存草稿')`）。
6. **成功判据**：页面出现「保存成功」toast。
   - ⚠️ **不要**用草稿箱条目数对比是否成功——无头模式下草稿列表常为空，会误判失败。

## 3. 运行产物

| 文件 | 作用 |
|---|---|
| `posts.json` | 当次 AI 生成的稿件数组 `[{body, images:[路径]}]` |
| `images/` | ImageGen 生成的配图 |
| `toutiao_auth.json` | 登录态 Cookie（首次 `--login` 生成，之后无头复用） |
| `published_topics.json` | 已发布主题去重表（按正文 md5 前 12 位） |
| `last_run.json` | 幂等标记（`{date, status, count, ts}`），当天 success 则跳过 |

## 4. 登录态管理

- 首次：`python publish_draft.py --login` → 弹浏览器 → 手机扫码 → 脚本轮询真实会话 Cookie
  （`sid_tt` / `sessionid` / `passport_auth_status` / `uid_tt`）出现才保存。
- 之后：无头模式 `add_cookies` 复用，无需重复扫码。
- 失效（Cookie 过期 / 睡眠唤醒无新登录）：重跑 `--login`。
- 校验：脚本启动后若 8s 内检测不到编辑器，判定登录失效，提示重跑 `--login`。

## 5. 故障排查表

| 现象 | 原因 | 处理 |
|---|---|---|
| 永不自动跑 | `next_run_at` 卡旧值 | 手动直写 DB 拉回次日 9 点（`rearm_automation.py --next9`） |
| 图没插进去 | 只 `set files+Escape` | 走完整 4 步（点图→set→等6s→点缩略图→确定） |
| 草稿数对比失败 | 无头 SPA 列表空 | 看「保存成功」toast，不比数量 |
| 登录失效 | Cookie 过期 | 重跑 `--login` |
| 登录触发不跑 | 睡眠唤醒无新登录 | 醒后重新登录一次 |
| 发布后流量停滞 | 过 6h 黄金窗改正文 | 只首评 / 回访篇，不改正文 |
| 编辑器点击被拦截 | 发文页自动弹出「发布助手」浮层（byte-drawer-mask）遮住编辑器 | 脚本已自动关浮层（点 `.byte-drawer-close-icon` + Escape）；若仍拦截，检查浮层关闭选择器 |

## 6. 选择器校准

所有选择器集中在 `../config.json` 的 `selectors`。若发布页改版导致定位失败：
1. 跑 `python publish_draft.py --inspect` 导出 `inspect.html`。
2. 浏览器打开，用开发者工具确认当前选择器。
3. 改 `config.json` 对应字段，无需动代码。

## 7. 换赛道 / 换账号 / 换机器

- 换赛道：改本文件第 1-2 节描述 + `content-strategy.md` 第 1-4 节（钩子库通用）。
- 换账号：删 `toutiao_auth.json` 重跑 `--login`；改 `config.json` 的 `niche`。
- 换机器：`run_on_logon.ps1` / `rearm_automation.py` 绝对路径 + `automation_id` 需改；`config.json` 的 `workbuddy_exe` / `python_exe` 改为本机路径。
