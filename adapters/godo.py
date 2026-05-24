"""Godo/NHN 어댑터 (micoffee, newbean, wbeans, royalcoffee).

- 검색: /goods/goods_search.php?keyword=&page=
- 상세: /goods/goods_view.php?goodsNo=
- 상품명 위치가 사이트마다 다름:
    * 링크 텍스트형 (micoffee, newbean, royalcoffee)
    * alt 속성형  (wbeans — 링크 텍스트 비어있음)
  → name_mode='auto' 가 둘 다 시도.
- royalcoffee 검색은 느슨(타산지 혼입) → 상품명에 산지 키워드 있는 것만 필터.
- 스펙이 이미지인 사이트(royalcoffee)는 spec_ocr.py 사용. 단 제목에 지역/품종/가공 다수 포함.

검증: micoffee 10, newbean 9, wbeans 6, royalcoffee 30 (에티오피아).
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import get, strip_tags, unescape, matches  # noqa: E402


def search(base, keywords, max_pages=6, name_mode="auto"):
    """
    base: 예 'https://www.micoffee.co.kr'
    return: [(goodsNo, name)]
    """
    seen = {}
    for kw in keywords:
        for pg in range(1, max_pages + 1):
            try:
                s = get(f"{base}/goods/goods_search.php?keyword={kw}&page={pg}")
            except Exception:
                break
            new = 0
            # (1) 링크 텍스트형
            if name_mode in ("auto", "link"):
                for g, c in re.findall(r"goods_view\.php\?goodsNo=(\d+)[^>]*>(.{0,220}?)</a>", s, re.S):
                    nm = strip_tags(c)
                    if g in seen or not nm:
                        continue
                    if matches(nm, keywords):
                        seen[g] = nm
                        new += 1
            # (2) alt 속성형 (wbeans) — goodsNo 매핑이 어려우면 이름만 수집
            if name_mode in ("auto", "alt") and new == 0:
                for a in re.findall(r'alt="([^"]+)"', s):
                    a = unescape(a).strip()
                    if a in seen or len(a) <= 5 or "로고" in a:
                        continue
                    if matches(a, keywords):
                        seen[a] = a  # key=name (alt형은 goodsNo 미상)
                        new += 1
            if new == 0 and pg > 1:
                break
    return list(seen.items())


def view_url(base, goods_no):
    return f"{base}/goods/goods_view.php?goodsNo={goods_no}"


if __name__ == "__main__":
    for name, base in [("micoffee", "https://www.micoffee.co.kr"),
                       ("newbean", "https://www.newbean.co.kr"),
                       ("wbeans", "https://wbeans.com"),
                       ("royalcoffee", "https://www.royalcoffeekorea.co.kr")]:
        rows = search(base, ["에티오피아", "ethiopia"])
        print(f"\n== {name}: {len(rows)}종 ==")
        for _, nm in rows[:8]:
            print("  -", nm[:55])
