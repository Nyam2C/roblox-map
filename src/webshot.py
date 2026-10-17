# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright==1.55.0"]
# ///
"""Web photos of a facility without the desktop app's browser (cycle-build 7b): open each page in headless Chrome,
scroll so lazy photos load, and save the page as viewport-sized PNG tiles to look at with Read.

Usage (repo root):
  uv run src/webshot.py <out dir> <url> [url ...]   # -> <out dir>/<n>-<tile>.png, one line per tile, LINK lines for blog posts
  # Naver searches (WebSearch never returns blog.naver.com):
  #   https://m.search.naver.com/search.naver?where=m_blog&query=<장소>    blog results with photos -> LINK lines -> open those
  #   https://m.search.naver.com/search.naver?where=m_image&query=<장소>   a grid of photos
  uv run src/webshot.py --selftest                  # URL rewrite only, no browser
blog.naver.com is opened as m.blog.naver.com (photos sit in the page there, not in an iframe).
Uses the installed Google Chrome; without it run once: uv run --with playwright==1.55.0 playwright install chromium
A page that shows a CAPTCHA or bot check is skipped, never worked around. Tiles go to a scratch folder, never the repo.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

VIEW_W, VIEW_H, MAX_TILES = 1000, 1400, 12
BLOCK_WORDS = ("captcha", "자동입력 방지", "로봇이 아닙니다", "unusual traffic", "verify you are human")


def rewrite(url: str) -> str:
    p = urlsplit(url)
    if p.hostname == "blog.naver.com":
        return urlunsplit(p._replace(netloc="m.blog.naver.com"))
    return url


def shoot(page, url: str, out: Path, n: int) -> list[Path]:
    page.goto(rewrite(url), wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)
    if any(w in page.inner_text("body").lower() for w in BLOCK_WORDS):
        print(f"BLOCKED {url}")
        return []
    tiles = []
    for i in range(MAX_TILES):
        page.evaluate(f"window.scrollTo(0, {i * VIEW_H})")
        page.wait_for_timeout(700)
        f = out / f"{n}-{i:02d}.png"
        page.screenshot(path=str(f))
        tiles.append(f)
        if (i + 1) * VIEW_H >= page.evaluate("document.body.scrollHeight"):
            break
    # blog posts linked from the page (a Naver search page), to open next; WebSearch never returns blog.naver.com
    links = page.eval_on_selector_all("a[href*='blog.naver.com/']", "as => [...new Set(as.map(a => a.href))]")
    for href in [h for h in links if re.search(r"blog\.naver\.com/\w+/\d+", h)][:10]:
        print(f"LINK {href}")
    return tiles


def main(argv: list[str]) -> None:
    if argv == ["--selftest"]:
        assert rewrite("https://blog.naver.com/abc/223") == "https://m.blog.naver.com/abc/223"
        assert rewrite("https://blog.naver.com/PostView.naver?blogId=a&logNo=1") == "https://m.blog.naver.com/PostView.naver?blogId=a&logNo=1"
        assert rewrite("https://m.blog.naver.com/abc/223") == "https://m.blog.naver.com/abc/223"
        assert rewrite("https://namu.wiki/w/x") == "https://namu.wiki/w/x"
        print("ok")
        return
    if len(argv) < 2:
        sys.exit(__doc__)
    from playwright.sync_api import sync_playwright

    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H}, locale="ko-KR")
        for n, url in enumerate(argv[1:]):
            try:
                for f in shoot(page, url, out, n):
                    print(f"{f}\t{url}")
            except Exception as e:  # one bad page must not stop the rest
                print(f"FAILED {url}: {e}")
            time.sleep(1)  # polite rate
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
