"""제휴사 데이터 피드 어댑터 — 크롤링 대신 '판매자가 제공한 데이터'를 읽음.

크롤링이 막힌 곳(네이버 스마트스토어: gimisa 등)을 제휴로 우회하는 정공법.
판매자는 구글시트만 관리, Burlap이 자동 구독 → 재고/가격이 늘 정확(판매자 소유).
출력은 표준 GreenBean → 크롤링 업체와 100% 동일하게 합류.

지원 소스:
  - gsheet  : 서비스 계정으로 비공개 구글시트 읽기 (선택적 공유 유지)  ⭐ 권장
  - csv_url : 공개 CSV URL (테스트/간단용, 인증 불필요)

── 서비스 계정 셋업 (최초 1회) ──
  1. GCP 프로젝트 → Google Sheets API 활성화 → 서비스 계정 생성 → 키 JSON 다운로드
  2. 판매자가 자기 시트를 '서비스계정 이메일'에 **보기(view)** 권한으로 공유
     → 시트는 비공개 유지(로봇 이메일 + 판매자만 접근). view-only라 우리가 수정 불가.
  3. 키 JSON은 백엔드 시크릿: 환경변수 GOOGLE_APPLICATION_CREDENTIALS = 키 경로
     (절대 앱/클라이언트에 넣지 말 것)

의존성(gsheet 모드): pip install google-api-python-client google-auth
"""
import os
import sys
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schema import GreenBean  # noqa: E402

# 시트 헤더(한/영) → GreenBean 필드
HEADER_MAP = {
    "상품명": "name", "상품": "name", "name": "name",
    "국가": "origin", "원산지": "origin", "origin": "origin", "country": "origin",
    "지역": "region", "생산지역": "region", "region": "region",
    "농장": "farm", "농장명": "farm", "farm": "farm", "lot": "farm",
    "생산자": "producer", "producer": "producer",
    "고도": "altitude", "재배고도": "altitude", "altitude": "altitude",
    "품종": "variety", "variety": "variety", "varietal": "variety",
    "가공": "process", "가공방식": "process", "process": "process",
    "등급": "grade", "grade": "grade",
    "컵노트": "cup_notes", "노트": "cup_notes", "cup_notes": "cup_notes", "cupping note": "cup_notes",
    "가격": "price", "price": "price",
    "재고": "in_stock", "stock": "in_stock", "in_stock": "in_stock",
    "상품링크": "url", "링크": "url", "url": "url", "link": "url",
}

_SOLD_WORDS = {"품절", "없음", "soldout", "sold out", "n", "no", "false", "0", "x", "off"}


def _parse_stock(v):
    s = str(v).strip().lower()
    if s in ("", "-"):
        return None
    return s not in _SOLD_WORDS


def to_greenbeans(rows, vendor):
    """rows[0]=헤더, 이하 데이터 → [GreenBean]. 알 수 없는 컬럼은 무시."""
    if not rows:
        return []
    header = [HEADER_MAP.get(str(h).strip().lower(), HEADER_MAP.get(str(h).strip(), None)) for h in rows[0]]
    beans = []
    for r in rows[1:]:
        rec = {}
        for col, val in zip(header, r):
            if col and str(val).strip():
                rec[col] = str(val).strip()
        if not rec.get("name"):
            continue
        cup = rec.get("cup_notes", "")
        beans.append(GreenBean(
            vendor=vendor,
            url=rec.get("url", ""),
            raw_name=rec.get("name", ""),
            origin=rec.get("origin"), region=rec.get("region"),
            farm=rec.get("farm"), producer=rec.get("producer"),
            altitude=rec.get("altitude"), variety=rec.get("variety"),
            process=rec.get("process"), grade=rec.get("grade"),
            cup_notes=[x.strip() for x in re.split(r"[,/·]", cup) if x.strip()],
            price=rec.get("price"),
            in_stock=_parse_stock(rec.get("in_stock", "")),
        ))
    return beans


def read_gsheet(sheet_id, rng="A1:Z2000", creds_path=None):
    """서비스 계정으로 비공개 구글시트 읽기. return: rows(list[list])."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    creds_path = creds_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not os.path.exists(creds_path):
        raise RuntimeError("서비스 계정 키 없음: 환경변수 GOOGLE_APPLICATION_CREDENTIALS 설정 필요")
    creds = Credentials.from_service_account_file(
        creds_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    res = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range=rng).execute()
    return res.get("values", [])


def read_csv_url(url):
    """공개 CSV URL 읽기 (인증 불필요). return: rows(list[list])."""
    import csv
    import io
    from common import get
    return list(csv.reader(io.StringIO(get(url))))


def fetch(vendor, cfg, keywords=None):
    """config 의 source(gsheet/csv_url)에 따라 피드 읽어 GreenBean 리스트 반환."""
    src = cfg.get("source")
    if src == "gsheet":
        rows = read_gsheet(cfg["sheet_id"], cfg.get("range", "A1:Z2000"))
    elif src == "csv_url":
        rows = read_csv_url(cfg["csv_url"])
    else:
        return []
    beans = to_greenbeans(rows, vendor)
    if keywords:
        beans = [b for b in beans
                 if any(k.lower() in ((b.raw_name or "") + " " + (b.origin or "")).lower()
                        for k in keywords)]
    return beans


if __name__ == "__main__":
    # 로컬 테스트: 동봉된 템플릿 CSV 로 동작 확인 (서비스계정 불필요)
    import csv
    tmpl = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config", "partner_feed_template.csv")
    with open(tmpl, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    beans = to_greenbeans(rows, "gimisa")
    print(f"템플릿에서 {len(beans)}건 파싱:")
    for b in beans:
        print(f"  - {b.raw_name} | {b.region} | {b.altitude} | {b.process} | 재고={b.in_stock} | {b.cup_notes}")
