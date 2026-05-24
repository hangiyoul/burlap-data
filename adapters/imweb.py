"""imweb 어댑터 (ayantu) — 헤드리스 전용 (SPA, JS 렌더).

⚠️ imweb은 SPA라 정적 HTML에 상품 없음 → Playwright 필수.
구조 (ayantu 실측):
  - 생두 카테고리: /{category}            예: /greenbean
  - 카테고리 페이지네이션: ?page=N         ← 끝까지 순회 필수(스크롤만으론 다음페이지 X)
  - 상품 상세: /?idx={NNN}
  - 상품명 = 상세 <title> ("아얀투 에티오피아 생두 [이름] 커피생두")
  - 가격 = 본문, 재고 = SOLDOUT/품절
  - 스펙(지역/고도/품종/컵노트) = 긴 상세 이미지 → spec_ocr 로 OCR

설치된 Chrome 재사용: channel="chrome".
검증: ayantu /greenbean → page1 9 + page2 4 = 에티오피아 생두 13종(판매중 12 + 품절 1).
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 Chrome/124.0 Safari/537.36")


def _clean_name(title):
    """상세 title → 상품명. '아얀투/AYANTU 에티오피아 생두 [이름] 커피생두' 패턴."""
    t = re.sub(r"\s+", " ", title or "").strip()
    t = re.sub(r"\|.*$", "", t).strip()                       # ' | 사이트명' 제거
    t = re.sub(r"^(아얀투|AYANTU)\s*", "", t, flags=re.I)
    t = re.sub(r"커피\s*생두\s*$", "", t).strip()
    return t


def search(base, category, keywords, max_pages=10, headless=True):
    """카테고리를 page 순회하며 산지 상품 수집.
    return: [(idx, name, price, in_stock, url)]"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=headless)
        page = br.new_page(user_agent=UA)

        # 1) 페이지네이션 순회하며 idx 수집
        idxs, seen_page = [], set()
        for n in range(1, max_pages + 1):
            page.goto(f"{base}/{category}?page={n}", timeout=40000, wait_until="domcontentloaded")
            for y in range(0, 8000, 600):
                page.evaluate(f"window.scrollTo(0,{y})"); page.wait_for_timeout(120)
            page.wait_for_timeout(1500)
            page_idxs = page.evaluate(
                """()=>[...new Set([...document.querySelectorAll('a[href*="idx="]')]"""
                """.map(a=>a.href.match(/idx=(\\d+)/)?.[1]).filter(Boolean))]""")
            new = [i for i in page_idxs if i not in idxs]
            if not new:
                break
            idxs += new

        # 2) 각 상품 상세 → 이름/가격/재고/산지
        out = []
        for idx in idxs:
            try:
                page.goto(f"{base}/?idx={idx}", timeout=40000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                d = page.evaluate("""()=>{
                  const body=document.body.innerText.replace(/\\s+/g,' ');
                  const buyArea=body.split('상세정보')[0];   // 구매부(리뷰/QA 앞)
                  return {title:document.title, body, buyArea};
                }""")
                name = _clean_name(d["title"])
                if not any(k.lower() in (name + d["body"][:200]).lower() for k in keywords):
                    continue
                m = re.search(r"([0-9][0-9,]{3,})\s*원", d["body"])
                price = m.group(0) if m else None
                sold = ("SOLDOUT" in d["buyArea"].upper().replace(" ", "")
                        or "품절" in d["buyArea"])
                out.append((idx, name, price, not sold, f"{base}/?idx={idx}"))
            except Exception:
                continue
        br.close()
    return out


if __name__ == "__main__":
    rows = search("https://ayantu.co.kr", "greenbean", ["에티오피아", "ethiopia"])
    instock = [r for r in rows if r[3]]
    print(f"ayantu 에티오피아 생두 {len(rows)}종 (판매중 {len(instock)})\n")
    for idx, name, price, ok, url in rows:
        print(f"  {'✅' if ok else '❌'} {name[:34]:34} {price or '-':>10}  {url}")
