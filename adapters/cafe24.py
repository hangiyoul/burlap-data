"""Cafe24 어댑터 (momos, coffeelibre).

⚠️ Cafe24는 스킨에 따라 상품 URL 패턴이 2가지 (실측 발견):
  A) /product/{slug}/{no}/category/...      → 상품명 = slug   (예: momos)
  B) /product/detail.html?product_no={no}   → 상품명 = 링크텍스트 (예: coffeelibre)
search() 가 두 패턴을 모두 처리해 (no, name, url) 통일 반환.

- 한글+영문 키워드 둘 다 순회 (영문 slug 누락 방지)
- green_only: 패턴A는 slug '생두-' prefix, 패턴B는 이름에 '생두' 포함으로 판정
- 텍스트 스펙 사이트(coffeelibre)는 detail_text()로 지역/고도/품종/가공/농장 추출
- 이미지 스펙 사이트(momos)는 spec_ocr.py(헤드리스+OCR) 사용
- 재고는 정적 불가 → stock_check.py(헤드리스)

검증: momos 에티오피아 생두 21종 / coffeelibre 과테말라 생두 17종.
"""
import re
import sys
import os
from urllib.parse import unquote
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import get, strip_tags, matches  # noqa: E402

SKIP_PREFIX = ("드립백", "캡슐", "콜드브루", "드립-")


def product_url_slug(base, slug, no, cat=1):
    return f"{base}/product/{slug}/{no}/category/{cat}/display/1/"


def product_url_detail(base, no):
    return f"{base}/product/detail.html?product_no={no}"


def search(base, keywords, green_only=True, max_pages=6):
    """두 Cafe24 스킨 모두 지원. return: [(no, name, url)]"""
    seen = {}
    for kw in keywords:
        for pg in range(1, max_pages + 1):
            try:
                s = get(f"{base}/product/search.html?keyword={kw}&page={pg}")
            except Exception:
                break
            new = 0
            # 패턴 A: slug 기반 (name = slug)
            for slug, no in re.findall(r"/product/([^/]+)/(\d+)/category/\d+", s):
                if no in seen:
                    continue
                dn = unquote(slug)
                if not matches(dn, keywords):
                    continue
                if green_only and not dn.startswith("생두-"):
                    continue
                if dn.startswith(SKIP_PREFIX):
                    continue
                seen[no] = (dn.replace("생두-", "").replace("-", " ").strip(),
                            product_url_slug(base, slug, no))
                new += 1
            # 패턴 B: detail.html?product_no= (name = 링크텍스트)
            for no, chunk in re.findall(r'detail\.html\?product_no=(\d+)[^>]*>(.{0,300}?)</a>', s, re.S):
                if no in seen:
                    continue
                nm = strip_tags(chunk)
                if not nm or len(nm) < 3 or not matches(nm, keywords):
                    continue
                if green_only and "생두" not in nm:
                    continue
                seen[no] = (re.sub(r"\[[^\]]*\]", "", nm).strip(), product_url_detail(base, no))
                new += 1
            if new == 0 and pg > 1:
                break
    return [(no, name, url) for no, (name, url) in seen.items()]


# --- 텍스트 스펙 추출 (coffeelibre형: 라벨 + 영문 병기) ---
_CL_FIELDS = {
    "farm": ("농장명", "생산자|지역|재배고도"),
    "producer": ("생산자", "지역|재배고도"),
    "region": ("지역", "재배고도|품종"),
    "altitude": ("재배고도", "품종|가공"),
    "variety": ("품종", "가공방식|입고|가공"),
    "process": ("가공방식", "입고일자|입고|상품|수상|원산지"),
}


def _eng_tail(v):
    """'한글 ... English' → 끝의 영문부만 (영문 병기 추출)."""
    m = re.search(r"([A-Za-z][A-Za-z0-9 .,&'\-/]+)$", v.strip())
    return m.group(1).strip() if m else v.strip()


def detail_text(url, prefer_english=True):
    """텍스트 스펙 상세 추출(best-effort). 컵노트는 LLM 권장(레이아웃 흔들림).
    return: dict(region, altitude, variety, process, farm, producer, cup_notes_kr)"""
    import html as H
    h = get(url)
    txt = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ",
                 re.sub(r"<script.*?</script>", "", h, flags=re.S))))
    out = {}
    for key, (label, stop) in _CL_FIELDS.items():
        m = re.search(re.escape(label) + r"\s*:?\s*(.*?)\s*(?:" + stop + ")", txt)
        v = m.group(1).strip() if m else ""
        out[key] = _eng_tail(v) if (prefer_english and key in ("region", "variety", "process", "farm")) else v
    # 컵노트: '농장명' 앞 trailing 한글 토큰 (결제팝업 등 노이즈 가드)
    pre = txt.split("농장명")[0]
    notes = []
    for t in reversed(pre.split()):
        if re.search(r"[가-힣]", t):
            notes.insert(0, t)
        else:
            break
    joined = " ".join(notes)
    out["cup_notes_kr"] = "" if ("결제" in joined or "(주)" in joined) else joined
    return out


if __name__ == "__main__":
    for name, base, kw in [("momos", "https://momos.co.kr", ["에티오피아", "ethiopia"]),
                           ("coffeelibre", "https://coffeelibre.kr", ["과테말라", "guatemala"])]:
        rows = search(base, kw)
        print(f"\n== {name}: {len(rows)}종 ==")
        for no, nm, url in rows[:5]:
            print(f"  - {nm[:45]}")
