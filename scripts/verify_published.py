#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_published.py — 发布后自检：微头条和文章是不是真的上线了。

用法:
  python scripts/verify_published.py              # 自动读 article_post.json + posts.json
  python scripts/verify_published.py "关键词"      # 只查指定关键词

判据（2026-09-09 校准）:
  - /profile_v4/index 是**首页**，里面的「最近作品」= 已发布内容 → 用它判定发布成功。
  - /profile_v4/manage/draft 才是草稿箱。两者别搞混（曾在这里误判过一次）。
  - /profile_v4/graphic/post（作品管理）在自动化里常渲染空白，不可靠，只作参考。

退出码: 0 = 全部命中；1 = 有未命中（供上层判断是否需要告警）
"""
import json, os, sys, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
HOME_URL = "https://mp.toutiao.com/profile_v4/index"


def log(m):
    print(f"[verify] {m}", flush=True)


def load_targets():
    """从稿件里取出要核验的关键词：文章标题 + 微头条正文开头。"""
    targets = {}
    ap = os.path.join(SKILL_ROOT, "article_post.json")
    if os.path.exists(ap):
        try:
            j = json.load(open(ap, "r", encoding="utf-8"))
            t = (j.get("title") or "").strip()
            if t:
                targets["文章"] = t[:12]      # 取前 12 字，避免列表截断导致匹配失败
        except Exception:
            pass
    # 引流微头条优先读 wtt_post.json（由文章生成）；没有再退回 posts.json
    wtt = os.path.join(SKILL_ROOT, "wtt_post.json")
    pf = wtt if os.path.exists(wtt) else os.path.join(SKILL_ROOT, "posts.json")
    if os.path.exists(pf):
        try:
            j = json.load(open(pf, "r", encoding="utf-8"))
            posts = j.get("posts", []) if isinstance(j, dict) else j
            if posts:
                body = (posts[0].get("body") or "").strip()
                if body:
                    targets["微头条"] = body[:12]
        except Exception:
            pass
    return targets


def main():
    if len(sys.argv) > 1:
        targets = {"自定义": sys.argv[1][:20]}
    else:
        targets = load_targets()

    if not targets:
        log("ERROR: 没有可核验的目标（article_post.json / posts.json 都为空）")
        sys.exit(1)

    log("待核验: " + json.dumps(targets, ensure_ascii=False))

    cfg = json.load(open(os.path.join(SKILL_ROOT, "config.json"), "r", encoding="utf-8"))
    auth = json.load(open(os.path.join(SKILL_ROOT, cfg["auth_file"]), "r", encoding="utf-8"))

    result = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge", headless=True)
        ctx = b.new_context()
        ctx.add_cookies(auth)
        page = ctx.new_page()
        page.set_default_timeout(25000)

        # 首页最近作品可能有延迟，最多刷 5 轮
        body_text = ""
        for i in range(5):
            try:
                page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(7)
                for _ in range(3):
                    page.mouse.wheel(0, 1200)
                    time.sleep(1)
                page.mouse.wheel(0, -5000)
                time.sleep(1)
                body_text = page.inner_text("body")
            except Exception as e:
                log(f"  第{i+1}轮读取失败: {str(e)[:80]}")
            if body_text:
                break
            time.sleep(4)

        for name, key in targets.items():
            hit = key in body_text if body_text else False
            result[name] = {"key": key, "published": hit}
            log(f"  {'✓' if hit else '✗'} {name}: {'已上线' if hit else '未找到'}  (关键词: {key})")

        page.screenshot(path=os.path.join(SKILL_ROOT, "verify_published.png"))
        b.close()

    json.dump(result, open(os.path.join(SKILL_ROOT, "verify_result.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=2)

    ok = all(v["published"] for v in result.values())
    log("结论: " + ("全部发布成功" if ok else "存在未发布成功的项目，需要人工查看"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
