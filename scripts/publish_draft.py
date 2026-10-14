#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_draft.py — 今日头条 / 微头条 自动存草稿核心脚本

依赖:
    pip install playwright && playwright install chromium

用法:
    python publish_draft.py --login        # 首次扫码登录，保存 toutiao_auth.json（有头模式）
    python publish_draft.py                # 读 posts.json，逐篇存草稿（无头复用登录态）
    python publish_draft.py --dry-run      # 只打印计划，不发布
    python publish_draft.py --inspect      # 导出发布页 HTML 到 inspect.html，用于校准选择器
    python publish_draft.py --config my.json

所有 URL / 选择器都在同目录 config.json 的 "selectors" 中；本机实测校准只改配置、不动代码。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time
import traceback

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright 未安装。请先运行: pip install playwright && playwright install chromium")
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)  # config.json 在技能根目录，不在 scripts/ 下
DEFAULT_CONFIG = os.path.join(SKILL_ROOT, "config.json")
REQUIRED_COOKIES = ["sid_tt", "sessionid", "passport_auth_status", "uid_tt"]


def log(*a):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}]", *a, flush=True)


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve(p, base):
    if not p:
        return p
    return p if os.path.isabs(p) else os.path.join(base, p)


def load_auth(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_auth(path, cookies):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    log("已保存登录态 ->", path)


def has_required_cookies(cookies):
    names = {c.get("name") for c in cookies}
    return all(k in names for k in REQUIRED_COOKIES)


def do_login(pw, cfg, auth_file):
    log("启动有头浏览器，请在弹出的窗口中用今日头条 APP 扫码登录...")
    browser = pw.chromium.launch(headless=False)
    ctx = browser.new_context()
    page = ctx.new_page()
    try:
        page.goto(cfg["publish_url"], wait_until="domcontentloaded")
    except Exception as e:
        log("WARN: 打开发布页异常（可能需先登录）:", e)
    deadline = time.time() + 180
    while time.time() < deadline:
        cookies = ctx.cookies()
        if has_required_cookies(cookies):
            save_auth(auth_file, cookies)
            browser.close()
            return True
        time.sleep(3)
    log("ERROR: 180s 内未检测到登录态（sid_tt/sessionid/passport_auth_status/uid_tt），请重试。")
    browser.close()
    return False


def resolve_images(post, images_dir):
    out = []
    for p in post.get("images") or []:
        if not os.path.isabs(p):
            p = os.path.join(images_dir, p)
        if os.path.exists(p):
            out.append(p)
        else:
            log("WARN: 图片不存在，跳过:", p)
    return out


def fill_editor(page, sel, text):
    editor = page.locator(sel).first
    # 用 focus() 而非 click()：发文页「发布助手」浮层会遮住编辑器，
    # focus 不受遮挡影响，能稳定把光标放入 contenteditable。
    editor.focus()
    # contenteditable 清空：全选 + 删除，再 insert_text
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.insert_text(text)
    time.sleep(0.5)


def upload_images(page, cfg, image_paths):
    s = cfg["selectors"]
    wait_s = cfg.get("wait_after_upload_ms", 6000) / 1000.0
    page.locator(s["image_button"]).click()
    # file input 是隐藏元素，不能用 visible 状态等待（永不"可见"），改为 attached 即可
    page.wait_for_selector(s["image_panel_file_input"], state="attached", timeout=10000)
    page.locator(s["image_panel_file_input"]).set_input_files(image_paths)
    time.sleep(wait_s)
    # 等缩略图出现（用 attached 而非 visible：面板可能残留上轮缩略图导致找到多个元素，
    # 其中旧的可能不可见；用 .last 取最新上传的那张）
    page.wait_for_selector(s["image_thumbnail"], state="attached", timeout=10000)
    # 关键修复：缩略图元素虽已 attached，但远程图片可能尚未渲染完成（0 尺寸/不可见），
    # 此时 force 点击会报 "Element is not visible"。先等 .last 真正可见再点击，避开未渲染完成的元素。
    page.locator(s["image_thumbnail"]).last.wait_for(state="visible", timeout=15000)
    page.locator(s["image_thumbnail"]).last.click(force=True)
    page.locator(s["image_confirm"]).click(force=True)
    # 校验：正文出现「共 N 张，还能上传 17 张」
    page.wait_for_selector(s["image_count_hint"], timeout=10000)
    log("图片已插入，校验通过:", s["image_count_hint"])


def dismiss_overlays(page):
    # 头条发文页会自动弹出「发布助手」浮层（byte-drawer-mask），
    # 它会遮住编辑器导致 editor.click 被拦截。发布前先把它关掉。
    for sel in [".byte-drawer-close-icon", ".icon-close"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                loc.click(timeout=3000)
                time.sleep(0.6)
        except Exception:
            pass
    # 兜底：直接隐藏浮层 DOM（display:none + 禁用指针事件），确保不再遮挡编辑器
    try:
        page.evaluate("""() => {
          ['byte-drawer-mask','byte-drawer-wrapper','byte-drawer'].forEach(c => {
            document.querySelectorAll('.' + c).forEach(e => {
              e.style.display = 'none';
              e.style.pointerEvents = 'none';
            });
          });
        }""")
        time.sleep(0.3)
    except Exception:
        pass


# ===== 微头条话题：必须走「话题选择器」点选，纯文本不会变可点击链接 =====
# 2026-10-12 校准：微头条编辑器与文章编辑器用的是同一套组件 ——
#   敲 `#` → section.mention-selector-modal.forum → 候选项 section.forum-list-item
#   文本在 .forum-list-item-text；面板内有「敲空格可取消插入话题」提示。
# 纯文本 insert_text 写进去的 `#话题#` 只是普通文字，点不动 → 用户 2026-10-12 反馈。
TOPIC_ITEM = ".mention-selector-modal .forum-list-item"


def _norm_topic(s):
    """话题名归一化：去空白、井号、零宽字符。"""
    return re.sub(r"[\s#\u200b\u200c\u200d]+", "", s or "")


def split_trailing_topics(body):
    """把末尾「只由 #话题# 组成」的那一行拆出来。返回 (正文, [话题名,...])。

    微头条正文按行分段，话题固定在最后一行（空格分隔多个）。
    没有这样的一行时原样返回、话题列表为空。
    """
    lines = body.split("\n")
    idx = len(lines) - 1
    while idx >= 0 and not lines[idx].strip():
        idx -= 1
    if idx <= 0:
        return body, []
    last = lines[idx].strip()
    found = re.findall(r"#([^#\n]+?)#", last)
    residue = re.sub(r"#[^#\n]+?#", "", last).strip()
    if not (found and not residue):
        return body, []
    topics = [t.strip() for t in found if t.strip()]
    return "\n".join(lines[:idx]), topics


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


def _run_topic_queries(page, name, add_sep):
    """跑一轮查询词（全名→首个标点前→前8/6/4字）。返回 (picked, saw_candidate)。"""
    if add_sep:
        page.keyboard.type(" ")
        time.sleep(0.25)
    target = _norm_topic(name)
    saw = False
    for q in topic_queries(name):
        try:
            page.keyboard.type("#", delay=80)
            page.wait_for_selector(TOPIC_ITEM, timeout=5000)
        except Exception:
            try:
                page.keyboard.press("Backspace")   # 面板没弹出，删掉刚敲的 #
            except Exception:
                pass
            continue

        try:
            page.keyboard.type(q, delay=60)
            time.sleep(1.5)
            items = page.locator(TOPIC_ITEM)
            try:
                n = items.count()
            except Exception:
                n = 0
            if n > 0:
                saw = True
            for exact in (True, False):
                for k in range(n):
                    it = items.nth(k)
                    try:
                        cls = it.get_attribute("class") or ""
                        if "create-forum-button" in cls:   # 跳过「创建话题」，免得挂出垃圾话题
                            continue
                        if it.locator(".forum-list-item-text").count():
                            txt = it.locator(".forum-list-item-text").first.inner_text(timeout=1200)
                        else:
                            txt = it.inner_text(timeout=900)
                    except Exception:
                        continue
                    cand = _norm_topic(txt)
                    if (cand == target) if exact else (target in cand or cand in target):
                        it.click(force=True)
                        time.sleep(0.55)
                        log(f"  话题已插入: #{txt.strip()}#（查询词「{q}」）")
                        return True, saw
        except Exception as e:
            log(f"  话题「{name}」点选异常: {str(e)[:70]}")

        # 本查询词没命中 → 清掉刚敲的 `#`+查询词，换更短的再试
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        for _ in range(len(q) + 1):
            page.keyboard.press("Backspace")
        time.sleep(0.25)
    return False, saw


def _insert_one_topic(page, name, first):
    """插入单个话题（走选择器）。返回 True=挂成真话题，False=退化为纯文本。

    全名搜不到时自动换更短的查询词重试；
    若**一次候选都没出现过**（联想服务偶发瞬时无响应，2026-10-12 实测），
    等待后把整串查询词再跑一轮。
    任何异常都不得外抛 —— 最坏只是退化成纯文本，绝不能中断发布。
    """
    try:
        picked, saw = _run_topic_queries(page, name, add_sep=not first)
        if not picked and not saw:
            time.sleep(2.5)
            picked, saw = _run_topic_queries(page, name, add_sep=False)
        if picked:
            return True
    except Exception as e:
        log(f"  话题「{name}」插入异常: {str(e)[:70]}")

    # 退化：纯文本（面板此时已关闭）
    page.keyboard.insert_text(f"#{name}#")
    log(f"  话题「{name}」无匹配候选，退化为纯文本")
    return False


def insert_wtt_topics(page, topics):
    """逐个插入话题，返回成功挂成真话题的个数。"""
    return sum(1 for i, name in enumerate(topics) if _insert_one_topic(page, name, i == 0))


def publish_one(page, cfg, post, images_dir, live=False):
    s = cfg["selectors"]
    dismiss_overlays(page)
    body = post.get("body", "")
    text_part, topics = split_trailing_topics(body)
    fill_editor(page, s["editor"], text_part)

    # 话题单独走选择器插入（否则只是不可点击的纯文本）
    if topics:
        got = 0
        try:
            if text_part.strip():
                page.keyboard.press("Enter")
                time.sleep(0.35)
            got = insert_wtt_topics(page, topics)
            n_nodes = page.evaluate("""() => {
                const ed = document.querySelector("[contenteditable='true']");
                if (!ed) return 0;
                return ed.querySelectorAll('a[class*=tteditor-forum], a[data-concern-id]').length;
            }""")
        except Exception as e:
            n_nodes = -1
            log(f"  WARN: 话题插入异常，按已插入内容继续: {str(e)[:80]}")
        log(f"  话题插入完成 {got}/{len(topics)} 个；可点击话题节点数 = {n_nodes}")
        if n_nodes >= 0 and n_nodes < len(topics):
            log("  ⚠️ 部分话题未挂成可点击链接（站内可能搜不到该话题）→ 生成侧请改用站内话题池原文")
        time.sleep(0.4)

    # 微头条正文生成规范 200~500 字符（用户 2026-09-15 调整下限到 200）；平台「头条首发」前置仍为 ≥100 字符
    if len(body) < 200:
        log("WARN: 微头条正文仅 %d 字符（生成规范 200~500，下限 200），低于本号生成标准，请检查生成器产出" % len(body))

    imgs = resolve_images(post, images_dir)
    if imgs:
        upload_images(page, cfg, imgs)

    if cfg.get("toutiao_first_release"):
        if len(body) >= 100:
            try:
                page.locator(s["first_release_label"]).click()
                log("已勾选头条首发")
            except Exception as e:
                log("WARN: 头条首发勾选失败（选择器需校准）:", e)
        else:
            log("INFO: 正文 %d 字符（≤100），跳过头条首发勾选（头条要求 >100 字符才可勾）" % len(body))

    # 作品声明 = 引用AI（用户 2026-09-14 指定）。已勾选则跳过，避免重复点击反而取消。
    try:
        _wdl = s.get("work_declare_label", "label:has-text('引用AI')")
        _loc = page.locator(_wdl)
        if _loc.count() > 0:
            _lab = _loc.first
            _read = "(el) => { const i = el.querySelector('input'); return i ? !!i.checked : false; }"
            if page.evaluate(_read, _lab.element_handle()):
                log("作品声明：引用AI 已是勾选态，跳过")
            else:
                _lab.click()
                time.sleep(0.6)
                _now = page.evaluate(_read, _lab.element_handle())
                log(f"已勾选作品声明：引用AI（now={_now}）")
        else:
            log("WARN: 未找到「引用AI」作品声明选项")
    except Exception as e:
        log("WARN: 引用AI 勾选失败:", e)

    if live:
        # ---- 直接发布（不存草稿）----
        # 微头条编辑器底部并排「存草稿」与「发布」，用 :has-text 精确匹配「发布」。
        btn = s.get("publish_button", "button:text-is('发布')")
        fallback = s.get("publish_button_fallback", "button:has-text('发布')")
        if page.locator(btn).count() > 0:
            page.locator(btn).last.click()
        else:
            log("WARN: 精确选择器未命中，回退到 contains 匹配")
            page.locator(fallback).last.click()
        log("已点「发布」（直接上线，非存草稿）")
        try:
            page.wait_for_selector(
                s.get("publish_success_toast", "text=发布成功"), timeout=15000)
            log("发布成功 toast 已出现")
        except Exception:
            log("WARN: 未捕获到发布成功 toast（可能已跳转），按成功继续")
    else:
        page.locator(s["save_draft_button"]).click()
        page.wait_for_selector(s["success_toast"], timeout=10000)
        log("保存成功 toast 已出现")


def load_posts(path):
    if not os.path.exists(path):
        log("ERROR: 未找到 posts.json:", path)
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("posts", [])
    return data


def topic_key(post):
    return hashlib.md5(post.get("body", "").encode("utf-8")).hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--login", action="store_true", help="扫码登录并保存 toutiao_auth.json")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不发布")
    ap.add_argument("--inspect", action="store_true", help="导出发布页 HTML 到 inspect.html")
    ap.add_argument("--publish", action="store_true",
                    help="直接发布上线；不加则只存草稿（默认存草稿）")
    ap.add_argument("--posts", default=None,
                    help="指定待发布稿件文件（默认读 config 的 posts_file）。用于引流微头条等独立稿件。")
    ap.add_argument("--force", action="store_true",
                    help="跳过「今天已发布则跳过」的幂等检查，强制发布（多篇文章各带微头条时用）")
    args = ap.parse_args()

    cfg = load_config(args.config)
    base = os.path.dirname(os.path.abspath(args.config))
    auth_file = resolve(cfg.get("auth_file"), base)
    posts_file = resolve(args.posts or cfg.get("posts_file"), base)
    published_file = resolve(cfg.get("published_topics_file"), base)
    last_run_file = resolve(cfg.get("last_run_file"), base)
    images_dir = resolve(cfg.get("images_dir"), base)

    with sync_playwright() as pw:
        if args.login:
            ok = do_login(pw, cfg, auth_file)
            sys.exit(0 if ok else 1)

        cookies = load_auth(auth_file)
        if not cookies:
            log("ERROR: 未找到登录态，请先运行 --login")
            sys.exit(1)

        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto(cfg["publish_url"], wait_until="domcontentloaded")

        if args.inspect:
            with open(os.path.join(base, "inspect.html"), "w", encoding="utf-8") as f:
                f.write(page.content())
            log("已导出 inspect.html，用浏览器打开即可校准选择器")
            browser.close()
            return

        try:
            page.wait_for_selector(cfg["selectors"]["editor"], timeout=8000)
        except Exception:
            log("ERROR: 未检测到编辑器，可能登录失效，请重跑 --login")
            browser.close()
            sys.exit(1)

        posts = load_posts(posts_file)
        if not posts:
            log("没有可发布的稿件（posts.json 为空）")
            browser.close()
            return

        published = {}
        if os.path.exists(published_file):
            try:
                with open(published_file, "r", encoding="utf-8") as f:
                    published = {p["key"]: p for p in json.load(f)}
            except Exception:
                published = {}

        today = datetime.date.today().isoformat()
        if not args.force and os.path.exists(last_run_file):
            try:
                with open(last_run_file, "r", encoding="utf-8") as f:
                    lr = json.load(f)
                if lr.get("date") == today and lr.get("status") == "success":
                    log("今天已成功发布，跳过（幂等）")
                    browser.close()
                    return
            except Exception:
                pass

        count = int(cfg.get("daily_count", 3))
        done = 0
        for post in posts:
            if done >= count:
                break
            key = topic_key(post)
            if key in published:
                log("跳过已发布:", key)
                continue
            if args.dry_run:
                log(f"[dry-run] 将发布: {post.get('body','')[:30]}... 图:{len(post.get('images',[]))}")
                published[key] = {"key": key, "date": today, "dry": True}
                done += 1
                continue
            try:
                publish_one(page, cfg, post, images_dir, live=args.publish)
                published[key] = {"key": key, "date": today, "body_head": post.get("body", "")[:40]}
                done += 1
                with open(published_file, "w", encoding="utf-8") as f:
                    json.dump(list(published.values()), f, ensure_ascii=False, indent=2)
                time.sleep(2)
            except Exception as e:
                log("ERROR 发布失败:", e)
                traceback.print_exc()
                break

        with open(last_run_file, "w", encoding="utf-8") as f:
            json.dump({
                "date": today,
                "status": "success" if done > 0 else "empty",
                "count": done,
                "ts": int(time.time()),
            }, f, ensure_ascii=False, indent=2)
        log(f"本次完成 {done} 篇")
        browser.close()


if __name__ == "__main__":
    main()
