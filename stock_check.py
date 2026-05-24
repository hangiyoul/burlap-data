"""재고 판정 (헤드리스 Playwright) — Cafe24/momos 검증됨.

정적 HTML로는 불가: 품절 배지/버튼/옵션태그가 판매중·품절 무관하게 항상 존재,
JS+CSS로 표시만 토글. → 실제 화면에 '보이는'(offsetParent!==null) 요소를 검사해야 함.

설치된 Chrome 재사용: channel="chrome" (브라우저 다운로드 불필요).
  pip install --user playwright

검증: momos 에티오피아 생두 21종 → 판매중 12 / 품절 9 (실제 홈페이지와 일치).
"""
import asyncio
import os

from playwright.async_api import async_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 Chrome/124.0 Safari/537.36")

# 동시에 띄울 페이지 수 (CI/로컬에서 환경변수로 조절 가능)
CONCURRENCY = int(os.environ.get("STOCK_CONCURRENCY", "8"))

# 화면에 실제 보이는 요소만 보고 품절 판정
_JS = """() => {
  const vis = el => el && el.offsetParent !== null;
  const all = [...document.querySelectorAll('button,a,span,strong')].filter(vis);
  const action = all
    .filter(b => /품절|구매하기|sold ?out|buy/i.test((b.innerText||'').trim()))
    .map(b => (b.innerText||'').trim());
  const badge = all.some(e => e.children.length === 0 && (e.innerText||'').trim() === '품절');
  return { soldout: action.some(t => /품절|sold/i.test(t)) || badge };
}"""


async def _check_async(urls, headless=True):
    out = {}
    async with async_playwright() as p:
        try:
            br = await p.chromium.launch(channel="chrome", headless=headless)  # 설치된 Chrome 우선
        except Exception:
            br = await p.chromium.launch(headless=headless)                    # CI: playwright chromium
        sem = asyncio.Semaphore(CONCURRENCY)

        async def one(key, url):
            async with sem:
                page = await br.new_page(user_agent=UA)
                try:
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2500)
                    res = await page.evaluate(_JS)
                    out[key] = bool(res["soldout"])
                except Exception:
                    out[key] = None
                finally:
                    await page.close()

        await asyncio.gather(*(one(key, url) for key, url in urls))
        await br.close()
    return out


def check_many(urls, headless=True):
    """
    urls: [(key, url)]  →  dict{key: True(품절)/False(판매중)/None(오류)}
    동시 CONCURRENCY개 페이지로 병렬 확인 (순차 대비 ~수배 빠름).
    networkidle 은 추적스크립트 때문에 타임아웃 → domcontentloaded + 대기.
    """
    return asyncio.run(_check_async(urls, headless=headless))


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from adapters import cafe24
    base = "https://momos.co.kr"
    rows = cafe24.search(base, ["에티오피아", "ethiopia"])
    urls = [(slug, cafe24.product_url(base, slug, no)) for no, slug in rows]
    res = check_many(urls)
    avail = [k for k, v in res.items() if v is False]
    sold = [k for k, v in res.items() if v is True]
    print(f"판매중 {len(avail)} / 품절 {len(sold)}")
    for k in avail:
        print("  ✅", k.replace("생두-", "").replace("-", " "))
    for k in sold:
        print("  ❌", k.replace("생두-", "").replace("-", " "))
