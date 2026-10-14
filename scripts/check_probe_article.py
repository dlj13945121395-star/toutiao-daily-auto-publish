"""只读核查：查找是否存在「定时探测」开头的文章，及其状态（已发布/草稿/待发布）。"""
import json
import os
import time

from playwright.sync_api import sync_playwright

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    cfg = json.load(open(os.path.join(SKILL_ROOT, "config.json"), "r", encoding="utf-8"))
    auth = json.load(open(os.path.join(SKILL_ROOT, cfg.get("auth_file", "toutiao_auth.json")), "r", encoding="utf-8"))

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=False)
        ctx = b.new_context(viewport={"width": 1600, "height": 1000})
        ctx.add_cookies(auth if isinstance(auth, list) else auth.get("cookies", []))
        page = ctx.new_page()
        page.set_default_timeout(25000)

        # 1) 首页最近作品（已发布）
        print("=== 首页最近作品 ===")
        try:
            page.goto("https://mp.toutiao.com/profile_v4/index", wait_until="domcontentloaded", timeout=40000)
            time.sleep(7)
            txt = page.inner_text("body")
            hit = "定时探测" in txt
            print(f"  含「定时探测」: {hit}")
            if hit:
                for line in txt.split("\n"):
                    if "定时探测" in line:
                        print("   >", line.strip()[:100])
        except Exception as e:
            print("  读取首页失败:", str(e)[:120])

        # 2) 草稿箱
        print("\n=== 草稿箱 ===")
        try:
            page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=40000)
            time.sleep(7)
            txt = page.inner_text("body")
            hit = "定时探测" in txt
            print(f"  含「定时探测」: {hit}")
            if hit:
                for line in txt.split("\n"):
                    if "定时探测" in line:
                        print("   >", line.strip()[:100])
            print("  摘要:", " / ".join([x.strip() for x in txt.split("\n") if x.strip()][:12])[:400])
        except Exception as e:
            print("  读草稿箱失败:", str(e)[:120])

        b.close()


if __name__ == "__main__":
    main()
