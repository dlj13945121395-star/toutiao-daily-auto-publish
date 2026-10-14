---
name: toutiao-weitoutiao-auto-publish
description: 今日头条/微头条每日自动发布技能。工作日 11:00 生成 6 篇原创文章（各 3 张无文字插图，共 18 张）+ 6 条对应微头条（内容对应文章、配图复用文章首图）→ 12:00 / 14:00 / 15:00 / 16:00 / 17:00 / 18:00 六个自动化任务各发一组「1 篇文章 + 1 条微头条」。含登录态复用、正文插图+自动封面、发布请求开关修正（tuwen_wtt_trans_flag）、微头条无定时功能需本机当场发、Windows 登录兜底触发。适用于自媒体日更、头条号矩阵运营。
---

# 今日头条 / 微头条 · 自动发布技能

把「头条号日常内容生产」自动化：工作日生成 6 篇「文字+插图」原创文章并自动发布（每天 6 个时段各发一组「文章+微头条」，均本机立即发），发布请求里强制置位微头条开关，实现一次发布原生带出文章+微头条（真·同时发布）。

## 触发场景（何时用我）

- 用户说「帮我自动发微头条 / 头条日更 / 头条号自动发布 / 微头条存草稿」
- 用户已部署本技能，需要排查「为什么不自动跑」「图没插进去」「登录失效」
- 用户想做头条号内容矩阵、热点跟进、数据驱动迭代

## 整体架构（三件套 + 双规范）

```
WorkBuddy 自动化（工作日：11:00 生成器 + 12/14/15/16/17/18 六个发布任务，共 7 个）
   └─ 11:00 生成器：ContentCreator 写 6 篇文章 + 6 条对应微头条 → ImageGen 配 18 张图（微头条复用文章图）
   │     → 写 articles_batch.json + wtt_batch.json（都不发布）
   └─ 12:00 发布：run_one_slot.py --slot 0 → 发第 1 篇文章 + 第 1 条微头条
   └─ 14:00 发布：run_one_slot.py --slot 1 → 发第 2 篇文章 + 第 2 条微头条
   └─ 15:00 发布：run_one_slot.py --slot 2 → 发第 3 篇文章 + 第 3 条微头条
   └─ 16:00 发布：run_one_slot.py --slot 5 → 发第 6 篇文章 + 第 6 条微头条
   └─ 17:00 发布：run_one_slot.py --slot 4 → 发第 5 篇文章 + 第 5 条微头条
   └─ 18:00 发布：run_one_slot.py --slot 3 → 发第 4 篇文章 + 第 4 条微头条，随后 cleanup_day.py 清理当天本地产物
   └─ 14:00 额外：fetch_comments.py 抓待回复评论 → 写 replies.json → reply_comment.py --send（幂等台账 replied_comments.json）
   └─ 写 published_topics.json（去重）

Windows 计划任务 ToutiaoAutoOnLogon（AtLogOn 兜底）
   └─ run_on_logon.ps1：拉起 WorkBuddy → 等 5s → rearm_automation.py
   └─ rearm_automation.py：直写 workbuddy.db 补跑错过的发布任务
```

**关键文件**（均在本技能目录内）：
- `SKILL.md` — 本文件
- `config.json` — **所有 URL / 选择器 / 路径集中在此**，校准只改这里
- `scripts/publish_draft.py` — 发布核心（登录 / 填稿 / 传图 / 存草稿）
- `scripts/fetch_topics.py` — 抓**站内真实话题 + 讨论数**（发布页 `#关键词` 联想），`merge_topics.py` 合并成话题池
- `scripts/fetch_comments.py` — 抓评论列表并判定待回复；`scripts/reply_comment.py` — 按计划发送回复（幂等台账 `replied_comments.json`）
- `scripts/rearm_automation.py` — 上膛（直写 DB 触发补跑）
- `scripts/run_on_logon.ps1` — 登录启动兜底
- `references/writing-spec.md` — 操作说明书（发布页操作 + 故障排查）
- `references/content-strategy.md` — 战略 + 10 类钩子库 + 数据闭环
- 运行产物：`posts.json` / `published_topics.json` / `last_run.json` / `toutiao_auth.json`(登录态) / `images/`

## 标准工作流（首次部署 see references/DEPLOY.md）

1. `pip install playwright && playwright install chromium`
2. `python scripts/publish_draft.py --login` → 弹浏览器扫码 → 自动存 `toutiao_auth.json`
3. 建 7 个 WorkBuddy 自动化（见 config.json 的 `automation_ids`，参数见 `automation_config.json`）：
   - 工作日 11:00 生成器：写 6 篇文章 + 6 条微头条 + 18 张图 → 写 articles_batch.json + wtt_batch.json
   - 工作日 11:20 生成兜底守护：自检当日批次，缺失则完整重跑生成（只生成不发布）
   - 工作日 12:00 / 14:00 / 15:00 / 16:00 / 17:00 / 18:00 六个发布任务：各跑 run_one_slot.py --slot 0/1/2/5/4/3
4. 每个自动化**建完手动直写 DB** 把 `next_run_at` 拉回目标时间（否则沿用旧值永不触发）
5. 注册 `ToutiaoAutoOnLogon` AtLogOn 计划任务（行内注册，见 DEPLOY）
6. 注销重登验证；次工作日按点自动跑，手机看首页最近作品复核

## 自动化 Prompt 模板

```
11:00 生成器（见 automation_config.json 的 prompt 全文）：
  ContentCreator + humanizer/humanizer-zh 写 6 篇「文字+3图」文章 →
  ImageGen 为每篇生成 3 张无文字插图（s{N}_a/b/c.png，存 images/article_inline/）→
  再写 6 条对应微头条（配图复用文章首图）→
  写 articles_batch.json + wtt_batch.json（均不发布）→ 输出 [DONE]。
12:00 / 14:00 / 15:00 / 16:00 / 17:00 / 18:00 发布器：各自运行 run_one_slot.py --slot 0/1/2/5/4/3，
  发布 1 篇文章 + 同组 1 条微头条（微头条由脚本内部调 publish_draft.py 完成）。
```

## ⚡ 生成提速（2026-09-20 用户要求「生成太慢」）

生成慢的头号原因是**18 张配图一张一张串行等**，其次是内容反复改文件。已在 11:00 生成器 prompt 里强制：

1. **配图并行**：18 张图（s0~s5）在**同一条消息里并发发起多张 ImageGen 调用**（建议每条 5 张，约 4 批跑完），全部 `output_dir=images/article_inline/`，prompt 强调 `no readable text`。
2. **内容一次落盘**：6 篇文章 + 6 条微头条写进**同一个 Python 生成脚本**，一次 Write、一次运行即落盘（`articles_batch.json` + `wtt_batch.json`），**不反复 Edit、不反复试跑**。
3. **热点并行抓**：第 0 步多条 WebSearch 并发发起。
4. **少输出中间稿**：直接产出最终脚本并运行。

> 图片生成独立且可并行；先并行挂起 18 张图、同时写正文脚本，两条线重叠进行。
> ⚠️ 并发 ImageGen 的文件名只精确到秒，**同一秒内并发的多张图会互相覆盖**（2026-09-22 实测）。对策：并发批之间错开，或落图后写 `images/article_inline/_rename_manifest.json` 清单，交给 `rename_today_images.py` 按 key 精确配对；发现少图就按内容补生成。

## ⭐ 站内话题抓取（2026-09-24 新增 · 做话题标签的首选来源）

**为什么不用 WebSearch 顶替**：微头条末尾的话题必须是**平台侧真实存在的 tag**，WebSearch 抓的热榜词大概率挂不上、点不进去。站内话题池才是正解。

**原理**：微头条发布页的正文编辑器输入 `#关键词`，会实时弹出**站内话题联想**（带讨论数），形如 `#Token经济# 887讨论`。

```bash
# 抓一批关键词的站内话题（默认词 = 账号定位 + 常见 AI 关键词）
python scripts/fetch_topics.py --keywords "Token,漫剧,副业,AI工具" --top 12
python scripts/fetch_topics.py --keywords "..." --write-hot   # 并入 hot_topics_today.json
python scripts/merge_topics.py                                # 合并成 topics_platform_<日期>.json
```

- 输出：`topics_probe*.json`（分关键词）+ `topics_platform_<日期>.json`（按讨论数排序的合并池）。
- 只读联想，**不发布、不存草稿**。
- ⚠️ **每条关键词都要重载一次发布页**：编辑器在清空/失焦后会从 DOM 摘掉，复用同一页面再点必 `Timeout waiting for [contenteditable='true']`。
- ⚠️ App「消息 → 创作邀请 → 话题」在网页端**没有**对应入口（左栏「创作灵感」是 2805 个有奖征文活动，不是话题榜）。App 里的话题名与站内 tag 也可能不一致（多逗号/措辞差异），**挂 tag 一律以 fetch_topics.py 抓到的站内原文为准**。

## ⭐ 文章 & 微头条话题都必须用「话题选择器」插入（2026-09-30 修文章 · 2026-10-12 补微头条）

**问题（用户两次反馈）**：文章末尾的 `#话题#` **点不动**；后来发现**微头条的也点不动**，两边都只是普通文字、没有点击跳转。

**根因（2026-10-12 已实测更正）**：**两个编辑器其实都不会**把纯文本 `#话题名#` 自动变成可点击话题。
（早期的「微头条会自动识别」判断是**错的** —— 当时只看了渲染文本、没验证点击跳转。）
两边都必须走编辑器的 **话题选择器**：正文里敲 `#` → 弹出 `section.mention-selector-modal.forum`
→ 候选项 `section.forum-list-item`（文本在 `.forum-list-item-text`，带「N讨论」）→ 点选后插入
`<a class="tteditor-forum" data-name="..." data-concern-id="...">#话题#</a>`，这才可点击跳转。

**修复（生成器只需保证话题名取自站内池，脚本侧全自动）**：
| 通道 | 脚本 | 做法 |
|---|---|---|
| 文章 | `publish_article_draft.py` | `split_trailing_topics(body)` 拆出末尾**单独一段**的 `#话题#`（仍计入 1200~2500 字数）→ `insert_article_topics()` 逐个敲 `#`、输名过滤、点选 |
| 微头条 | `publish_draft.py` | `split_trailing_topics(body)` 拆出末尾**单独一行**的 `#话题#` → `insert_wtt_topics()` 逐个敲 `#`、输名过滤、点选 |

- **无候选一律退化为纯文本**（宁可点不动，也不挂错话题）；每个话题的异常都被单独兜住，**最坏只退化、绝不中断发布**。
- 🔑 **搜索技巧（2026-10-12 实测关键）：站内话题联想的匹配是按「短关键词」做的，输入全名常常零候选！**
  例：`技术有速度，人间有温度，读懂当下的人工智能` 输全名搜不到，输 `技术有速度` 才命中；
  `AI编程正在重塑Java团队协作模式` 输全名搜不到，输 `AI编程` 才命中。
  → 因此两个脚本都内置 `topic_queries()`：**按「全名 → 首个标点前 → 前8/6/4 字」由长到短逐个试探**，
  某个查询词零候选就把敲进去的 `#`+查询词退格清掉、换更短的再试。
  → 若整串查询词**一个候选都没出现**（联想服务偶发瞬时无响应，实测有 2/7 概率），**等待 2.5s 后整体再跑一轮**。
  → 校验工具：`python scripts/verify_live_topics.py [--slots 1,2,3]`（只读实测每个话题能否点开，输出 HIT/NEAR/MISS）。
- ⚠️ **注意区分「话题不存在」与「查询词太长」**：`Token经济会成为下一个风口吗`（App 推荐页的口号式长标题）
  换 4 个查询词都搜不到 → 属于**真不存在**，必须换成站内真话题（如 `Token经济`，906 讨论）；
  而 `技术有速度，…` / `AI编程正在重塑…` 只是**查询词太长**，改查询词即可，**不必改稿件**。
- ⚠️ **话题名必须取站内话题池原文**（`topics_platform_<日期>.json` / `hot_topics_today.json`），否则选择器搜不到候选 → 退化成纯文本 → 依旧点不动。`audit_*.py` 已校验「话题 ∈ 当日池」。
- **数量（2026-10-13 用户指定）**：每篇文章末尾话题段、每条微头条话题行各挂 **4~5 个** `#话题#`（由 2~3 上调），且**必须与该篇内容强相关**（按正文关键词从池里挑，6 篇之间可复用、禁止为凑数挂无关话题）；池子不够大就加关键词再跑一轮 `fetch_topics.py`（串行，`--out topics_probe2.json`）。`audit_20261008.py` 已按 4~5 校验。
- ⚠️ 面板里敲**空格 = 取消插入话题**，所以多话题之间的分隔空格必须在面板关闭后再敲。
- ⚠️ 必须跳过面板里的 `div.create-forum-button`（「创建话题」），否则会创建垃圾话题。
- 选择器已登记进 `config.json`：`selectors.article_topic_item` / `selectors.wtt_topic_item`（同值）。
- 插入后脚本会校验编辑器内 `a[class*=tteditor-forum], a[data-concern-id]` 节点数并打印
  「话题插入完成 X/N 个；可点击话题节点数 = M」，M < N 时告警（说明该话题站内搜不到）。
- 校准工具（均只读、不发布）：`scripts/inspect_article_topics.py`（文章）、`scripts/inspect_wtt_topics.py`（微头条，含点选验证）。

## ⭐ 评论自动回复（2026-09-24 新增 · 挂在 14:00 任务上）

用户指定：**评论回复在 14:00 那个自动化里做**，且**回复过的评论不再二次回复**。

```bash
# 1) 抓待回复评论（★ = 待回复）
python scripts/fetch_comments.py --out pending_comments.json
# 2) 把回复写进 replies.json（格式见 reply_comment.py 顶部注释）
# 3) 发送（不加 --send 只预演）
python scripts/reply_comment.py --plan replies.json --send --limit 6
```

**幂等两道闸**（用户硬规则：回复过的不二次回复）：
1. **主力防线** `replied_comments.json` 台账 —— key = `作者 + 评论正文` 的 md5 前 12 位；发送成功即落账，下次直接跳过。
2. 页面复核 —— 详情区「全部 N 条回复」> 0，或**页面正文里能找到台账记的那条回复原文**（`reply_text_on_page`）。

⚠️ 实测坑：**页面回复数不太可靠**（刚回复完读到 1，再次抓取又读到 0），所以**台账才是判据**，页面对比只作辅助。

**回复口径**：口语化、第一人称、短句，直接答读者问的那件事；纯夸赞的顺着接一句 + 补一个具体细节；每条 40~120 字；禁用冒号/破折号/双引号；拿不准的不编。

**页面结构（换版时按这个查）**：
- 入口 `https://mp.toutiao.com/profile_v4/manage/comment/all?enter_from=left_menu`（左栏「管理 → 评论管理」）
- 列表条目 `.all-comment-item-wrap`（选中态多一个 `select` 类），条目内文本顺序 = 作者 / 评论了微头条|文章 / 《作品摘录》 / 评论正文 / 时间 / 回复 / 赞 / 置顶
- 点击某条后，右侧才出现可见的 `textarea.byte-textarea`（placeholder「积极回复可吸引更多人评论」）+ `button.byte-btn-primary`「发布」（空输入时 disabled）

## 关键机制（详见 writing-spec.md）

- **登录态**：`--login` 轮询真实会话 Cookie（sid_tt/sessionid/passport_auth_status/uid_tt）出现才保存，之后无头复用
- **图片上传 4 步**：点图片 → `set_input_files` → 等 6s → 点缩略图 → 点确定 → 验证「共 N 张，还能上传」
- **头条首发**：正文 ≥100 字才可勾；点击自定义 `label:has-text('头条首发')`
- **成功判据**：点存草稿后页面出现「保存成功」toast（**不**比草稿箱条目数，无头常为空）
- **幂等**：当天 `last_run.json` success 则跳过，防重复生成
- **兜底触发**：WorkBuddy 无 CLI/无 logon 触发器 → OS 计划任务 + `rearm_automation.py` 直写 DB

## 内容生成工作流（多技能协同 SOP）

本技能生成文章内容时，必须按以下链路协同「热点猎手」专家与多个技能，确保内容既蹭对热点、又有人味（规避头条 AI 降权）：

1. **内容创作专家（ContentCreator / 热点猎手）**：从当日热榜定题 + 定切入角度（AI 搞钱/提效/避坑视角），做合规与账号调性把关。
2. **热点选题**：把选定热点变成可发内容（正文/封面文案/话题标签），输出初稿。
3. **humanizer（v4.1，中文深度）— 强制关卡**：按四层自检处理正文
   - L1 硬性规则：禁用词清零；标点禁令（全文无冒号「：」、破折号「——」、双引号）；清「不是A而是B」三毒（假靶子/同义替换/无关硬凑）；高频堆叠副词（极其/猛地/稳稳/仿佛…）一段内只留一处；删结构套话（"先说答案""在当今…的时代""掰开了揉碎了"）；工具名必须具体，不许"某个AI工具"
   - L2 风格一致性：开头从具体事件切入；长短句交替，有一句话独立成段；口语化，至少一处自嘲或承认不足
   - L3 内容质量：每个观点有具体人/场景/数据支撑；知识"聊着顺手带出来"而非"下面我来科普"；承认对立面
   - L4 活人感终审：读完像真人在聊，不是 AI 在输出信息
4. **humanizer-zh — 强制补查**：5 条核心原则 —— 删填充短语、打破公式结构（**两项优于三项**）、变化节奏、信任读者（不手把手引导）、删金句（听着像可引用的就重写）。
5. **tencent-docx**（可选）：仅当用户明确要 Word 交付时才产出，否则不落地文件（见「发布后自动清理」）。
6. **toutiao-weitoutiao-auto-publish（本技能）**：文章**必须配 3 张正文插图**——用 ImageGen 生成「无文字」插图，存 `images/article_inline/`，文件名 `s{N}_x.png` 写入 `articles_batch.json` 的 `inline_images`。发布走 `python scripts/run_one_slot.py --slot N [--schedule HH:MM]`：① 发布文章（自动插图 + 复用自动封面 + 勾选头条首发/引用AI）→ ② 头条默认「同时发布微头条」开关自带微头条（无需脚本）→ ③ 标记 `published_at` + 清理本 slot 图（已发到服务器，删本地无碍）。生成器在 11:00 只生成不发布；六个发布器分别在 12:00 / 14:00 / 15:00 / 16:00 / 17:00 / 18:00 各跑 `run_one_slot.py --slot 0/1/2/5/4/3` 本机立即发。

> **去 AI 味只改「怎么说」，不改「说什么」**——事实、数据、人物一律不动。这一关直接对应《今日头条低质账号专项治理公告》对「低质 / AI 内容」的治理，2026-09-10 起设为发布前强制步骤。

> 账号定位：**AI（普通人用 AI 搞钱 / 提效 / 避坑）**（2026-09-01 改，原为「人情世故 + 真实故事」）。内容以普通人视角讲 AI 工具的真实玩法、踩过的坑、能落地的搞钱/提效思路，说人话、给方法、不空谈概念；人味由真人审核把关。AI 工具真实经历（美图API/影刀RPA/OpenClaw 等）是核心素材，落点就是「这东西普通人怎么用、能省多少事/赚多少钱、有哪些坑别踩」。

## 调度架构（2026-09-20 修订：1 个生成器 + 1 个生成兜底 + 6 个发布任务，共 8 个）

每天工作日 8 个独立 automation（config.json 的 `automation_ids`）：

| 时间 | 任务 | ID | 角色 |
|---|---|---|---|
| **11:00** | 头条日更·生成器 | `automation-1789031424055` | **只生成内容**：第 0 步先跑 `fetch_topics.py` 抓站内话题池 → 再并发 WebSearch 补热点 → 6 篇文章（各 3 图 + 末尾话题段）+ 6 条微头条 → 写 `articles_batch.json` + `wtt_batch.json`。**不调用任何发布脚本** |
| **11:20** | 头条日更·生成兜底守护 | `bfcb8b20-269c-41b1-a550-4709aa5dcae9` | 自检当日批次，缺失则完整重跑生成流水线（**只生成不发布**）；正常日跳过 |
| **12:00** | 头条日更·发布 slot0 | `automation-1789033524917` | `run_one_slot.py --slot 0` → 发第 1 篇文章 + 第 1 条微头条（含生成兜底自检） |
| **14:00** | 头条日更·发布 slot1 + **评论回复** | `automation-1789371591338` | `run_one_slot.py --slot 1` → 第 2 组；**随后抓待回复评论 → 逐条写回复 → `reply_comment.py --send`** |
| **15:00** | 头条日更·发布 slot2 | `automation-1789371596649` | `run_one_slot.py --slot 2` → 第 3 组 |
| **16:00** | 头条日更·发布 slot5 | `c2f0d87c-14e1-4918-b01d-2e2e1a4458a0` | `run_one_slot.py --slot 5` → 第 6 组（2026-09-20 新增） |
| **17:00** | 头条日更·发布 slot4 | `6bf71745-9386-4634-88fe-733f7cdd1a42` | `run_one_slot.py --slot 4` → 第 5 组（只发布，不清理） |
| **18:00** | 头条日更·发布 slot3 + 当日清理 | `automation-1789371601835` | `run_one_slot.py --slot 3` → 第 4 组；再 `cleanup_day.py --yes` 清理当天本地产物（带安全闸） |

**为什么拆成 6 个发布任务**：微头条编辑器只有「存草稿 / 发布」两个按钮，**没有定时发布**，
所以微头条必须在排定时刻由本机当场发出；`run_one_slot.py --slot N` 按**用户指定顺序**完成：
**先发微头条**（文字 + 1 张复用图）→ **再发文章**（3 张插图插在文字段落之间，图文交替）。
（文章本身支持头条定时发布，但为了和微头条成对，统一走本机即时发布 —— 需电脑在线）。

**批次文件 `articles_batch.json`** schema：

```json
{
  "generated_at": "ISO 时间",
  "articles": [
    {
      "slot": 0,
      "type": "article",
      "title": "...", "body": "...",
      "cover": "post1.png",
      "inline_images": ["s0_a.png", "s0_b.png", "s0_c.png"],
      "settings": {"first_release": "头条首发", "work_declare": "引用AI"},
      "schedule_time": null,
      "published_at": null,
      "publish_status": null
    },
    {...slot 1/2/3/4/5 同结构，schedule_time 分别为 "14:00"/"15:00"/"18:00"/"17:00"/"16:00"...}
  ]
}
```

> 注意：`articles_batch.json` 的 schema **无 `wtt` 字段**——微头条单独存在根目录 `wtt_batch.json`（每条带 `slot` 字段），由各发布任务按 slot 取用后单独发布。

**图片命名规范**：每个 slot 的配图必须用 `s{N}_x.png` 格式（脚本据此只清本 slot 的图，不影响其他 slot）。

**清理策略**：每个 `run_one_slot.py --slot N` 完成后，只删 `images/article_inline/s{N}_*.png` 与本 slot 临时文件，**不动其他 slot、封面图、`articles_batch.json`、`published_topics.json`**。

## ⛔ 隔日批次硬闸（2026-10-12 新增 · 用户要求「保证今天发布的是今日生成的」）

**问题背景**：调度器存在**提前/二次触发**的历史 bug，曾导致某天任务取用了**隔日旧批次**（如今天发出 10-09 的内容），造成跨日错乱与重复发文。

**硬约束**：`scripts/run_one_slot.py` 在**发布前**执行 `stale_guard()`，两项**必须同时满足**，否则**拒绝发布并 `exit 3`**：

| 检查 | 判据 |
|---|---|
| 文章批次 | `articles_batch.json` 的 `generated_at` 日期 **== 今天** |
| 微头条批次 | 同目录 `wtt_batch.json` 的 **mtime 日期 == 今天** |

- **微头条路径跟随文章批次**：`--batch X` 时用 `X` 同目录的 `wtt_batch.json`（根批次 → 根 `wtt_batch.json`），避免「文章用旧批、微头条用新批」张冠李戴。
- **人工补发历史批次**：显式加 `--allow-stale` 放行（此时只告警不拦截），并打印「人工补发模式」。
- `article_post.json` 新增溯源字段 `source_generated_at`，事后可核对稿件来自哪个批次。
- **一键体检**：`python scripts/verify_today_batch.py`（只读）——核验 ①批次 `generated_at` ②`wtt_batch` mtime ③`hot_topics_today.date` ④标题与 `published_topics` 零重复 ⑤各 slot 配图齐备；全绿输出 `RESULT: PASS`，否则 `FAIL` 并逐项列明。

**常规发布任务无需任何改动**（它们不传 `--batch`，默认用根批次，天然走今日批次）；**只有人工补发的历史命令才需要显式 `--allow-stale`**。

## 头号坑（必读）

1. `automation_update` **每次调用都会把 `next_run_at` 重置回初始值**（不只是"不重算"——改 prompt、改 rrule 都会触发重置。2026-09-10 实测两次：设好的 12:30 被打回 12:25）
   → **每次 `automation_update` 之后都必须重新直写一次**：
   ```bash
   python scripts/rearm_automation.py --id <ID> --at <目标时间 epoch 毫秒>
   ```
   再用 sqlite 读 `automations.next_run_at` 复核。（历史教训：曾卡 2030 永不触发；也曾在改完 prompt 后把 12:30 打回 12:25）
2. **头条「定时发布」可用，但必须补 `timer_status=1`**（2026-09-10 实测确认，曾一度误判为"功能坏了"）：
   - 现象：选完日期/时/分点「预览并定时发布」→ 再点「确认发布」，文章却被**立即发布**。
   - 根因：请求里 `timer_time`（目标时间）是对的，但 **`timer_status` 仍是 `0`**（未启用定时）→ 服务端当立即发布。
   - 修复：`page.route("**/article/publish**")` 拦截，把 post body 的 `timer_status=0` 改为 `1`（已在 `publish_article_draft.py` 的 `scheduled_publish()` 实现）。
   - 另外：定时弹窗**必须文章已设封面**才出现；下拉选择必须用**真实点击**（force/JS click 会导致 React 状态不同步）。
   - 硬约束：排程时间须在「当前 +2 小时」到「+7 天」之间。
2. WorkBuddy 无 CLI / 无 logon 触发器 → OS 计划任务 + DB 直写兜底
3. PowerShell `Restricted` → 计划任务必须**行内注册** + `Import-Module ScheduledTasks`
4. 图上传只 `set files+Escape` 不插入 → 必须走 4 步
5. 图含可读文字 / 敏感地名会被过滤 → ImageGen prompt 强调 `no readable text`
6. 过 6h 黄金窗改正文会重新过审掉推荐 → 只首评 / 回访篇救
7. 模型可能谎报完成（尤其免费混元：没写完/没插图也说"完成"）→ 必须手机草稿箱**肉眼复核**正文完整度、配图比例、头条首发勾选；脚本只保证"存草稿动作执行"，不保证内容质量

## 文章通道（2026-09-07 二轮验证 · 推翻前结论 · 必读）

**前结论「文章存草稿不可行」是错的。文章可以存草稿**，正确路径是「复刻 `/article/publish` 请求 + `save=1`」。

### 可行方案：复刻 save=1（已验证可落库）

1. 导航 `hub 根 → 点「文章」` 挂载编辑器（直链子路由不挂载）。
2. 填标题 `textarea[placeholder*='请输入文章标题']`、正文 `.ProseMirror`。
3. 点「预览并发布」→ **捕获 `/mp/agw/article/publish` 的完整请求**（form 表单，非 JSON）。
4. 把字段 `save` 由 `0` 改成 `1`，用 `page.evaluate(fetch)` 同域复刻 POST（cookie 自动带）。
5. 判据看 **`code` 与 `pgc_id`**：`code:0` 且 pgc_id 非 0 = 真落库；`code:7050 保存失败 / pgc_id:"0"` = 服务端拒绝。

**为什么必须复刻**：「预览并发布」的确认模态框（含 存草稿/确认发布 按钮）在 headless 沙箱**根本不渲染**，全页搜不到这两个词。绕开它只能复刻请求。
注意：自己 fetch 复刻常返回 `code:0` 但那多半是**预览回显**，不是真保存——服务端是否建草稿要看编辑器自身那次请求的响应。

### payload 字段（form-encoded）

`source, extra, content, title, search_creation_info, title_id, mp_editor_stat, is_refute_rumor, save, timer_status, draft_form_data, pgc_feed_covers, article_ad_type, is_fans_article, govern_forward, praise, disable_praise, tree_plan_article, activity_tag, trends_writing_tag, claim_exclusive`

### 侧边栏设置（选择器 + 坑）

- **声明首发**：`.pgc-edit-cell` 内 `.edit-label` 为「声明首发」，点 **`label.byte-checkbox:has-text('头条首发')`**。
  ⚠️ 直接点文字 span 会被 `byte-checkbox-mask` 吃掉，`checked` 仍是 False（务必点 label）。
- **作品声明**：同上，点 `label.byte-checkbox:has-text('引用AI')`（该组还有 取材网络/原创 等，是 checkbox 组非下拉）。
- **同时发布微头条（2026-09-13 纠正：光勾 UI 不够）**：头条编辑器「同时发布微头条」开关**勾上 ≠ 后端真生成微头条**（09-13 实战：4 篇都勾了却没带出）。真生效靠发布请求 payload 里的 `tuwen_wtt_transfer_switch=1`；`publish_article_draft.py` 已用 `_patch_publish` 路由在发请求前强制注入（定时+直接发布分支共用），UI 勾选仅作幂等兜底。若注入后仍缺失微头条，回退显式 `gen_wtt_from_article.py` + `publish_draft.py --force` 方案。
- **封面（`required`）**：`.article-cover-add`（「+」）弹素材库 →「本地上传」→ `input[type=file]` → 上传 → **选中刚传的图** →「确定」。
  - ⚠️ **卡死根因（2026-09-10）**：正文一旦插入图片，头条会**自动抓正文图之一当封面**，此时 `.article-cover-add` 按钮直接**从 DOM 消失**（变成「编辑/替换」）。脚本若仍去点它 → 超时卡死。
    → `publish_article_draft.py` 已改为：先判 `.article-cover-img-wrap img` 是否存在，**已自动填充就直接复用，不再点 `.article-cover-add`**；只有按钮还在时才走上传。`cover` 字段给个兜底图名（post1.png 等）即可，通常走不到上传分支。
  - 上传后缩略图渲染需 **~5 秒**，等 2 秒去选会找不到元素。
  - 只点「确定」不选中图片 → `pgc_feed_covers` 为空。

### 结论更新（2026-09-09 16:00 · 推翻 09-07 的「7050 = 频次保护」判断 · 以本节为准）

- **7050 只拦「存草稿」那一路**（编辑器 autosave / `save=1` 复刻），**不拦发布**。
- 「预览并发布 → **确认发布**」发出的请求带 `msToken + a_bogus` 签名 → 返回 `code:0 提交成功`，**文章直接上线（真发布）**。
- 所以本号**没有可用的「文章存草稿」通道**：不发，或发就是上线。别再尝试 `save=1`。
- **曾误判「落入草稿箱」**：那次用 `/profile_v4/index` 当草稿箱搜标题——**该 URL 是首页**（最近作品 = 已发布条目），命中其实是「已发布」。真草稿箱是 `/profile_v4/manage/draft`（当时实测「共 0 条内容 / 暂无草稿」）。
- **判定发布成功只看首页最近作品是否出现该标题**；`/graphic/post`（作品管理）在自动化里常渲染空白，不可靠。
- **勾选复选框的坑**：`label.byte-checkbox:has_text('引用AI')` 用**下划线**是无效 CSS → `querySelectorAll` SyntaxError → 静默没勾上。必须用 `:has-text`（连字符），或 JS 直派 DOM（`label.click()`），并**回读 `checked` 确认 now=True**。
- **勾选第二坑（2026-09-10 实测）**：编辑器会**记住上次的侧边栏设置**，头条首发可能本来就是勾上的。脚本若**盲点**会把已勾选项点掉（实测 was=True → now=False，当天文章就这样丢了首发声明）。已在 `publish_article_draft.py` 修复（wasChecked=True 就跳过点击）。判定是否已声明首发，以日志 `now=True` 为准。
- **7050 出现在「预览并发布 → 确认发布」步 = 硬失败（2026-09-23 / 09-24 连续两日复现）**：中途 autosave 的 7050 可忽略，但**最终带签名令牌的确认发布请求**若仍返回 `code=7050`、且日志 `已发布(首页最近作品命中): False`，则文章未上线（`run_one_slot.py` 会标 slot failed / rc=1）。
  - **标准补救动作：不要重跑 `run_one_slot.py`（会重复发微头条）**，直接原地重跑
    `python scripts/publish_article_draft.py article_post.json`
    —— 09-23、09-24 两次实测均**重试一次即成功**（`首页最近作品命中: True` → `DONE 文章已发布上线`）。
  - 成功后必须把 `articles_batch.json` 该 slot 由 `failed` 手工改回 `published` + 实际时间、删 `error`，否则 18:00 的清理安全闸会误判、当日产物不被清理。
  - 独立复核：`verify_published.py "<标题关键词>"` → 「已上线」。

> 双脚本幂等说明（2026-09-14 修订）：`publish_article_draft.py` **不写** `last_run.json`；微头条由 `run_one_slot.py` 在文章发出后单独发布（读 `wtt_batch.json` 按 slot 取），5 组各自独立、互不干扰。`published_topics.json` 用兼容 dict 格式（`{"key":..., "type":"article"/"wtt"}`），不同稿件 key 不同不会互删。

## 微头条（原生「同时发布微头条」· 2026-09-14 定案）

### 🔑 决定性规则：能否同步微头条，取决于**正文字符数**

| 正文长度 | 前端 `extra.tuwen_wtt_trans_flag` | 结果 |
|---|---|---|
| **< 100 字符** | 自动置 `"1"` | ✅ 头条原生同步带出微头条 |
| **≥ 100 字符** | 自动置 `"0"` | ❌ 服务端不生成微头条（平台限制，脚本无法绕过） |

抓包硬证据（同一脚本、同一账号）：
- 14:16 短文（75 字符）→ 日志 `原值 {'tuwen_wtt_trans_flag': '1'}`
- 13:54 / 13:32 长文 → 日志 `原值 {'tuwen_wtt_trans_flag': '0'}`

> 这也是此前所有尝试全部失败的根本原因：脚本原本有 `len(body) < 200` 的硬性校验，
> 发的全是长文，永远落在「不可同步」区间。**该校验已改为只保留 10 字符防空白**，
> 并按长度在日志里标注「短文模式（可同步微头条）」/「长文模式（不会同步微头条）」。

### 字段名坑（排查过程中的关键发现）

最终「确认发布」请求用的字段是 **`tuwen_wtt_trans_flag`**，和编辑期自动保存用的
`tuwen_wtt_transfer_switch` **不是同一个字段**（对应 UI class `form-tuwen_wtt_trans`）。
此前按错误字段名注入，所以永远无效。`_patch_publish` 路由现在把两个字段都兜底置 `"1"`。

> ⚠️ 重建请求体必须用 `m.start(1)` / `m.end(1)`。正则 `(?:^|&)(extra=...)` 会把前导 `&` 吃进匹配，
> 若用 `m.start()` 重建会丢掉 `&`、参数串损坏 → 服务端 `7050 保存失败`（曾误判为「签名拦不住」）。

### 当前生产配置（2026-09-14 定稿，2026-09-17 新增 17:00，2026-09-20 新增 16:00 共 6 个时间点自动发「文章 + 微头条」）

| 时间 | 任务 | 动作 |
|---|---|---|
| 11:00 | 生成器 | 生成 6 篇文章（各 3 图，共 18 张）+ 6 条对应微头条（**配图复用文章首图**）→ 写 `articles_batch.json` + `wtt_batch.json`，不发布 |
| 12:00 | 发布 slot 0 | **先发微头条 → 再发文章** |
| 14:00 | 发布 slot 1 | **先发微头条 → 再发文章** |
| 15:00 | 发布 slot 2 | **先发微头条 → 再发文章** |
| 16:00 | 发布 slot 5 | **先发微头条 → 再发文章**（2026-09-20 新增） |
| 17:00 | 发布 slot 4 | **先发微头条 → 再发文章**（只发布，不清理） |
| 18:00 | 发布 slot 3 | **先发微头条 → 再发文章**，随后清理当天本地产物（`cleanup_day.py`，带安全闸） |

> **排版（用户指定）**：文章 = 文字 + 图片 + 文字 + 图片 + 文字 + 图片（3 张图均匀插在文字段落之间）；
> 微头条 = 文字 + 图片（1 张图在文字后）。
> **生成顺序**：先生成 6 篇文章，再基于文章生成 6 条一一对应的微头条。

- 每个发布任务 = 一条命令：`python scripts/run_one_slot.py --slot N`
  （内部顺序：发文章 → 读 `wtt_batch.json` 取同 slot 的微头条 → `publish_draft.py --publish` 发布）。
- 文章的图：`s0~s5_a/b/c.png`（18 张）；微头条复用对应文章的 `s{N}_a.png`。
- 微头条**没有定时发布**功能，只能在本机排定时刻当场发（需电脑在线，用户已确认持续在线）。
- `config.json` 的 `daily_count` 必须 ≥6，否则第 6 条微头条会被截断。

> 历史备注：文章在自动化下**存不了草稿箱**（编辑器无「存草稿」按钮、自动保存恒 `7050`、
> 四种退出方式草稿箱均无新增）。曾评估「排定时到次日 / 存草稿待手动发」，最终用户选择
> 「4 个时间点本机自动发布」。

### 自检

- `python check_draft.py`：列草稿箱条目，确认 6 条微头条已存进去。
- `python check_wtt.py`：统计首页「发布了微头条」次数。
  ⚠️ 注意：同步出来的微头条**可能不作为独立作品列在首页「最近作品」**，计数 0 不等于没生成；
  若需确认，去头条 App / 公开主页的「微头条」tab 看。
- 兜底（可选）：`WTT_FALLBACK=1` 可恢复「发布后再补发一条引流微头条」。原生生效时**不要开**，会重复。

## 发文设置清单（用户 2026-09-14 指定，脚本自动完成）

> **正文字数硬要求（用户指定）**：**文章 1200~2500 字符**、**微头条 200~500 字符**。
> 生成器落盘前必须用 python 逐条校验 `len(body)`，不达标就地重写。
> （满 100 字符即可勾「头条首发」；本号微头条生成规范下限已提到 200，均在 200~500 之间。）

### 文章（`publish_article_draft.py` 第 4 步）

| 设置项 | 要勾的选项 | 条件 |
|---|---|---|
| 投放广告 | **投放广告赚收益** | 总是勾选（默认不勾，需主动点；该组是互斥单选项） |
| 声明首发 | **头条首发** | **仅正文 ≥100 字符**；短文头条不提供该选项 |
| 同时发布微头条 | 同时发布微头条 / 发布得更多收益 | **正文 <100 字符**：平台默认勾选（脚本调 `ensure_wtt_switch_editor()` 确保勾上）；**正文 ≥100 字符**：头条不提供该开关（选不了） |
| 作品声明 | **引用AI** | 总是勾选 |

实测日志：

```
ok 勾选 投放广告赚收益: was=False now=True
ok 勾选 头条首发: was=True now=True (已勾选，跳过点击)
长文（1339 字符 ≥ 100）：头条不提供「同时发布微头条」开关（选不了），跳过
ok 勾选 引用AI: was=False now=True
```

> 第 3 项「同时发布微头条」规则（2026-09-20 用户澄清）：**<100 字符默认勾；≥100 字符平台不提供该开关（选不了）**。本号文章均 ≥1200 字符，实际走「跳过」分支。

> `set_checkbox()` 的选择器已同时兼容 `checkbox` 与 `radio`。

### 微头条（`publish_draft.py`，选择器见 config.json 的 `selectors`）

| 设置项 | 要勾的选项 | 条件 |
|---|---|---|
| 声明首发 | **头条首发** | **仅正文 ≥100 字符**；<100 字符跳过 |
| 作品声明 | **引用AI** | 总是勾选 |

- 选择器：`first_release_label = label:has-text('头条首发')`、`work_declare_label = label:has-text('引用AI')`。
- 声明区真实结构：`label.byte-checkbox.checkbot-item > input[type=checkbox]`。
- 勾选前先回读 `input.checked`，已勾选则跳过（避免重复点击反而取消）。
- 「作品声明 = 引用AI」为 **2026-09-14 新增**（此前脚本只勾头条首发）。

实测日志（102 字符）：

```
已勾选头条首发
已勾选作品声明：引用AI（now=True）
保存成功 toast 已出现
```

## 发布后自动清理（强制 · 用户 2026-09-09 立规）

> **「图片生成发布过后就自动删除，文章也是，不要在电脑上有留存。」**

每次发布完成（或用户审阅完交付稿）后，**必须**清掉产生的一切中间产物，电脑上不留：

```bash
python scripts/cleanup_after_publish.py          # 先 dry run 看清单
python scripts/cleanup_after_publish.py --yes    # 确认后真删
```

**每日自动清理（用户 2026-09-14 指定）**：18:00 的发布任务（slot3，当天最后一个发布任务）发完后会额外执行

```bash
python scripts/cleanup_day.py          # 带安全闸：5 组都发完才清理（先 dry run）
python scripts/cleanup_day.py --yes    # 通过后真删
```

- 安全闸：读 `articles_batch.json`，若还有 slot 的 `publish_status` 不是 published/scheduled、
  或任一 `wtt_status` 为 failed → **不清理**并返回 1（保留文件以便重试/排查）。
- 通过后调用 `cleanup_after_publish.py`，删掉当天的 `articles_batch.json`、`wtt_batch.json`、
  `images/article_inline/**`、调试截图与诊断文件。

**删什么**
1. 生成的文内配图 → `images/article_inline/`（整个目录）
2. 产出的文章 Word → 桌面 / 技能根，匹配 `*-带配图版-*.docx`、`*article*.docx`
3. 调试截图 → 技能根 `*.png`
4. 诊断 json/txt/log → 技能根，除白名单外（含每天的 `articles_batch.json` / `wtt_batch.json`）

**绝不删（删了流程就跑不动）**
- `config.json` / `toutiao_auth.json`（登录态）/ `posts.json`
- **`article_post.json`** — 稿件源。Word 随时能靠它重建，删了才真没了
- `published_topics.json(+.bak)` / `cover_url_cache.json` / `last_run.json`
- **`images/post*.png`** — 封面素材。没有封面 → 发布必失败

**两个已踩过的坑**
- 配图曾放 `Desktop\inline_imgs\`，被清理后脚本**静默**生成了一份无图 Word 覆盖掉带图的 → 配图一律存技能内 `images/article_inline/`；且构建脚本加了「缺图即 `sys.exit(1)`」硬校验。
- 本机 `Add-Type` 与 COM（`Shell.Application`）均被安全策略拦截，**没有可用的回收站 API**，只能直接删除 → 因此删前务必确认 `article_post.json` 还在。

## 复用适配

- 换赛道：改 writing-spec 第 1-2 节、content-strategy 第 1-4 节（钩子库通用）
- 换账号：删 `toutiao_auth.json` 重跑 `--login`；改 `config.json`
- 换机器：`run_on_logon.ps1` / `rearm_automation.py` 路径 + `automation_id` 需改；`config.json` 中 `workbuddy_exe`/`python_exe` 改为本机路径
