"""표준 스키마 — 어떤 업체/플랫폼에서 왔든 결과는 이 한 모양.

원칙: fetch 어댑터는 제각각(slug/링크텍스트/alt/텍스트표)이지만,
extract/pipeline 을 거치면 모두 GreenBean 으로 정규화 → 앱/DB는 한 형태만 소비.

Cupping Spoon 산지 모델과 필드명 정합(FINDINGS §6) → "발견→구매→커핑평가" 데이터 연결.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from datetime import datetime, timezone


@dataclass
class GreenBean:
    # --- 출처 ---
    vendor: str                       # 업체 키 (momos, cobeans, ...)
    url: str                          # 원본 상품 페이지 (딥링크)
    raw_name: str                     # 수집 원문 상품명 (정규화 전)

    # --- 산지 정보 (Cupping Spoon originXXX 와 매핑) ---
    origin: Optional[str] = None      # 국가      ↔ originCountry
    region: Optional[str] = None      # 지역      ↔ originRegion
    farm: Optional[str] = None        # 농장/로트  ↔ originFarm
    producer: Optional[str] = None    # 생산자    ↔ originFarmer
    altitude: Optional[str] = None    # 고도      ↔ originAltitude
    variety: Optional[str] = None     # 품종      ↔ originVariety
    process: Optional[str] = None     # 가공      ↔ originProcess
    grade: Optional[str] = None       # 등급(G1, Q1 ...)
    cup_notes: List[str] = field(default_factory=list)   # 컵노트

    # --- 거래 정보 (시계열로 축적 → 해자) ---
    price: Optional[str] = None       # 가격(원문 문자열, 파싱 별도)
    in_stock: Optional[bool] = None   # 재고 (헤드리스 판정; None=미확인)
    moisture: Optional[str] = None
    density: Optional[str] = None
    score: Optional[str] = None       # 컵 스코어(+87.5 등)
    arrival: Optional[str] = None     # 입항(2026.04 등)

    # --- 메타 ---
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return asdict(self)


# 헤드리스 OCR(spec_ocr.py)이 뽑는 스펙 카드 12필드 → GreenBean 매핑 키
SPEC_TO_FIELD = {
    "origin": "origin", "region": "region", "farm/lot": "farm", "producer": "producer",
    "altitude": "altitude", "moisture": "moisture", "density": "density",
    "varietal": "variety", "process": "process", "score": "score",
    "arrival": "arrival", "cupping_note": "cup_notes",
}
