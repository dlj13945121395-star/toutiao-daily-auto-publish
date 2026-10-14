#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_article_draft.py — PUBLISH AN ARTICLE (live) via 预览并发布 -> 确认发布.

CORRECTED 2026-09-09 15:45 — earlier I wrongly reported this "saves to draft box":
  - 确认发布 is a REAL publish. The article goes LIVE.
  - /profile_v4/index is the HOMEPAGE (最近作品 = published items), NOT the draft box.
    The earlier "draft_hits" came from that URL and was a false positive.
  - The draft box (/profile_v4/manage/draft) was actually EMPTY (共 0 条内容).
  - This account has NO working "save article as draft" path: the editor's autosave
    always returns 7050 保存失败. The only request that succeeds (code 0) is the signed
    one fired by 预览并发布 -> 确认发布 (it carries msToken + a_bogus).

So the working publish path is:
  fill title/body/cover/settings -> click 预览并发布 -> click 确认发布
  -> signed request returns code 0 -> the article is PUBLISHED (live).

Settings applied every run (idempotent: only checks, never unchecks):
  声明首发 = 头条首发
  作品声明 = 引用AI

OLD BUG (fixed): clicking 引用AI with `label.byte-checkbox:has_text(...)` — the
underscore form is INVALID CSS and throws a querySelectorAll SyntaxError, so the box
was never checked. Must use `:has-text` (hyphen), or the JS DOM dispatch used below.

Verification uses the homepage 最近作品 list, because /graphic/post (作品管理) often
renders blank in automation.
"""
import datetime, hashlib, json, os, re, subprocess, sys, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
DEFAULT_CONFIG = os.path.join(SKILL_ROOT, "config.json")
DEFAULT_INPUT = os.path.join(SKILL_ROOT, "article_post.json")
SCRIPTS_DIR = HERE  # 本脚本所在目录（scripts/）


# ---------------------------------------------------------------------------
# 微头条：原生「同时发布微头条」为主，补发仅作兜底
# ---------------------------------------------------------------------------
# 根因（2026-09-14 定位）：
#   「确认发布」请求的 extra 里，微头条开关字段叫 tuwen_wtt_trans_flag，
#   和编辑期自动保存用的 tuwen_wtt_transfer_switch 不是同一个字段；
#   而且预览页重新序列化表单时，tuwen_wtt_trans_flag 被置为 "0"。
#   所以之前无论怎么点 UI 开关、或按错误字段名注入，服务端都收不到开关。
# 修复：在 _patch_publish 路由里把两个字段都强制置 "1"，由服务端原生带出微头条。
# 兜底：若账号原生同步仍不生效，用 WTT_FALLBACK=1 启用下面的补发函数。
def _wtt_clean_punct(s):
    return (s.replace("：", "，").replace("—", "，").replace("“", "")
             .replace("”", "").replace('"', "").replace("「", "").replace("」", ""))


def _wtt_first_sentences(text, n=2, max_len=90):
    parts = re.split(r"[。！？\n]", text)
    parts = [p.strip() for p in parts if p.strip()]
    out = []
    for p in parts:
        out.append(p)
        if len(out) >= n:
            break
    lead = "。".join(out) + "。"
    if len(lead) > max_len:
        lead = lead[:max_len].rstrip("，。") + "。"
    return lead


_WTT_TAG_POOL = [
    ("AI", "#AI工具"), ("智能体", "#人工智能"), ("自动化", "#效率"),
    ("agent", "#AI工具"), ("写作", "#写作"), ("职场", "#职场"),
    ("副业", "#副业"), ("头条", "#自媒体"), ("流量", "#运营"),
]
_WTT_DEFAULT_TAGS = ["#AI工具", "#人工智能", "#效率"]
_WTT_FUNNELS = [
    "上面的只是个开头。完整怎么搭、踩过哪些坑，我写成一篇长文了，去我主页就能翻到。",
    "这点展开能讲一整篇。我把步骤和避坑都整理成长文，放在我主页了，想看的自己去翻。",
    "话说到这儿。更细的玩法我单独写了篇长文，去我主页找就行。",
    "就先说这些。剩下的门道我整理成一篇长文放主页了，感兴趣的去看。",
]


def _wtt_pick_tags(text):
    tags = []
    for kw, tag in _WTT_TAG_POOL:
        if kw.lower() in text.lower() and tag not in tags:
            tags.append(tag)
        if len(tags) >= 3:
            break
    return (tags or list(_WTT_DEFAULT_TAGS))[:3]


def publish_linked_microblog(post, cfg, images_dir):
    """文章发布成功后显式补发一条引流微头条。返回 (ok: bool, info: str)。"""
    title = (post.get("title") or "").strip()
    body = (post.get("body") or "").strip()
    inline = post.get("inline_images") or []
    lead = _wtt_clean_punct(_wtt_first_sentences(body, n=2))
    funnel = _WTT_FUNNELS[hash(title) % len(_WTT_FUNNELS)]
    tags = _wtt_pick_tags(title + " " + body)
    wtt_body = f"{lead}\n\n{funnel}\n\n" + " ".join(tags)
    chosen = ["article_inline/" + inline[0]] if inline else []
    wtt = [{"body": wtt_body, "images": chosen}]
    wtt_path = os.path.join(SKILL_ROOT, "wtt_post.json")
    json.dump(wtt, open(wtt_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"   生成引流微头条: {lead[:28]}... (配图: {chosen or '无'})")
    py = cfg.get("python_exe") or sys.executable
    script = os.path.join(SCRIPTS_DIR, "publish_draft.py")
    cmd = [py, script, "--publish", "--posts", wtt_path, "--force"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=360)
        out = (r.stdout or "") + (r.stderr or "")
        ok = (r.returncode == 0) or ("发布成功" in out) or ("DONE" in out)
        log(f"   微头条发布 subprocess rc={r.returncode}")
        for line in out.strip().splitlines()[-8:]:
            if line.strip():
                log("     | " + line.strip()[:120])
        return ok, out[-200:]
    except Exception as e:
        log(f"   ⚠️ 微头条发布异常: {e}")
        return False, str(e)


def log(m): print(f"[article] {m}", flush=True)

def safe_click(loc, desc, t=6000):
    try:
        loc.click(force=True, timeout=t); log(f"  ok {desc}"); return True
    except Exception as e:
        log(f"  -- {desc}: {str(e)[:90]}"); return False

def cell_of(page, label):
    return page.locator(".pgc-edit-cell").filter(has=page.locator(".edit-label", has_text=label))


def ensure_wtt_switch_editor(page):
    """（保留备用 · 当前未被调用）勾选文章编辑器的「同时发布微头条」开关。

    ⚠️ 2026-09-14 起本函数**不再被调用**：用户明确要求文章的「同时发布微头条」不勾选；
    且文章正文都 ≥300 字符，头条本就不提供该开关（≥100 字符选不了）。保留以备将来需要。

    历史说明：用 Playwright 真实点击而非 JS 直接 .click()，React 才能捕获状态切换；
    已勾选时先取消再勾选，确保产生完整 change。
    """
    try:
        cell = cell_of(page, "同时发布微头条").first
        if cell.count() == 0:
            # 兜底：按收益文案定位
            cell = page.locator(".pgc-edit-cell").filter(has=page.locator("text=发布得更多收益")).first
        if cell.count() == 0:
            log("  -- 编辑器未找到「同时发布微头条」设置项")
            return
        inp = cell.locator("input[type=checkbox]").first
        lab = cell.locator("label").filter(has_text="发布得更多收益").first
        target = lab if lab.count() > 0 else inp
        if inp.count() > 0 and inp.is_checked():
            # 已勾选时先点一次取消，再点一次勾选，确保 React 看到完整切换
            target.click(force=True, timeout=3000); time.sleep(0.5)
        target.click(force=True, timeout=3000); time.sleep(0.5)
        log(f"  ok 编辑器「同时发布微头条」已勾选: checked={inp.is_checked() if inp.count()>0 else '?'}")
    except Exception as e:
        log(f"  -- 编辑器微头条开关异常: {str(e)[:80]}")


def compute_image_positions(total, n):
    """在 total 个段落之间均匀插入 n 张图，避开首尾，返回『插在第几段之后』的下标列表。"""
    if n <= 0 or total < 2:
        return []
    pos = []
    for k in range(n):
        idx = int(round((k + 1) * total / (n + 1))) - 1
        idx = max(0, min(total - 2, idx))
        pos.append(idx)
    # 去重：若两张图落同一段后，后移
    seen, out = set(), []
    for p in pos:
        while p in seen and p < total - 2:
            p += 1
        seen.add(p)
        out.append(p)
    return out


def _toast_visible(page):
    try:
        return page.locator(".byte-toast:has-text('保存失败'), div[class*='toast']:has-text('保存失败')").filter(visible=True).count() > 0
    except Exception:
        return False

def wait_no_toast(page, timeout=8000):
    """频繁弹出的「保存失败」toast 会遮挡 force 点击，点击前先等其消失。"""
    end = time.time() + timeout / 1000.0
    while time.time() < end:
        if not _toast_visible(page):
            time.sleep(0.3)
            return
        time.sleep(0.4)

def resolve_img(rel, images_dir):
    """按相对名解析真实图片路径：兼容无扩展名、article_inline 子目录。"""
    if not rel:
        return None
    if os.path.isabs(rel) and os.path.exists(rel):
        return rel
    cands = [rel, rel + ".png", rel + ".jpg", rel + ".jpeg",
             os.path.join("article_inline", rel),
             os.path.join("article_inline", rel + ".png"),
             os.path.join("article_inline", rel + ".jpg")]
    for c in cands:
        p = os.path.join(images_dir, c)
        if os.path.exists(p):
            return p
    return None

TOPIC_ITEM = ".mention-selector-modal .forum-list-item"


def _norm_topic(s):
    """话题名归一化：去掉空白、井号、零宽字符，便于模糊匹配。"""
    return re.sub(r"[\s#\u200b\u200c\u200d]+", "", s or "")


def split_trailing_topics(body):
    """把正文末尾「单独一段、只由 #话题# 组成」的话题行拆出来。

    返回 (paras, topics)：
      paras  —— 去掉话题行后的段落列表（用于写正文、算插图位置）
      topics —— 话题名列表，如 ['AI工具', '副业']；没有话题行时为空列表

    ⚠️ 2026-09-30 根因修复：生成器按规范把 2~3 个 `#话题#` 放在正文末尾一段
    （计入 1200~2500 字数），但**纯文本 `#话题#` 在文章编辑器里不会变成可点击话题**
    （微头条编辑器会自动识别，文章不会）。所以文章侧必须把这行拆出来，
    改由「话题选择器」（敲 # 弹出 .mention-selector-modal）插入成真正的话题节点。
    """
    paras = [x for x in body.split("\n\n") if x.strip()]
    if len(paras) < 2:
        paras = [x for x in body.split("\n") if x.strip()]
    topics = []
    if paras:
        last = paras[-1].strip()
        found = re.findall(r"#([^#\n]+?)#", last)
        residue = re.sub(r"#[^#\n]+?#", "", last).strip()
        # 整段必须只由 #...#（可带空格分隔）构成，才认定是话题行
        if found and not residue:
            topics = [t.strip() for t in found if t.strip()]
            paras = paras[:-1]
    return paras, topics


_TOPIC_SPLIT = re.compile(r"[，,。.、！!？?；;：:（）()【】\[\]]")


def topic_queries(name):
    """给出「由长到短」的试探查询词：全名 → 首个标点前 → 前8/6/4 字。

    2026-10-12 实测：站内话题联想的匹配是**按短关键词**做的 —— 输入全名常常零候选，
    但输入它的前半段就能命中同一条话题。例：
      `技术有速度，人间有温度，读懂当下的人工智能` → 输「技术有速度」命中；
      `AI编程正在重塑Java团队协作模式` → 输「AI编程」命中。
    """
    qs = [name]
    head = _TOPIC_SPLIT.split(name)[0].strip()
    if head and head != name:
        qs.append(head)
    for n in (8, 6, 4):
        if len(name) > n:
            qs.append(name[:n])
    seen, out = set(), []
    for q in qs:
        q = (q or "").strip()
        if len(q) >= 2 and q not in seen:
            seen.add(q)
            out.append(q)
    return out


def _run_article_topic_queries(page, name):
    """跑一轮查询词（全名→首个标点前→前8/6/4字）。返回 (picked, saw_candidate)。"""
    target = _norm_topic(name)
    saw = False
    for q in topic_queries(name):
        try:
            page.keyboard.type("#", delay=90)
            page.wait_for_selector(TOPIC_ITEM, timeout=5000)
        except Exception:
            try:
                page.keyboard.press("Backspace")   # 面板没弹出，删掉刚敲的 #
            except Exception:
                pass
            continue
        page.keyboard.type(q, delay=50)
        time.sleep(1.5)
        items = page.locator(TOPIC_ITEM)
        try:
            n = items.count()
        except Exception:
            n = 0
        if n > 0:
            saw = True
        # 先精确命中 .forum-list-item-text；再退一步做子串命中。
        # ⚠️ 一律跳过「创建话题」（div.create-forum-button）——否则话题名不存在时
        #    子串匹配会点中「创建话题 xxx」，在平台上误建脏话题。
        for exact in (True, False):
            for j in range(n):
                try:
                    if items.nth(j).locator(".create-forum-button").count() > 0:
                        continue
                    txt = items.nth(j).locator(".forum-list-item-text").inner_text()
                except Exception:
                    continue
                t = _norm_topic(txt)
                if target and (t == target if exact else target in t):
                    items.nth(j).click()
                    log(f"  ok 话题已插入: #{txt.strip()}#（查询词「{q}」）")
                    return True, saw
        # 本查询词没命中 → 敲的 `#`+查询词原样退格清掉，换更短的查询词再试
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        for _ in range(len(q) + 1):
            page.keyboard.press("Backspace")
        time.sleep(0.25)
    return False, saw


def insert_article_topics(page, topics):
    """在正文末尾用「话题选择器」插入话题，生成**可点击话题**。

    流程：回车起新段 → 敲 `#` 打开 .mention-selector-modal（forum 面板）→
    输入查询词过滤 → 命中候选就点选（插入话题节点）。
    全名搜不到时**自动换更短的查询词重试**（长标题常常搜不到，见 topic_queries）；
    若一次候选都没出现过（联想服务偶发瞬时无响应），等一会儿整体再跑一轮。
    全都搜不到才退化为纯文本 `#话题#`（不挂错话题）。返回点选成功数。
    """
    ok = 0
    if topics:
        # 插图后光标位置不确定，先把光标移到文末，保证话题追加在正文最后
        try:
            page.locator(".ProseMirror").first.click(force=True)
            page.keyboard.press("Control+End")
            time.sleep(0.3)
        except Exception:
            pass
    for i, raw in enumerate(topics):
        name = re.sub(r"[#\s]+", "", raw or "")
        if not name:
            continue
        try:
            if i == 0:
                page.keyboard.press("Enter")
            else:
                page.keyboard.type(" ", delay=60)
            picked, saw = _run_article_topic_queries(page, name)
            if not picked and not saw:
                time.sleep(2.5)
                picked, saw = _run_article_topic_queries(page, name)
            if picked:
                ok += 1
            else:
                page.keyboard.insert_text(f"#{name}#")
                log(f"  -- 话题「{name}」无匹配候选，退化为纯文本")
            time.sleep(0.8)
        except Exception as e:  # noqa: BLE001
            log(f"  -- 话题「{name}」插入异常: {str(e)[:80]}")
            try:
                page.keyboard.insert_text(f"#{name}#")
            except Exception:
                pass
    return ok


def insert_inline_image(page, fname, images_dir):
    """在文章正文(.ProseMirror)光标处插入一张本地图片。复用与微头条相同的
    .upload-image-panel 上传面板。返回 True 表示 .ProseMirror 内 img 数增加。
    频繁弹出的「保存失败」toast 会遮挡 force 点击，故关键点击前先 wait_no_toast，
    并对整段流程做最多 3 次重试。"""
    abs_path = os.path.join(images_dir, "article_inline", fname) if not os.path.isabs(fname) else fname
    if not os.path.exists(abs_path):
        log(f"  -- 插图文件不存在: {abs_path}")
        return False
    before = page.locator(".ProseMirror img").count()
    for attempt in range(3):
        try:
            wait_no_toast(page)
            # 打开插图面板（优先真实点击避开遮挡；失败再 force 兜底）
            try:
                page.locator(".syl-toolbar-tool.image").first.click(timeout=8000)
            except Exception:
                page.locator(".syl-toolbar-tool.image").first.click(force=True, timeout=8000)
            time.sleep(2)
            panel = page.locator(".upload-image-panel")
            # 面板可能要先点「本地上传」才出现 file input
            if panel.locator("text=本地上传").count() > 0:
                try:
                    panel.locator("text=本地上传").last.click(timeout=5000)
                except Exception:
                    panel.locator("text=本地上传").last.click(force=True, timeout=5000)
                time.sleep(1)
            fi = panel.locator("input[type='file']").first
            fi.wait_for(state="attached", timeout=8000)
            fi.set_input_files(abs_path, timeout=15000)
            time.sleep(7)
            thumb = panel.locator(".img-wrap img").last
            thumb.wait_for(state="visible", timeout=15000)
            try:
                thumb.click(timeout=5000)
            except Exception:
                thumb.click(force=True, timeout=5000)
            time.sleep(1)
            wait_no_toast(page)
            ok_btn = page.locator("button:has-text('确定')").last
            if ok_btn.count() > 0:
                try:
                    ok_btn.click(timeout=8000)
                except Exception:
                    ok_btn.click(force=True, timeout=8000)
            time.sleep(2)
            # 关键：插图面板必须关掉，否则会挡住后续「封面」弹窗（曾导致封面上传卡死）
            try:
                page.locator(".upload-image-panel").first.wait_for(state="detached", timeout=6000)
            except Exception:
                try:
                    page.keyboard.press("Escape"); time.sleep(1)
                except Exception:
                    pass
        except Exception as e:
            log(f"  -- 插图异常(第{attempt+1}次): {str(e)[:100]}")
        after = page.locator(".ProseMirror img").count()
        if after > before:
            log(f"  ok 正文插图已插入 ({fname})")
            return True
        # 未成功：关掉可能残留的面板再重试
        try:
            page.keyboard.press("Escape"); time.sleep(1)
        except Exception:
            pass
        log(f"  -- 插图未生效（第{attempt+1}次），重试")
    log("  -- 插图后未检测到 img 增加，可能失败")
    return False


def _pick_select(page, sel_cls, candidates, desc):
    """点开 byte-select 下拉，选中文本命中 candidates 任一项。
    用 Playwright **真实点击**（不 force、不走 JS .click()）——React 合成事件
    需要完整的可交互点击序列，force/JS click 常导致状态不同步。
    candidates 传列表是为了兼容「4 / 04」「0 / 00」两种渲染。返回 bool。"""
    if isinstance(candidates, str):
        candidates = [candidates]
    # 1) 真实点击打开下拉
    try:
        page.locator(f".{sel_cls}").first.click(timeout=6000)
    except Exception as e:
        log(f"  -- {desc} 点开失败: {str(e)[:80]}")
        return False
    time.sleep(1.5)
    # 2) 按候选顺序，真实点击匹配到的选项
    for want in candidates:
        opt = page.locator(f".byte-select-option:text-is('{want}')")
        if opt.count() > 0:
            try:
                opt.first.click(timeout=5000)
                log(f"  {desc} -> {want}")
                time.sleep(1.0)
                return True
            except Exception as e:
                log(f"  -- {desc} 点选项 {want} 失败: {str(e)[:80]}")
    # 全部未命中：列出可选项便于排查
    try:
        avail = page.evaluate(
            "() => Array.from(document.querySelectorAll('.byte-select-option'))"
            ".slice(0,15).map(o => (o.innerText||'').trim())")
    except Exception:
        avail = "?"
    log(f"  -- {desc} 未命中 {candidates}；可选项: {avail}")
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    return False


def scheduled_publish(page, when_dt):
    """走『定时发布』：定时发布按钮 -> 选日期/时/分 -> 预览并定时发布。
    when_dt 为 datetime。头条硬约束：只能选『当前时间 +2 小时 ~ +7 天』。
    返回 True 表示已提交排程（不保证已发，发出由头条服务器到点执行）。"""
    now = datetime.datetime.now()
    delta = (when_dt - now).total_seconds()
    if delta < 2 * 3600:
        when_dt = now + datetime.timedelta(minutes=130)
        log(f"⚠️ 目标不足 2 小时（{int(delta / 60)} 分钟），头条拒绝；自动顺延到 {when_dt:%m-%d %H:%M}")
    elif delta > 7 * 24 * 3600:
        log("⚠️ 目标超过 7 天，头条拒绝；改为直接发布")
        return False

    log(f"6/6 定时发布 -> 目标 {when_dt:%Y-%m-%d %H:%M} ...")
    # 优先点「可见」的那个按钮（避免命中隐藏的重复按钮）；force 点击会被
    # 频繁弹出的「保存失败」toast 遮罩吃掉，故优先真实点击（自动等待可交互），
    # 再配合最多 3 次重试 + 弹窗轮询，规避 toast 遮挡导致的「点到了但没开弹窗」。
    timer_btns = page.locator("button:has-text('定时发布')")
    timer_btn = timer_btns.last
    try:
        if timer_btns.count() > 1:
            for i in range(timer_btns.count()):
                if timer_btns.nth(i).is_visible():
                    timer_btn = timer_btns.nth(i)
                    break
    except Exception:
        pass
    opened = False
    for attempt in range(3):
        try:
            timer_btn.click(timeout=8000)
        except Exception:
            try:
                timer_btn.click(force=True, timeout=8000)
            except Exception as e:
                log(f"  -- 定时发布点击失败: {str(e)[:80]}")
                break
        for _ in range(12):
            modal = page.locator(".byte-modal")
            if modal.count() > 0 and modal.last.is_visible():
                opened = True
                break
            time.sleep(1)
        if opened:
            break
        log(f"  -- 弹窗未出现（第 {attempt+1} 次，可能 toast 遮挡），重试")
        try:
            page.keyboard.press("Escape"); time.sleep(1.5)
        except Exception:
            pass
    if not opened:
        log("  -- 定时弹窗未出现（多半是封面没设好，封面是必需项）")
        try:
            page.screenshot(path=os.path.join(SKILL_ROOT, "article_schedule_fail.png"))
            body_txt = page.evaluate(
                "() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0, 500)")
            log(f"  -- 页面文本快照: {body_txt!r}")
        except Exception as e:
            log(f"  -- 诊断失败: {str(e)[:80]}")
        return False

    mmdd = f"{when_dt.month:02d}月{when_dt.day:02d}日"
    ok = True
    ok &= _pick_select(page, "day-select", [mmdd], "日期")
    ok &= _pick_select(page, "hour-select",
                       [str(when_dt.hour), f"{when_dt.hour:02d}"], "时")
    # 分钟若不在可选项里（如按 5 分钟粒度），向下取整到最近的可用值
    ok_min = _pick_select(page, "minute-select",
                          [f"{when_dt.minute:02d}", str(when_dt.minute)], "分")
    if not ok_min:
        for cand in range(when_dt.minute - 1, -1, -1):
            if _pick_select(page, "minute-select",
                            [f"{cand:02d}", str(cand)], f"分(回退{cand})"):
                ok_min = True
                break
    ok &= ok_min

    if not ok:
        log("  -- 日期/时间选择失败，取消定时，不提交")
        try:
            page.locator(".byte-modal button:has-text('取消')").last.click(force=True, timeout=5000)
        except Exception:
            pass
        return False

    try:
        prev = page.locator(".byte-modal").last.inner_text()
        log(f"  弹窗确认: {' '.join(prev.split())[:120]}")
    except Exception:
        pass

    # 注意：发布请求的拦截修正（仅 timer_status=1，用于定时发布排程）
    # 已统一在 main() 注册 _patch_publish 路由，定时与直接发布分支共用，此处不再重复注册。

    if not safe_click(page.locator(".byte-modal button:has-text('预览并定时发布')").last,
                      "预览并定时发布"):
        return False
    time.sleep(6)

    # 进入预览页后必须点「确认发布」才真正提交。
    # 有了上面的 timer_status=1，这次点击是「确认定时发布」，不会变成立即发布。
    if not safe_click(page.locator("button:has-text('确认发布')").last, "确认发布(定时)"):
        return False
    time.sleep(6)
    return True


def main():
    argv = sys.argv[1:]
    schedule_arg = None
    if "--schedule" in argv:
        i = argv.index("--schedule")
        if i + 1 < len(argv):
            schedule_arg = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
    inp = argv[0] if argv else DEFAULT_INPUT
    if not os.path.exists(inp):
        print(f"ERROR: 稿件不存在 {inp}"); sys.exit(1)
    post = json.load(open(inp, "r", encoding="utf-8"))
    if post.get("type") != "article":
        print("ERROR: type=article"); sys.exit(1)
    title = post["title"].strip()
    body = post["body"].strip()
    cover_rel = (post.get("cover") or "").strip()
    settings = post.get("settings", {}) or {}
    want_first = settings.get("first_release", "头条首发")
    want_declare = settings.get("work_declare", "引用AI")
    if not (2 <= len(title) <= 30):
        print("ERROR: 标题长度 2-30"); sys.exit(1)
    # 2026-09-14 用户实测规则：头条「同时发布微头条」只在【正文 < 100 字符】时生效，
    # ≥100 字符的长文服务端不会同步生成微头条。故这里不能再卡 200 字下限，
    # 只保留防空白的最小长度；并按长度提示本次是否属于「可同步微头条」的短文。
    if len(body) < 10:
        print("ERROR: 正文过短"); sys.exit(1)
    if len(body) < 100:
        log(f"   短文模式（{len(body)} 字符 < 100）：头条会原生同步带出微头条")
    else:
        log(f"   长文模式（{len(body)} 字符 ≥ 100）：头条不会同步微头条（服务端限制）")

    # 定时发布时间：命令行 --schedule 优先，其次稿件里的 schedule_time
    schedule_dt = None
    raw = (schedule_arg or post.get("schedule_time") or "").strip()
    if raw:
        try:
            schedule_dt = datetime.datetime.strptime(raw, "%Y-%m-%d %H:%M")
            log(f"定时发布模式：目标 {schedule_dt:%Y-%m-%d %H:%M}")
        except ValueError:
            log(f"⚠️ schedule_time 格式错误（需 YYYY-MM-DD HH:MM）: {raw!r} -> 改为直接发布")

    cfg = json.load(open(DEFAULT_CONFIG, "r", encoding="utf-8"))
    auth = json.load(open(os.path.join(SKILL_ROOT, cfg["auth_file"]), "r", encoding="utf-8"))
    images_dir = os.path.join(SKILL_ROOT, cfg.get("images_dir", "images"))

    state = {"err": None, "publish_code": None}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        ctx.add_cookies(auth)
        page = ctx.new_page()
        page.set_default_timeout(25000)

        def on_response(r):
            try:
                if "/article/publish" in r.request.url:
                    try:
                        j = r.json()
                        state["publish_code"] = j.get("code")
                        if j.get("code") not in (0, None):
                            state["err"] = f"server_code_{j.get('code')}_{j.get('message')}"
                            log(f"  [publish resp] code={j.get('code')} msg={j.get('message')}")
                        else:
                            log(f"  [publish resp] code={j.get('code')} msg={j.get('message')}")
                    except Exception:
                        pass
            except Exception:
                pass
        page.on("response", on_response)

        # 发布请求拦截：
        #  1) 定时模式把 timer_status 0 -> 1（头条定时发布前端误发 0，不翻则不排程）；
        #  2) 关键的「同时发布微头条」开关修正（2026-09-14 根因修复）：
        #     「确认发布」请求的 extra 里，微头条开关字段名是 tuwen_wtt_trans_flag，
        #     与编辑期自动保存用的 tuwen_wtt_transfer_switch 不是同一个字段；
        #     且该字段在确认发布时恒为 "0"（预览页重新序列化表单时把它置零），
        #     所以服务端一直收不到开关、不会生成微头条。
        #     这里在请求发出前把两个字段都强制置为 "1"，让一次发布动作原生带出微头条。
        # 重建 body 必须用 m.start(1)/m.end(1)：正则 (?:^|&) 会吃掉前导 &，
        # 用 m.start() 会把 & 丢掉 -> 参数串损坏 -> 服务端 7050。
        _publish_logged = {"done": False, "seq": 0}
        _route_dump = os.path.join(SKILL_ROOT, "route_dump.txt")
        _route_detail = os.path.join(SKILL_ROOT, "route_detail.txt")
        try:
            os.remove(_route_dump)
            os.remove(_route_detail)
        except Exception:
            pass
        def _patch_publish(route, request):
            try:
                url = request.url or ""
                if "/article/publish" in url:
                    pd = request.post_data or ""
                    _publish_logged["seq"] += 1
                    seq = _publish_logged["seq"]
                    import urllib.parse as _up
                    # 2026-09-14 根因修复（关键）：
                    # 头条「确认发布」请求（预览页重新序列化）的 extra 里，微头条开关字段名
                    # 是 tuwen_wtt_trans_flag，而不是编辑期自动保存用的 tuwen_wtt_transfer_switch。
                    # 之前按错误字段名注入，所以服务端始终收不到开关、不会生成微头条。
                    # 这里把两个字段都强制置为 "1"，让一次发布动作原生带出微头条。
                    # 注意重建 body 时必须用 m.start(1)/m.end(1)（正则 (?:^|&) 会吃掉前导 &，
                    # 用 m.start() 会把 & 丢掉导致参数串损坏 -> 服务端 7050）。
                    WTT_FIELDS = ("tuwen_wtt_trans_flag", "tuwen_wtt_transfer_switch")
                    flag_val = "NO_EXTRA"
                    mm = re.search(r"(?:^|&)(extra=[^&]+)", pd)
                    if mm:
                        try:
                            dec = _up.unquote(mm.group(1)[6:])
                            d = json.loads(dec)
                            if isinstance(d, dict):
                                before = {k: d.get(k) for k in WTT_FIELDS if k in d}
                                changed = False
                                for fld in WTT_FIELDS:
                                    if str(d.get(fld)) != "1":
                                        d[fld] = "1"
                                        changed = True
                                if changed:
                                    new_enc = _up.quote(json.dumps(d, ensure_ascii=False), safe="")
                                    pd = pd[:mm.start(1)] + "extra=" + new_enc + pd[mm.end(1):]
                                    log(f"  [route] seq={seq} 微头条开关置1（原值 {before}）")
                                flag_val = str(d.get("tuwen_wtt_trans_flag"))
                            else:
                                flag_val = "NOT_DICT"
                        except Exception as e:
                            flag_val = f"PARSE_ERR:{str(e)[:30]}"
                    with open(_route_dump, "a", encoding="utf-8") as f:
                        f.write(f"seq={seq} trans_flag={flag_val}\n")
                    # 详细落盘：顶层参数名 + extra 里所有 key + URL 查询参数，
                    # 用于确认开关是否换了别的字段名 / 位置。
                    try:
                        keys = sorted({p.split("=", 1)[0] for p in pd.split("&") if p})
                        ex_keys = []
                        if mm:
                            try:
                                ex_obj = json.loads(_up.unquote(mm.group(1)[6:]))
                                if isinstance(ex_obj, dict):
                                    ex_keys = sorted(ex_obj.keys())
                            except Exception:
                                ex_keys = ["<parse_err>"]
                        q = url.split("?", 1)[1] if "?" in url else ""
                        qkeys = sorted({p.split("=", 1)[0] for p in q.split("&") if p})
                        with open(_route_detail, "a", encoding="utf-8") as f:
                            f.write(f"--- seq={seq} trans_flag={flag_val}\n")
                            f.write(f"URL_QUERY_KEYS: {qkeys}\n")
                            f.write(f"TOP_KEYS: {keys}\n")
                            f.write(f"EXTRA_KEYS: {ex_keys}\n")
                    except Exception as e:
                        log(f"  [route] detail dump err: {str(e)[:60]}")
                    if not _publish_logged["done"]:
                        _publish_logged["done"] = True
                        keys = sorted({p.split("=", 1)[0] for p in pd.split("&") if p})
                        log("  [route] 发布请求参数名: " + ", ".join(keys))
                    # 仅【定时模式】才把 timer_status=0 翻成 1（头条定时发布前端误发 0，
                    # 不翻则服务端当立即发布）。立即发布(schedule_dt=None)必须保留
                    # timer_status=0，否则会被误改成「无效时间的定时发布」→ 服务端 7050 保存失败。
                    # 注意：改写 extra 必须整体解析 JSON 后用 m.start(1)/m.end(1) 精确重建
                    # （用 m.start() 会丢掉前导 &，导致参数串损坏 -> 服务端 7050）。
                    if schedule_dt is not None and "timer_status=0" in pd:
                        pd = pd.replace("timer_status=0", "timer_status=1")
                        log("  [route] timer_status 0 -> 1（启用定时发布）")
                    route.continue_(post_data=pd)
                    return
            except Exception as e:
                log(f"  [route] patch error: {str(e)[:80]}")
            route.continue_()
        page.route("**/article/publish**", _patch_publish)

        log("1/6 打开后台...")
        page.goto("https://mp.toutiao.com/profile_v4/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(6)
        log("2/6 进入文章编辑器...")
        page.locator("text=文章").first.click()
        page.wait_for_selector("[contenteditable='true']", timeout=30000); time.sleep(2)
        for sel in [".byte-drawer-close", ".ai-assistant-drawer [class*='close']"]:
            try:
                if page.locator(sel).count() > 0:
                    page.locator(sel).first.click(force=True, timeout=2000); time.sleep(1); break
            except Exception:
                pass

        log("3/6 填标题与正文（含正文插图）...")
        ta = page.locator("textarea[placeholder*='请输入文章标题']")
        ta.click(force=True); ta.fill(title); time.sleep(1)
        ed = page.locator(".ProseMirror").first
        ed.click(force=True); page.keyboard.press("Control+a"); page.keyboard.press("Delete")
        # 末尾单独一段的 #话题# 不写纯文本，改由话题选择器插入成可点击话题。
        # （分段逻辑同理保留：\n\n 不足 2 段时回退 \n 分段，避免整篇被当 1 段致插图越界）
        paras, topics = split_trailing_topics(body)
        if topics:
            log(f"   检出末段话题 {topics}（用话题选择器插入，不写纯文本）")
        inline_fnames = [p for p in (post.get("inline_images") or []) if isinstance(p, str)]
        img_after = compute_image_positions(len(paras), len(inline_fnames))
        img_cursor = 0
        log(f"   正文 {len(paras)} 段，计划插图 {len(inline_fnames)} 张，位置={img_after}")
        for i, p in enumerate(paras):
            if i:
                page.keyboard.press("Enter")
            page.keyboard.insert_text(p)
            time.sleep(0.25)
            if img_cursor < len(inline_fnames) and img_cursor < len(img_after) and i == img_after[img_cursor]:
                time.sleep(0.5)
                if insert_inline_image(page, inline_fnames[img_cursor], images_dir):
                    img_cursor += 1
                else:
                    log("  -- 插图失败，继续正文（文章仍会带封面发出）")
                time.sleep(0.5)
        # 段落太少时仍有剩余图：追加到结尾
        while img_cursor < len(inline_fnames):
            page.keyboard.press("Enter")
            if insert_inline_image(page, inline_fnames[img_cursor], images_dir):
                img_cursor += 1
            else:
                break
        time.sleep(2)
        log(f"   实际插入正文图片 {img_cursor} 张")

        if topics:
            log("3.5/6 用话题选择器插入正文话题...")
            got = insert_article_topics(page, topics)
            log(f"   话题插入完成 {got}/{len(topics)} 个（其余退化为纯文本）")
            time.sleep(0.8)

        log("4/6 声明首发 / 作品声明（JS 直派 DOM + 勾选后校验）...")
        def set_checkbox(cell_label, option_text, desc):
            js = """(args) => {
                const cells = document.querySelectorAll('.pgc-edit-cell');
                for (const c of cells) {
                    const lbl = c.querySelector('.edit-label');
                    if (!lbl || !lbl.innerText.includes(args.cellLabel)) continue;
                    const labels = c.querySelectorAll('label');
                    for (const lab of labels) {
                        if (!lab.innerText.includes(args.option)) continue;
                        const inp = lab.querySelector('input[type=checkbox], input[type=radio]');
                        const wasChecked = inp ? inp.checked : false;
                        // 2026-09-10 fix: editor remembers last-run settings, so the box
                        // may ALREADY be checked. Blind-clicking toggles it OFF (this
                        // actually happened: 头条首发 was=True -> now=False). Only click
                        // when unchecked.
                        if (wasChecked) {
                            return JSON.stringify({found:true, wasChecked:true, isChecked:true, skipped:true});
                        }
                        lab.click();
                        const inp2 = lab.querySelector('input[type=checkbox], input[type=radio]');
                        const isChecked = inp2 ? inp2.checked : false;
                        return JSON.stringify({found:true, wasChecked, isChecked});
                    }
                }
                return JSON.stringify({found:false});
            }"""
            try:
                result = page.evaluate(js, {"cellLabel": cell_label, "option": option_text})
                import json as _json
                r = _json.loads(result) if isinstance(result, str) else result
                if r.get("found"):
                    log(f"  ok {desc}: was={r.get('wasChecked')} now={r.get('isChecked')}{' (已勾选，跳过点击)' if r.get('skipped') else ''}")
                    return r.get("isChecked")
                log(f"  -- {desc}: 未找到对应复选框")
            except Exception as e:
                log(f"  -- {desc}: {str(e)[:80]}")
            return False
        # ===== 发文设置清单（用户 2026-09-14 指定；2026-09-20 更新第 3 项为平台默认规则）=====
        # 1) 投放广告       -> 「投放广告赚收益」  总是勾（默认不勾，需主动点）
        # 2) 声明首发       -> 「头条首发」        正文 ≥100 字符才勾（文章都 ≥300，故总勾）
        # 3) 同时发布微头条  -> 正文<100 默认勾选；正文≥100 平台不提供该开关（选不了）
        # 4) 作品声明       -> 「引用AI」          总是勾
        is_short = len(body) < 100

        # 1) 投放广告
        set_checkbox("投放广告", "投放广告赚收益", "勾选 投放广告赚收益")

        # 2) 声明首发
        if want_first:
            if is_short:
                log(f"   短文（{len(body)} 字符 < 100）：跳过「{want_first}」（头条对短文不提供首发选项）")
            else:
                set_checkbox("声明首发", want_first, f"勾选 {want_first}")

        # 3) 同时发布微头条（2026-09-20 用户澄清平台规则：正文 <100 默认勾；≥100 选不了）
        if is_short:
            ensure_wtt_switch_editor(page)
            log(f"   短文（{len(body)} 字符 < 100）：确保「同时发布微头条」勾选（平台默认勾）")
        else:
            log(f"   长文（{len(body)} 字符 ≥ 100）：头条不提供「同时发布微头条」开关（选不了），跳过")

        # 4) 作品声明
        if want_declare:
            set_checkbox("作品声明", want_declare, f"勾选 {want_declare}")

        # 关键：先彻底关掉所有残留的上传/弹窗面板（正文插图可能没完全关闭，
        # 残留面板的「本地上传」会误判封面上传「已打开」并操作到错误面板）
        for _ in range(5):
            if page.locator(".upload-image-panel").count() == 0:
                break
            try: page.locator(".upload-image-panel button:has-text('确定')").last.click(force=True, timeout=3000)
            except Exception: pass
            try: page.keyboard.press("Escape"); time.sleep(1)
            except Exception: pass
        time.sleep(1)

        cover_ok = False
        # 头条在正文有图时常会自动抓一张作封面（原「添加」按钮 .article-cover-add 会消失）。
        # 优先复用自动封面；否则用 cover 字段指定的文件，或正文第一张图主动上传兜底。
        # 2026-09-13 fix：旧逻辑把自动封面检查放进 `if cover_rel:` 内，cover 为空时整块跳过
        # 导致 cover_ok 恒为 False 而中止。现提到外层，空 cover 也能走自动封面/正文图兜底。
        has_auto_cover = page.locator(".article-cover-img-wrap img").count() > 0
        if has_auto_cover:
            log("5/6 封面已由正文图自动填充，直接复用（无需上传）。")
            cover_ok = True
        else:
            # 候选封面：优先 cover 指定文件，否则正文第一张图
            cand_rel = ""
            cover_path = resolve_img(cover_rel, images_dir) if cover_rel else None
            if cover_path:
                cand_rel = cover_path
            elif inline_fnames:
                cand_rel = resolve_img(inline_fnames[0], images_dir) or inline_fnames[0]
            if cand_rel:
                abs_cover = cand_rel if os.path.isabs(cand_rel) else os.path.join(images_dir, cand_rel)
                add_btn = page.locator(".article-cover-add")
                if add_btn.count() > 0:
                    log(f"5/6 上传封面（用 {cand_rel}）...")
                    try:
                        add_btn.first.scroll_into_view_if_needed(timeout=5000)
                        add_btn.first.click(force=True, timeout=6000)
                    except Exception:
                        try: page.evaluate("() => { const e=document.querySelector('.article-cover-add'); if(e) e.click(); }")
                        except Exception: pass
                    time.sleep(2.5)
                    if page.locator(".upload-image-panel").count() > 0:
                        # 只针对最新弹出的封面面板操作（残留面板在前，封面面板在后 = .last）
                        panel = page.locator(".upload-image-panel").last
                        try:
                            ub = panel.locator(".upload-btn:has-text('本地上传'), span:has-text('本地上传')").last
                            if ub.count() > 0:
                                ub.click(force=True, timeout=5000); time.sleep(1)
                            fi = panel.locator("input[type='file']").first
                            fi.wait_for(state="attached", timeout=8000)
                            fi.set_input_files(abs_cover, timeout=15000)
                            time.sleep(8)
                            thumb = panel.locator(".img-wrap img").last
                            thumb.wait_for(state="visible", timeout=15000)
                            thumb.click(force=True)
                            time.sleep(1.5)
                            panel.locator("button:has-text('确定')").last.click(force=True, timeout=8000)
                            time.sleep(3)
                            cover_ok = True
                        except Exception as e:
                            log(f"  -- 封面上传: {str(e)[:120]}")
                    if not cover_ok and page.locator(".article-cover-img-wrap img").count() > 0:
                        log("  -- 上传未成功，但检测到自动封面，复用之。")
                        cover_ok = True
                else:
                    # 没有「添加」按钮且无可自动封面，稍等重试一次自动封面
                    time.sleep(2)
                    if page.locator(".article-cover-img-wrap img").count() > 0:
                        log("5/6 延时后检测到自动封面，复用。")
                        cover_ok = True
            else:
                log("  -- 无候选封面文件且无可自动封面。")
        if not cover_ok:
            log("ERROR: 封面未就绪，中止。"); browser.close(); sys.exit(2)

        if schedule_dt:
            # ===== 定时发布分支：由头条服务器到点自动发出 =====
            if not scheduled_publish(page, schedule_dt):
                log("ERROR: 定时发布失败，中止（未提交任何内容）。")
                state["err"] = state["err"] or "schedule_failed"
                browser.close()
                json.dump(state, open(os.path.join(SKILL_ROOT, "article_capture.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                sys.exit(1)
            published = True
            state["scheduled"] = f"{schedule_dt:%Y-%m-%d %H:%M}"
            state["published"] = False   # 尚未到点，首页查不到
            log(f"   已排程（头条到点自动发出）: {state['scheduled']}")
            page.screenshot(path=os.path.join(SKILL_ROOT, "article_scheduled.png"))
        else:
            # ===== 直接发布分支 =====
            log("6/6 预览并发布 -> 确认发布（带签名令牌的请求，绕过 7050）...")
            preview_btn = page.locator("button:has-text('预览并发布'), span:has-text('预览并发布')").last
            safe_click(preview_btn, "预览并发布")
            # 7050 自动保存抖动时，预览弹窗 / 确认发布按钮可能延迟出现，
            # 轮询等待（最多 ~20s）而非固定 sleep；若首点被 7050 弹窗吃掉则重试。
            confirm = page.locator("button:has-text('确认发布')")
            appeared = False
            for _ in range(10):
                try:
                    if confirm.last.count() > 0 and confirm.last.is_visible():
                        appeared = True
                        break
                except Exception:
                    pass
                try:
                    if confirm.last.count() == 0 and preview_btn.count() > 0:
                        preview_btn.click(force=True, timeout=3000)
                except Exception:
                    pass
                time.sleep(2)
            if not appeared:
                log("⚠️ 未找到确认发布按钮（预览可能已 7050）")
                state["err"] = state["err"] or "no_confirm_button"
                browser.close()
                json.dump(state, open(os.path.join(SKILL_ROOT, "article_capture.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                sys.exit(1)

            confirm.last.click(force=True, timeout=8000)
            time.sleep(6)

            # verify it actually got PUBLISHED.
            # NOTE: /profile_v4/index is the HOMEPAGE (最近作品 = published items); that is
            # the reliable signal. /graphic/post (作品管理) often renders blank, so treat a
            # hit there as a bonus, not a requirement.
            time.sleep(2)
            published = False
            for _ in range(6):
                try:
                    page.goto("https://mp.toutiao.com/profile_v4/index",
                              wait_until="domcontentloaded", timeout=30000)
                    time.sleep(6)
                    if title in page.inner_text("body"):
                        published = True
                        break
                except Exception:
                    pass
                time.sleep(4)
            state["published"] = published
            state["in_draft"] = None   # no draft path exists; kept for schema compatibility
            log(f"   已发布(首页最近作品命中): {published}")
            page.screenshot(path=os.path.join(SKILL_ROOT, "article_published.png"))

            # 微头条：默认走头条原生「同时发布微头条」（开关已在上面的路由里置 1，
            # 由服务端在文章上线时一并带出），不再事后补发。
            # 若某账号原生同步确实不生效，可用 WTT_FALLBACK=1 打开「发布后再补发一条」
            # 作为兜底（注意：原生生效时开启会产生重复微头条）。
            if (published and not state.get("scheduled")
                    and os.environ.get("WTT_FALLBACK") == "1"):
                try:
                    ok, info = publish_linked_microblog(post, cfg, images_dir)
                    log(f"   兜底补发微头条: {'成功' if ok else '失败'}")
                    if ok:
                        state["microblog"] = True
                except Exception as e:
                    log(f"   ⚠️ 兜底补发微头条异常: {e}")

            if not published:
                state["err"] = state["err"] or "not_published"
        browser.close()

    json.dump(state, open(os.path.join(SKILL_ROOT, "article_capture.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if not published:
        log(f"FAIL: {state.get('err')}")
        sys.exit(1)

    # record de-dup
    topic_hash = hashlib.sha1((title + "::" + body).encode()).hexdigest()[:12]
    pt_file = os.path.join(SKILL_ROOT, cfg.get("published_topics_file", "published_top.json"))
    pt = json.load(open(pt_file, "r", encoding="utf-8")) if os.path.exists(pt_file) else []
    if isinstance(pt, list):
        if not any(isinstance(x, dict) and x.get("key") == topic_hash for x in pt):
            pt.append({"key": topic_hash, "date": time.strftime("%Y-%m-%d"), "type": "article", "title": title})
    json.dump(pt, open(pt_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if state.get("scheduled"):
        log(f"DONE 文章已排程 -> {state['scheduled']}（头条服务器到点自动发出，无需本机在线）。")
    else:
        log("DONE 文章已发布上线（确认发布路径，带签名令牌）。")

if __name__ == "__main__":
    main()
