"""파이프라인 — config 기반으로 fetch → 정규화 → 표준 GreenBean 수집.

흐름: vendors.json(active) → platform별 어댑터 dispatch → 상품목록 수집
      → extract(규칙/LLM)로 GreenBean 정규화 → 리스트 반환
재고/스펙(헤드리스)은 enrich 단계로 분리 (stock_check.py / spec_ocr.py).

사용: python3 pipeline.py [origin]   # 기본 ethiopia
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import ORIGIN_KEYWORDS
from config import active_vendors
from extract import normalize_with_rules
from adapters import cafe24, godo, cobeans, youngcart


def _fetch_catalog(vendor, cfg, keywords):
    """platform 별 어댑터 dispatch → [(url, name)]"""
    p, base = cfg["platform"], cfg.get("base")
    if p == "cafe24":
        # 어댑터가 두 URL 스킨 모두 처리 → (no, name, url)
        return [(url, name) for no, name, url in cafe24.search(base, keywords)]
    if p == "godo":
        out = []
        for gid, name in godo.search(base, keywords, name_mode=cfg.get("name_mode", "auto")):
            url = godo.view_url(base, gid) if gid.isdigit() else base
            out.append((url, name))
        return out
    if p == "cobeans":
        return [(f"{base}/shop/detail.php?pno={pno}", name) for pno, name in cobeans.search(keywords)]
    if p == "youngcart":
        return [(youngcart.item_url(base, iid), name) for iid, name in youngcart.search(base, keywords)]
    if p == "imweb":
        # 헤드리스 엔진 (Playwright 필요, 느림). 판매중만 카탈로그에 포함.
        from adapters import imweb
        rows = imweb.search(base, cfg.get("category", "greenbean"), keywords)
        return [(url, name) for idx, name, price, in_stock, url in rows if in_stock]
    return []  # sixshop/smartstore → 헤드리스 어댑터 추가 예정


def run(origin="ethiopia"):
    keywords = ORIGIN_KEYWORDS.get(origin, [origin])
    origin_label = origin.capitalize()
    beans = []
    per_vendor = {}
    for vendor, cfg in active_vendors().items():
        try:
            # 제휴 피드(gsheet/csv_url): 판매자 제공 데이터 → 이미 GreenBean 완성형
            if cfg.get("source") in ("gsheet", "csv_url"):
                from adapters import feed
                vbeans = feed.fetch(vendor, cfg, keywords)
                beans.extend(vbeans)
                per_vendor[vendor] = f"{len(vbeans)} (partner)"
                continue
            # 크롤링 업체: 카탈로그 → 규칙 정규화
            catalog = _fetch_catalog(vendor, cfg, keywords)
        except Exception as e:
            per_vendor[vendor] = f"<error {type(e).__name__}>"
            continue
        per_vendor[vendor] = len(catalog)
        for url, name in catalog:
            beans.append(normalize_with_rules(vendor, url, name, origin_hint=origin_label))
    return beans, per_vendor


if __name__ == "__main__":
    origin = sys.argv[1] if len(sys.argv) > 1 else "ethiopia"
    beans, per_vendor = run(origin)
    for v, n in per_vendor.items():
        print(f"  {v:14} {n}")
    print(f"\n표준 GreenBean {len(beans)}건 (정적). 샘플:")
    for b in beans[:5]:
        print(f"  - [{b.vendor}] {b.raw_name[:34]:34} variety={b.variety} process={b.process}")
    print("\n→ 재고/스펙은 stock_check.py / spec_ocr.py(헤드리스)로 enrich.")
    print("→ 정밀 추출은 extract.normalize_with_llm 연결 시 완성.")
