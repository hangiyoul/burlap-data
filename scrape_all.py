"""전 업체 카탈로그 통합 수집 데모 (정적 어댑터).

사용: python3 scrape_all.py [origin]   # 기본 ethiopia
업체별로 산지 상품을 모아 출력. (재고/스펙은 stock_check.py / spec_ocr.py 로 별도)

검증(에티오피아): momos24, cobeans22, royalcoffee30, sewoonggc20,
                 micoffee10, newbean9, wbeans6, coffeelibre0  = 121종
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ORIGIN_KEYWORDS
from adapters import cafe24, godo, cobeans, youngcart

GODO_SITES = {
    "micoffee":    "https://www.micoffee.co.kr",
    "newbean":     "https://www.newbean.co.kr",
    "wbeans":      "https://wbeans.com",
    "royalcoffee": "https://www.royalcoffeekorea.co.kr",
}
CAFE24_SITES = {
    "momos":       "https://momos.co.kr",
    "coffeelibre": "https://coffeelibre.kr",
}
YOUNGCART_SITES = {
    "sewoonggc":   "https://www.sewoonggc.com",
}

# 헤드리스 필요(미구현 — 정적 불가): ayantu(imweb), gimisa(sixshop),
#   verde_trade/ryubeans(네이버 스마트스토어). 추후 Playwright 어댑터 추가.
HEADLESS_NEEDED = ["ayantu", "gimisa", "verde_trade", "ryubeans"]


def run(origin="ethiopia"):
    kws = ORIGIN_KEYWORDS.get(origin, [origin])
    results = {}

    for name, base in CAFE24_SITES.items():
        try:
            results[name] = [slug.replace("생두-", "").replace("-", " ")
                             for _, slug in cafe24.search(base, kws)]
        except Exception as e:
            results[name] = [f"<error {e}>"]

    for name, base in GODO_SITES.items():
        try:
            results[name] = [nm for _, nm in godo.search(base, kws)]
        except Exception as e:
            results[name] = [f"<error {e}>"]

    try:
        results["cobeans"] = [nm for _, nm in cobeans.search(kws)]
    except Exception as e:
        results["cobeans"] = [f"<error {e}>"]

    for name, base in YOUNGCART_SITES.items():
        try:
            results[name] = [nm for _, nm in youngcart.search(base, kws)]
        except Exception as e:
            results[name] = [f"<error {e}>"]

    total = 0
    for name, items in results.items():
        total += len(items)
        print(f"\n===== {name} ({len(items)}종) =====")
        for it in items:
            print("  -", it[:60])
    print(f"\n>>> 정적 수집 합계: {total}종")
    print(f">>> 헤드리스 필요(미수집): {', '.join(HEADLESS_NEEDED)}")
    return results


if __name__ == "__main__":
    origin = sys.argv[1] if len(sys.argv) > 1 else "ethiopia"
    run(origin)
