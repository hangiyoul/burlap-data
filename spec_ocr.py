"""스펙 이미지 추출 (헤드리스 + 채도선별) — momos/royalcoffee 검증됨.

momos/royalcoffee 는 스펙(국가/지역/농장/생산자/고도/수분/밀도/품종/가공/점수/입항/컵노트)이
'이미지'로 박혀 있음. 파이프라인:
  1. Playwright 로 상세 렌더 + 스크롤(지연로딩 유발)
  2. 모든 <img> 의 src/크기 수집
  3. 스펙표 = 저채도(회색 배경, HSV S평균 ≈ 2.0) + 대략 1000×(660~800)
     ※ '주문안내' 이미지도 회색이므로 크기/내용으로 추가 구분 필요
  4. 선별 이미지를 비전 모델(Claude 등)로 OCR → 정형 JSON

이 스크립트는 (1)~(3) '스펙표 이미지 다운로드'까지 자동화.
(4) OCR 은 비전 모델 호출(예: Anthropic API)로 연결 — 자리만 표시.

검증: momos 12종 전부 스펙표 이미지 정확 선별 성공.

의존성: pip install --user playwright Pillow
"""
import io
import os
from playwright.sync_api import sync_playwright
from PIL import Image

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get_bytes  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 Chrome/124.0 Safari/537.36")


def _saturation(b):
    """이미지 평균 채도(0~255). 회색 스펙표 ≈ 2, 사진은 훨씬 큼."""
    im = Image.open(io.BytesIO(b)).convert("HSV").resize((80, 60))
    s = list(im.split()[1].getdata())
    return sum(s) / len(s)


def download_spec_image(url, base, out_path,
                        w_range=(900, 1050), h_range=(640, 820), sat_max=6.0):
    """
    상세페이지(url)를 렌더 → 스펙표 후보 중 가장 저채도(회색) 이미지 저장.
    return: 저장 경로 or None
    """
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)
        page = br.new_page(user_agent=UA)
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        for y in range(0, 14000, 500):
            page.evaluate(f"window.scrollTo(0,{y})")
            page.wait_for_timeout(80)
        page.wait_for_timeout(1000)
        imgs = page.evaluate(
            "() => [...document.images].map(i => "
            "({s:(i.currentSrc||i.src), w:i.naturalWidth, h:i.naturalHeight}))")
        br.close()

    cand = [o for o in imgs
            if w_range[0] <= o["w"] <= w_range[1] and h_range[0] <= o["h"] <= h_range[1]]
    best, best_sat = None, 999.0
    seen = set()
    for o in cand:
        k = o["s"].split("/")[-1]
        if k in seen:
            continue
        seen.add(k)
        try:
            b = get_bytes(o["s"], base=base, referer=base + "/")
            sat = _saturation(b)
            if sat < sat_max and sat < best_sat:
                best_sat, best = sat, b
        except Exception:
            pass
    if best:
        with open(out_path, "wb") as f:
            f.write(best)
        return out_path
    return None


# ── (4) OCR 자리: 비전 모델로 스펙표 이미지 → JSON ──
SPEC_SCHEMA = ["origin", "region", "farm/lot", "producer", "altitude",
               "moisture", "density", "varietal", "process", "score",
               "arrival", "cupping_note"]

OCR_PROMPT = (
    "이 커피 스펙 카드 이미지에서 다음 필드를 JSON으로 정확히 추출하세요(없으면 null): "
    + ", ".join(SPEC_SCHEMA) + ". 라벨이 한글/영문 어느 쪽이든 값만 뽑으세요."
)


def ocr_spec(image_path, vendor="", url="", origin_hint=None):
    """스펙카드 이미지 → 표준 GreenBean. extract.normalize_with_llm(비전) 위임.
    키/SDK 없으면 normalize_with_llm 내부에서 규칙 폴백(스펙 텍스트가 없으니 빈 결과일 수 있음)."""
    from extract import normalize_with_llm
    return normalize_with_llm(vendor, url, image_path=image_path, origin_hint=origin_hint)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from adapters import cafe24
    base = "https://momos.co.kr"
    rows = cafe24.search(base, ["에티오피아", "ethiopia"])   # [(no, name, url)]
    no, name, url = rows[0]
    path = download_spec_image(url, base, "/tmp/spec_demo.jpg")
    print("스펙표 저장:", path)
    print("→ ocr_spec(path, vendor='momos', url=url, origin_hint='Ethiopia') 로 추출")
