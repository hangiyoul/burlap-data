"""cobeans 어댑터 (자체 PHP) — 가장 깔끔(텍스트 풀스펙).

- 검색: /shop/search_result.php?search_str=&page=
- 상세: /shop/detail.php?pno={32자리 HEX}
- 상세페이지에 라벨:값 표로 풀스펙 존재.
- 주의(오탐): "판매가"→환불정책 문구, "농장"→"방문하기" 버튼이 잡힘.
  단순 정규식은 한계 → 실제 운영은 LLM 추출 권장. 아래는 best-effort 정규식.
- 세트상품("커피지도 세트"), "입고예정"(스펙 미공개) 필터링 필요.

검증: 에티오피아 22종(세트 1 제외 21), 콜롬비아 17종.
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import get, strip_tags, unescape, matches  # noqa: E402

BASE = "https://www.cobeans.com"
FIELDS = {
    "region":   ["지역"],
    "farm":     ["농장"],
    "altitude": ["고도", "해발"],
    "variety":  ["품종"],
    "process":  ["가공", "프로세스", "가공방식"],
    "cupnote":  ["컵노트", "컵 노트", "노트", "향미"],
}


def search(keywords, max_pages=4):
    """return: [(pno, name)]"""
    seen = {}
    for kw in keywords:
        for pg in range(1, max_pages + 1):
            try:
                s = get(f"{BASE}/shop/search_result.php?search_str={kw}&page={pg}")
            except Exception:
                break
            new = 0
            for pno, c in re.findall(r"detail\.php\?pno=([0-9A-F]{32})[^>]*>(.{0,220}?)</a>", s, re.S):
                nm = strip_tags(c)
                if pno in seen or not nm:
                    continue
                if matches(nm, keywords):
                    seen[pno] = re.sub(r"[◼■]", "", nm).strip()
                    new += 1
            if new == 0 and pg > 1:
                break
    return list(seen.items())


def detail(pno):
    """단일 상품 상세 → dict(best-effort 정규식). 운영은 LLM 추출 권장."""
    html = get(f"{BASE}/shop/detail.php?pno={pno}")
    txt = re.sub(r"[ \t]+", " ", unescape(re.sub(r"<[^>]+>", "\n", html)))
    out = {}
    for key, labels in FIELDS.items():
        val = ""
        for lb in labels:
            m = re.search(rf"{lb}\s*[:：]?\s*\n?\s*([^\n]{{1,45}})", txt)
            if m and m.group(1).strip():
                val = m.group(1).strip()
                break
        out[key] = val
    return out


if __name__ == "__main__":
    rows = search(["에티오피아", "ethiopia"])
    print(f"cobeans 에티오피아 {len(rows)}종")
    for pno, nm in rows[:5]:
        d = detail(pno)
        print(f"  - {nm[:30]} | {d.get('region')} | {d.get('altitude')} | {d.get('process')}")
