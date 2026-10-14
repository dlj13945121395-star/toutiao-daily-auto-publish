# 头条日更 · 全自动发布链路

**今日头条 / 微头条 的无人值守日更系统**：每天工作日自动完成
「抓站内话题热点 → 生成 6 篇文章 + 6 条微头条 → 生成 18 张配图 → 按 6 个时段自动发布 → 自动回评论 → 当日清理」，
全程无需人工确认。

```
话题抓取(11:00前)          内容生成(11:00)              定时发布(12:00~18:00)            收尾
┌──────────────┐      ┌──────────────────┐      ┌──────────────────────────┐      ┌──────────┐
│ fetch_topics │ ──▶  │  6 篇文章          │ ──▶  │ 12:00 slot0 微头条→文章    │ ──▶  │ 自动回评论 │
 │ (站内话题联想)│      │  6 条微头条        │      │ 14:00 slot1 + 评论回复     │      │ (14:00)  │
 │ merge_topics │      │  18 张 1:1 方图    │      │ 15:00 slot2                │      │          │
 │ + WebSearch  │      │  articles_batch   │      │ 16:00 slot5                │      │ 18:00    │
 │ 热榜         │      │  wtt_batch        │      │ 17:00 slot4                │      │ 清理当日  │
 └──────────────┘      └──────────────────┘      │ 18:00 slot3                │      │ 产物      │
                                                  │  (先发微头条，再发文章)      │      └──────────┘
                                                  └──────────────────────────┘
```

---

## 目录

- [一、账号人设与定位](#一账号人设与定位)
- [二、每日时间线（8 个自动化任务）](#二每日时间线8-个自动化任务)
- [三、环节 1 · 话题热点抓取](#三环节-1--话题热点抓取)
- [四、环节 2 · 文章 / 微头条生成](#四环节-2--文章--微头条生成)
- [五、环节 3 · 配图生成](#五环节-3--配图生成)
- [六、环节 4 · 图片位置与文章排版](#六环节-4--图片位置与文章排版)
- [七、环节 5 · 自动发布（含勾选清单）](#七环节-5--自动发布含勾选清单)
- [八、环节 6 · 话题可点击（选择器插入）](#八环节-6--话题可点击选择器插入)
- [九、环节 7 · 自动回评论](#九环节-7--自动回评论)
- [十、环节 8 · 隔日硬闸与幂等保护](#十环节-8--隔日硬闸与幂等保护)
- [十一、环节 9 · 发布后清理](#十一环节-9--发布后清理)
- [十二、文件结构](#十二文件结构)
- [十三、部署到新机器](#十三部署到新机器)
- [十四、排障铁律（踩过的坑）](#十四排障铁律踩过的坑)
- [十五、隐私与脱敏说明](#十五隐私与脱敏说明)

---

## 一、账号人设与定位

| 项 | 值 |
|---|---|
| 定位 | **普通人用 AI 搞钱 / 提效 / 避坑** |
| 内容形态 | 热点新闻见解文（概况 25% + 观点 60% + 结尾 15%） |
| 更新频率 | 工作日每天 **6 篇文章 + 6 条微头条**（周末不跑） |
| 发布平台 | 今日头条（mp.toutiao.com） |
| 语气 | 第一人称、口语化、煽动共鸣、落点压在读者自己的处境上 |

**写作规范**（`references/content-strategy.md` 是完整范本）：

- 段落极短（1~2 句成段，允许单句成段）；「我说…他说…」推进节奏
- 每篇**前 200 字内必须出现「你」**
- 去 AI 腔强制替换：首先→先说第一点、其次→再说第二个、综上所述→说白了、
  值得注意的是→但你发现没、因此→所以、此外→还有一个点、然而→但是
- 禁用词/标点：`**` 加粗（脚本不转 markdown 会原样显示星号）、冒号、破折号、
  直角引号「」、弯引号“”
- 标题 18~25 字（**硬上限 30 字，超了平台直接拒**），禁「震惊/绝了/重磅」
- 文章正文 1200~2500 字符；微头条 200~500 字符

---

## 二、每日时间线（8 个自动化任务）

全部为 **recurring**，RRULE `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR`（仅工作日）。
任务定义见 `automation_config.json`，在 WorkBuddy 自动化中心创建。

| 时间 | 任务 | 干什么 |
|---|---|---|
| 11:00 | 生成器 `automation-1789031424055` | 抓站内话题池 → WebSearch 热榜 → 生成 6 文 + 6 微头条 + 18 图，写 `articles_batch.json` / `wtt_batch.json`，**不发布** |
| 11:20 | 生成兜底守护 `bfcb8b20-…` | 自检当日批次，缺则整条重跑；**只校验+上报**，不删文件不改状态 |
| 12:00 | 发布 slot0 `automation-1789033524917` | 含生成兜底自检；先发微头条再发文章 |
| 14:00 | 发布 slot1 `automation-1789371591338` | 发布 + **评论自动回复** |
| 15:00 | 发布 slot2 `automation-1789371596649` | 发布 |
| 16:00 | 发布 slot5 `c2f0d87c-…` | 发布 |
| 17:00 | 发布 slot4 `6bf71745-…` | 发布 |
| 18:00 | 发布 slot3 `automation-1789371601835` | 发布 + `cleanup_day.py` 当日清理 |

> ⚠️ **slot 号 ≠ 时间点**：16:00=slot5、17:00=slot4、18:00=slot3。
> 微头条没有定时发布功能，每个发布时刻由本机当场发出（需电脑在线）。

---

## 三、环节 1 · 话题热点抓取

**核心原则：话题标签必须是平台侧真实存在的话题**，否则挂不上、点不进去。

### 3.1 站内话题池（主来源）

```bash
# 1) 在微头条发布页输入 #关键词，触发站内真实话题联想（含讨论数），只读不发布
python scripts/fetch_topics.py --keywords "AI,人工智能,大模型,Token,算力,智能体,副业,职场,自动化,AI编程,AI医疗,AI漫剧,AI长剧,AI剧场,如果不缺钱,超级智能" --top 12 --out topics_probe.json

# 2) 合并多批探测结果为站内话题池（按讨论数排序）
python scripts/merge_topics.py        # → topics_platform_<日期>.json
```

- 原理：发布页编辑器输入 `#关键词` 实时弹出话题联想下拉，里面就是站内真话题 + 讨论数，
  形如 `#Token经济# 913讨论`。比 WebSearch 热榜更准。
- **每个关键词都要重载一次发布页**，全程约 2~5 分钟；**只能串行跑，严禁并发**（会互相抢浏览器实例全部超时）。
- 池子要够大：合并去重后建议 **≥20 条**，保证每篇能挑到 4~5 个相关话题。

### 3.2 热榜补充

并发 WebSearch：`今日头条热榜 今日`、`抖音热榜 今日`、`AI 人工智能 热点 今日`、`科技热点 今日`。

### 3.3 汇总写入 `hot_topics_today.json`

```json
{
  "date": "YYYY-MM-DD",
  "trending": ["#站内真实话题#", "…至少 10 个"],
  "positioning": ["#AI工具#", "#人工智能#", "#副业#", "#职场效率#"],
  "fresh_topics_from_platform": ["…站内池讨论数最高的 20~40 条原样 tag"]
}
```

**⚠️ 严禁自己编话题名**。站内池里没有的一律不写；App 里显示的话题名可能与站内 tag
有出入（多逗号、措辞不同），**一律以站内池原文为准**。

**⚠️ 入池两道滤（2026-10-13 新增）**：名字含**禁标点**（：——「」“”）或**内部带空格**的
话题不能入池 —— 前者触发审计禁标点，后者会被话题行按空格拆散。

**⚠️ 查询词技巧**：站内话题联想按**短关键词**匹配，输入全名常常零候选。
`#技术有速度，人间有温度，读懂当下的人工智能#` 要输 `技术有速度` 才命中。
发布脚本已内置「全名 → 首个标点前 → 前8/6/4字」由长到短自动试探。

**兜底**：`merge_topics.py` 内置 `SHOT` 基线（App「创作邀请→话题」8 条官方推荐，平台原文可直接用）；
`fetch_topics.py` 整体失败时退化为 WebSearch 热榜 + `positioning` 常青池，并在日志标注。

---

## 四、环节 2 · 文章 / 微头条生成

由 11:00 生成器任务（agent + ImageGen + 一个 Python 落盘脚本）完成，**只生成不发布**。

### 4.1 文章（6 篇，主题互不相同）

- 结构：标题 + **概况 25%** + **观点 60%**（第一人称、煽动共鸣、落读者处境）+ **结尾 15%**（金句 + 引导评论）
- 正文 1200~2500 字符（**含末尾话题段**），`\n\n` 分段，实际经验值 **26~32 个短段**才能稳过下限
- 标题每篇出 10 个候选（数字型/反常识型/身份型/悬念型）挑 TOP3；18~25 字，硬上限 30 字
- 用 `published_topics.json` 去重，不与近 7 天已发文章重复
- 结尾必须引导评论（提问 / 二选一 / 征求意见）

### 4.2 微头条（6 条，与文章一一对应）

三段式：**钩子一句 → 引流句 → 4~5 个话题**，总长 200~500 字符。

- 不写完整观点文，负责把人带回主页看长文；钩子取对应文章里最抓人的点
- 黄金 3 秒法则：首屏前 3 行（约 50-80 字）直接决定打开率，钩子单刀直入、带具体画面或反差
- 引流句示例：「上面的只是个开头…去我主页就能翻到」

### 4.3 话题标签（文章 + 微头条都必须有）

- **每篇 / 每条 4~5 个**（2026-10-13 起由 2~3 上调，用户要求「话题太少」）
- 文章：正文**最后单独一段**，空格分隔，计入总字数
- 微头条：**最后单独一行**，空格分隔
- 每个话题都必须是 `hot_topics_today.json` 里的**原文**，优先 `fresh_topics_from_platform` 的站内原样 tag
- **相关性强制**：按正文关键词从池里挑，禁止为凑数挂无关话题；相关话题不够就回第 0 步扩充池子
- 至少 1 个当日热门 + 1 个定位话题，其余按相关度补足到 4~5 个

### 4.4 落盘与自检（生成器收尾必修）

```bash
python check_batch.py              # 字数/结构校验 → 必须 RESULT: PASS
python scripts/audit_20261008.py   # 合规审计 → 必须 AUDIT: PASS
```

审计项：话题 ∈ 今日池、文章/微头条各 4~5 个话题、标题 18~30 字、前 200 字含「你」、
无禁词禁标点、status/at 为 null、图片存在、结尾含互动引导。

### 4.5 批次文件格式

```jsonc
// articles_batch.json
{
  "generated_at": "2026-10-14T11:16:14",
  "articles": [
    {"slot": 0, "type": "article", "title": "…", "body": "…\n\n#话题A# #话题B# …",
     "cover": "post1", "inline_images": ["s0_a.png", "s0_b.png", "s0_c.png"],
     "settings": {"first_release": "头条首发", "work_declare": "引用AI"},
     "published_at": null, "publish_status": null}
  ]
}

// wtt_batch.json（纯 list，无 status 字段）
[{"slot": 0, "body": "钩子…引流句…\n#话题A# #话题B# …", "images": ["article_inline/s0_a.png"]}]
```

> 完整脱敏样例见 [`docs/examples/`](docs/examples/)。

---

## 五、环节 3 · 配图生成

### 5.1 样式规范

| 项 | 规范 |
|---|---|
| 数量 | **18 张**（6 篇文章 × 3 张） |
| 比例 | **1:1 正方形**（实测与范本一致） |
| 内容 | 无文字插图，prompt 强调 `no readable text` |
| 风格 | 与文章主题相关的现代扁平插画 / 概念性编辑插画 |
| 命名 | `s{N}_a.png` / `s{N}_b.png` / `s{N}_c.png`（N=slot 0~5，a/b/c=同组第 1/2/3 张） |
| 后处理 | **裁底 172px 去水印**，清单优先重命名（`_rename_manifest.json` → `scripts/rename_today_images.py`） |

### 5.2 关键经验

- ⚠️ **每条 prompt 开头用互不相同的英文词** —— 落盘名 = 提示词首词 + 秒级时间戳，
  同词同秒会**同名覆盖丢图**。首词如 `Excavator_cab…`、`Notebook_flatlay…`
- ⚡ **18 张必须并行生成**：同一条消息内并发发起多张 ImageGen 调用（建议每批 5 张，4 批跑完），
  全部 `output_dir` 指向 `images/article_inline/`
- 生成后按清单重命名 + 裁底；有非 `s` 开头残留 png 即非 0 退出

---

## 六、环节 4 · 图片位置与文章排版

### 6.1 文章 = 文 + 图交替（3 张）

- 排版：**文字 + 图片 + 文字 + 图片 + 文字 + 图片**
- 位置算法（`publish_article_draft.py` 的 `compute_image_positions`）：
  在 N 个段落之间**均匀插 3 张图，避开首尾**（范本实测：10 段文字时落在第 2/5/8 段后）
- 段落太少仍有剩余图时追加到结尾；插图失败不中断（文章仍会带封面发出）
- ⚠️ 插图面板必须关掉，否则挡住后续「封面」弹窗（曾导致封面上传卡死）

### 6.2 微头条 = 文 + 图（1 张）

- 文字在前、1 张图在后，**复用对应文章首图 `s{N}_a.png`，不新生成**

### 6.3 话题段位置

- 文章：正文**最后单独一段**（`\n\n` 分隔），计入字数
- 微头条：**最后单独一行**（`\n` 分隔）

---

## 七、环节 5 · 自动发布（含勾选清单）

### 7.1 发布编排（`scripts/run_one_slot.py --slot N`）

```bash
python scripts/run_one_slot.py --slot 0            # 12:00 立即发布（先微头条后文章）
python scripts/run_one_slot.py --slot 1 --batch X  # 指定历史批次（人工补发）
python scripts/run_one_slot.py --slot 0 --dry-run  # 只写 payload 不发布
python scripts/run_one_slot.py --slot 0 --skip-wtt # 只发文章
```

- **用户指定顺序：先发微头条，再发文章**
- 发布前跑 `stale_guard()` 隔日硬闸（见环节 8）
- 成功后把该 slot 状态回写批次、只删本 slot 的图（`s{N}_*.png`）
- ⚠️ **部分发布后禁止重跑 `run_one_slot`**（会重复发微头条）→ 文章单独重跑
  `publish_article_draft.py article_post.json`

### 7.2 文章侧勾选（`publish_article_draft.py` 第 4 步，全自动）

| 开关 | 规则 |
|---|---|
| **投放广告赚收益** | ✅ 总是勾（默认不勾，需主动点） |
| **声明首发「头条首发」** | ✅ 正文 ≥100 字符才勾（文章都 ≥300，故总勾） |
| **同时发布微头条** | 仅正文 <100 字符时平台才提供该开关（长文选不了 → 走独立微头条发布） |
| **作品声明「引用AI」** | ✅ 总是勾 |

### 7.3 微头条侧勾选（`publish_draft.py`，全自动）

| 开关 | 规则 |
|---|---|
| **头条首发** | ✅ 正文 ≥100 字符才勾（微头条 200+，故总勾） |
| **作品声明「引用AI」** | ✅ 总是勾（已勾选则跳过，避免重复点击反而取消） |

> 微头条编辑器只有「存草稿 / 发布」，没有定时发布，所以到点当场发布。
> `:has-text`（连字符）是无效 CSS，勾选必须用 `:has-text`，否则静默失败。

### 7.4 成功判据（唯一权威）

- `article_capture.json` 的 `published == true` / **首页最近作品命中**
- ⚠️ 7050：流程中间出现 = 非致命自动保存噪声；**最终「预览并发布」签名请求上出现 = 硬失败**
- ⚠️ 文章 rc=1 可能是**假阴性**（发布刚落地时即时单次检查查不到）→ 先跑
  `scripts/verify_published.py "<标题前12字>"`（内置 5 轮刷新）确认，别急着重跑

---

## 八、环节 6 · 话题可点击（选择器插入）

**2026-10-12 用户反馈修复**：文章末尾的 `#话题#` 点不动、微头条的能点。

**根因**：`publish_draft.py` 原来用 `insert_text` 整段纯文本写入。
**两个编辑器都不会**把纯文本 `#话题#` 自动变成可点击链接（早期「微头条会自动识别」的判断已实测推翻）。

**修复**：两边都走编辑器的**话题选择器**：

```
敲 # → 弹出 section.mention-selector-modal.forum
     → 候选项 section.forum-list-item（文本在 .forum-list-item-text，含「N讨论」）
     → 点选 → 插入 <a class="tteditor-forum" data-name=... data-concern-id=...>#话题#</a>
     （这才是可点击、能跳转的话题节点）
```

- 发布前用 `split_trailing_topics()` 把正文末尾单独一段/行的话题拆出来再逐个点选
- **多查询词自动试探**：全名 → 首个标点前 → 前 8/6/4 字，由长到短；零候选就退格换更短的
- 联想服务偶发瞬时无响应（实测 2/7 概率）→ 整串查询词都没出现过候选时，等 2.5s 整体重跑一轮
- 三道保险：① 每话题单独 try 兜住，最坏退化为纯文本**绝不中断发布**；② 无候选也退化纯文本
  （宁可点不动，也不挂错话题）；③ 跳过面板里的「创建话题」按钮，避免造垃圾话题
- 插入后校验并打印：`话题插入完成 X/N 个；可点击话题节点数 = M`
- ⚠️ 面板打开时敲空格 = 取消插入，多话题之间的空格只在面板关闭后敲
- 校准工具（只读）：`scripts/inspect_article_topics.py` / `scripts/inspect_wtt_topics.py`
- 发布前抽查：`scripts/verify_live_topics.py --slots 1,2,3,4,5`（逐话题实测 HIT/NEAR/MISS）

---

## 九、环节 7 · 自动回评论

挂在 **14:00 任务**上（发布 slot1 之后执行），幂等，回复过的不二次回复。

```bash
# 1) 抓待回复评论（入口 https://mp.toutiao.com/profile_v4/manage/comment/all）
python scripts/fetch_comments.py            # → replies.json（text 只写正文，去掉前缀）

# 2) 把回复写进 replies.json（格式见 reply_comment.py 顶部注释）

# 3) 发送（不加 --send 只预演）
python scripts/reply_comment.py --plan replies.json --send
```

- 入口：`https://mp.toutiao.com/profile_v4/manage/comment/all?enter_from=left_menu`
- **幂等两道闸**：① `replied_comments.json` 台账已有该 key → 跳过；
  ② 页面上该评论已有回复（全部 N 条回复 ≥1）→ 跳过并补记台账
- 定位用归一化匹配（剥离 emoji 与标点，只留文字字母数字），含 emoji 评论也能命中
- 回复正文上限 300 字符，超出自动截断
- 部分失败 rc=1（成功不回滚），上报「失败 M 条」即可

---

## 十、环节 8 · 隔日硬闸与幂等保护

### 10.1 隔日批次硬闸（2026-10-12 新增，用户要求）

`run_one_slot.py` 发布前跑 `stale_guard()`，**两项必须同时满足**，否则 **exit 3 拒发**：

| 检查项 | 判据 |
|---|---|
| 文章批次 | `articles_batch.json` 的 `generated_at` 日期 **== 今天** |
| 微头条批次 | 同目录 `wtt_batch.json` 的**文件修改日期 == 今天** |

- 人工补发历史批次：显式加 `--allow-stale` 放行，日志打印「人工补发模式」
- 宁可少发，也**绝不在今天发出隔日旧内容**
- 微头条批次路径跟随 `--batch` 同目录，避免「文章用旧批、微头条用新批」
- `article_post.json` 带溯源字段 `source_generated_at`，事后可追溯

### 10.2 其他幂等闸

- 批次状态为 `published`/`scheduled` 的 slot 自动跳过
- `failed` 允许补一次重试，避免重复提交同样被拦死
- 一键只读体检：`python scripts/verify_today_batch.py`（批次日期 / wtt mtime / 今日话题 /
  标题零重复 / 配图齐备，全绿才发）

---

## 十一、环节 9 · 发布后清理

18:00 最后一组发完后执行（`scripts/cleanup_day.py --yes`）：

- **安全闸**：还有 slot 未 published/scheduled、或有 wtt failed → **不清理**，保留文件以便重试
- 清理动作：删 `articles_batch.json` / `wtt_batch.json` / `images/article_inline/**` / 调试截图
- **保留**：`config.json`、`toutiao_auth.json`、`published_topics.json`（去重）、
  `replied_comments.json`（回评去重）、封面 `post*.png`、所有脚本
- ⚠️ `cleanup_after_publish.py` 会无差别删 `images/article_inline/**` 与根下非 KEEP 的 json，
  **只在当天全发完后用**；定向清理前先断言「根批次是今天的 + 图齐 18 张」

---

## 十二、文件结构

```
toutiao-weitoutiao-auto-publish/
├── README.md                     # 本文件 · 全链路工程文档
├── SKILL.md                      # agent 执行规范（触发场景/工作流/调度/坑）
├── DEPLOY.md                     # 换机器部署指南
├── config.json                   # 配置 + 全部选择器（含话题选择器校准记录）
├── automation_config.json        # 8 个自动化任务的完整定义（id/rrule/prompt）
├── check_batch.py                # 批次字数结构校验
├── check_draft.py / check_wtt.py
├── hot_topics_today.json         # 当日话题池（trending/positioning/fresh）
├── published_topics.json         # 已发布去重台账
├── replied_comments.json         # 已回评论去重台账
├── images/
│   ├── post1~3.png               # 封面素材（发布必需）
│   └── article_inline/           # 当日 18 张配图 s0_a~s5_c（发后即清）
├── references/
│   ├── content-strategy.md       # 写作规范 + 内容策略（含 §8 话题规范）
│   └── DEPLOY.md
└── scripts/
    ├── fetch_topics.py           # 站内话题联想抓取（只读）
    ├── merge_topics.py           # 多批探测合并为站内话题池
    ├── run_one_slot.py           # 发布编排（隔日硬闸 + 先微头条后文章）
    ├── publish_article_draft.py  # 文章发布（插图/勾选/话题选择器/封面）
    ├── publish_draft.py          # 微头条发布（勾选/话题选择器）
    ├── fetch_comments.py         # 抓待回复评论
    ├── reply_comment.py          # 按计划回复评论（幂等）
    ├── cleanup_day.py            # 当日清理（安全闸）
    ├── cleanup_after_publish.py  # 总清理
    ├── rename_today_images.py    # 图片清单重命名 + 裁底去水印
    ├── audit_20261008.py         # 合规审计（话题数/禁词/禁标点/字数）
    ├── verify_today_batch.py     # 一键只读体检（今日批次）
    ├── verify_live_topics.py     # 发布前逐话题实测可点性
    ├── verify_published.py       # 首页最近作品核验（5 轮刷新）
    ├── guard_verify.py           # 标题唯一/零重复/图齐/status 全 null
    ├── rearm_automation.py       # 直写 next_run_at（工具调用会重置）
    ├── setup_new_machine.py      # 换机器一键部署 + 登录
    └── run_on_logon.ps1          # 开机补跑兜底
```

---

## 十三、部署到新机器

```powershell
# 1) 拷贝技能目录到 C:\Users\<用户名>\.workbuddy\skills\
# 2) 装依赖
& "<托管python>" -m pip install playwright
& "<托管python>" -m playwright install chromium
# 3) 一键部署（自动探测本机 Python/WorkBuddy/Edge 路径写回 config.json）
& "<python>" "<技能目录>\scripts\setup_new_machine.py"
# 4) 登录（登录态不能跨机器复制，必须重新扫码）
& "<python>" "<技能目录>\scripts\setup_new_machine.py" --login
# 5) 按 automation_config.json 的 tasks 逐个创建自动化任务
# 6) 用 rearm_automation.py --at <epoch毫秒> 逐个直写 next_run_at
```

⚠️ `automation_update` 每次调用都会**重置** `next_run_at`（改排程/改名/改状态都会），
且工具返回值可能与实际写库值不一致，**必须直接读 `workbuddy.db` 核对**。

---

## 十四、排障铁律（踩过的坑）

1. **隔日批次硬闸** exit 3 = 批次不是今天生成的，人工补发才加 `--allow-stale`
2. **7050**：中间自动保存 = 非致命；最终「预览并发布」签名请求上 = 硬失败。
   判成功唯一权威 = `article_capture.json.published` / 首页最近作品命中
3. **文章 rc=1 可能是假阴性**（即时单次检查查不到刚落地文章）→ 先跑
   `verify_published.py` 确认，别重跑（会重复发文）
4. **文章脚本崩后禁止重跑 `run_one_slot`**（会重复发微头条）→ 单独重跑
   `publish_article_draft.py article_post.json`
5. **话题搜不到先分两类**：查询词太长（改查询词即可，发布脚本已自动处理）vs
   话题真不存在（必须换站内真话题）
6. **发布侧 Bash 命令可能被执行两次**（沙箱升级批准）→ 删除脚本一律写成
   「存在才删」的幂等形式，并用独立复核命令确认最终状态
7. **`:has-text` 是无效 CSS**，勾选复选框必须用 `:has-text`，否则静默失败
8. **登录态不能跨机器复制**；封面 `images/post*.png` 必须一起拷（缺失则发布失败）
9. **本机 PATH 常坏** → 一律用绝对路径调托管 python
10. **反引号坑**：`python -c "…"` 双引号内的反引号会被 bash 命令替换、静默写坏文件
    → 含反引号/`$` 的长文本用 Write/Edit 工具

---

## 十五、隐私与脱敏说明

本仓库**只包含链路代码与文档**，以下内容已通过 `.gitignore` 排除，**不在仓库中**：

| 排除项 | 原因 |
|---|---|
| `toutiao_auth.json` | 登录态（cookie），严禁外传 |
| `published_topics.json` / `replied_comments.json` | 运营台账，含已发布内容 |
| `articles_batch.json` / `wtt_batch.json` / `hot_topics_today.json` / `topics_platform_*.json` / `topics_probe*.json` | 当日生成批次与话题池 |
| `gen_batch_*.py` | 生成器一次性落盘脚本，内含文章全文 |
| `images/article_inline/*.png` | 当日配图（发后即清） |
| `.workbuddy/memory/` | 内部工作日志 |
| 各种 `*.bak_*` / `*.log` / 调试截图 | 临时产物 |

如需查看批次/话题池的真实格式，见 [`docs/examples/`](docs/examples/) 下的脱敏样例。

---

## 附：常用命令速查

```bash
# 发布前体检（只读）
python scripts/verify_today_batch.py

# 实测话题可点性（只读，逐话题 HIT/NEAR/MISS）
python scripts/verify_live_topics.py --slots 1,2,3,4,5

# 抓站内话题池
python scripts/fetch_topics.py --keywords "AI,Token,副业" --top 12 --out topics_probe.json
python scripts/merge_topics.py

# 发布一个 slot（先微头条后文章）
python scripts/run_one_slot.py --slot 0

# 人工补发历史批次
python scripts/run_one_slot.py --slot 1 --batch _backfill/articles_batch.json --allow-stale

# 评论回复
python scripts/fetch_comments.py
python scripts/reply_comment.py --plan replies.json --send

# 当日清理（18:00 最后一组发完后）
python scripts/cleanup_day.py --yes
```
