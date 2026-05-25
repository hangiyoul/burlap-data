"""시장 지표 헤드라인 스크레이핑 → data/market.json (자체 시계열 적립).

스크레이핑이 필요한 참조 지표(무료 클라이언트 API 없음):
  - Freight Index = Baltic Dry Index (BDI)   ← 현재 구현
  - ICO Composite / ICE Certified Stocks      ← 소스 확정 후 추가 (TODO)

매 실행 시 오늘 값을 history 에 append(최근 365개 유지) → 시간이 지나며 차트 이력이 쌓임.
크롤 스케줄(crawl.yml)에 함께 돌리면 하루 3회 갱신.
이후: cp data/market.json Burlap/Burlap/market.json → 앱 재빌드

⚠️ 출처 약관: 데이터 재판매 사이트(예: tradingeconomics) 스크레이핑은 약관 주의.
   "지연·참고용 + 출처표기"로 운영하고, 가능하면 1차 출처로 교체 권장.
"""
import json
import os
import re
import shutil
import urllib.request
from datetime import datetime, timezone

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "market.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")


def scrape_container_freight():
    """컨테이너 운임 지수(Containerized Freight Index) — 커피는 컨테이너 운송이라 BDI보다 적합."""
    html = fetch("https://tradingeconomics.com/commodity/containerized-freight-index")
    m = re.search(r"Containerized Freight Index[^0-9]{0,40}?([\d,]+(?:\.\d+)?)\s*Points", html, re.I)
    if not m:
        m = re.search(r"([\d,]+\.\d+)\s*Points", html)
    return float(m.group(1).replace(",", "")) if m else None


def load():
    if os.path.exists(DATA):
        try:
            return json.load(open(DATA, encoding="utf-8"))
        except Exception:
            pass
    return {"metrics": {}}


# 일별 1포인트로 최대 ~5.5년 보관
_HISTORY_CAP = 2000


def append_point(metrics, title, value, unit, fmt="{:,.0f}"):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    m = metrics.get(title, {})
    hist = list(m.get("history") or [])
    dates = list(m.get("dates") or [])
    # 구버전(날짜 없음/길이 불일치) → 평평한 레거시 버리고 날짜 기반으로 새로 시작
    if len(dates) != len(hist):
        hist, dates = [], []
    # 하루 1회: 오늘 점이 이미 있으면 값 갱신, 없으면 추가 (크롤이 하루 3번 돌아도 1점/일)
    if dates and dates[-1] == today:
        hist[-1] = value
    else:
        hist.append(value)
        dates.append(today)
    hist = hist[-_HISTORY_CAP:]
    dates = dates[-_HISTORY_CAP:]
    prev = hist[-2] if len(hist) >= 2 else value
    chg = (value - prev) / prev * 100 if prev else 0.0
    metrics[title] = {
        "value": fmt.format(value),
        "unit": unit,
        "changePct": round(chg, 2),
        "history": hist,
        "dates": dates,   # history 와 1:1 정렬 (YYYY-MM-DD)
    }


def main():
    payload = load()
    metrics = payload.get("metrics", {})

    cfi = None
    try:
        cfi = scrape_container_freight()
    except Exception as e:
        print("운임 스크레이프 오류:", type(e).__name__, e)
    if cfi:
        append_point(metrics, "Freight Index", cfi, "pt", fmt="{:,.1f}")
        print(f"Freight Index (Container): {cfi:,.1f}  (history {len(metrics['Freight Index']['history'])}pt)")
    else:
        print("운임 스크레이프 실패 — 이번 회차 건너뜀")

    # 스페셜티 경매 결과 — COE + Best of Panama(BOP) 통합 (변화 감지 후 델타만 크롤)
    try:
        import coe_scrape
        existing_all = payload.get("coe_auctions", []) or []
        existing_coe = [a for a in existing_all if a.get("country") != "panama"]
        existing_bop = [a for a in existing_all if a.get("country") == "panama"]

        coe_metric, coe_auctions = coe_scrape.to_metric(existing=existing_coe)
        coe_auctions = coe_auctions or []
        bop_auctions = []
        try:
            import bop_scrape
            bop_auctions = bop_scrape.to_auctions(existing=existing_bop)
        except Exception as e:
            print("BOP 스크레이프 오류:", type(e).__name__, e)
            bop_auctions = existing_bop                     # 실패 → 기존 BOP 보존
        all_auctions = coe_auctions + bop_auctions

        # 안전장치 ⑤ 정합성 게이트 — 경매/로트 수가 줄면 쓰기 중단(기존 유지)
        if existing_all:
            old_lots = sum(len(a.get("lots", [])) for a in existing_all)
            new_lots = sum(len(a.get("lots", [])) for a in all_auctions)
            if len(all_auctions) < len(existing_all) or new_lots < old_lots * 0.8:
                print(f"⚠️ 경매/로트 급감 감지(경매 {len(existing_all)}→{len(all_auctions)}, "
                      f"로트 {old_lots}→{new_lots}) — 기존 데이터 유지")
                all_auctions = existing_all
                coe_metric = coe_metric or {"value": metrics.get("Specialty Auction", {}).get("value", "—"),
                                            "unit": "$/lb", "changePct": 0.0,
                                            "history": [a.get("medianBid", 0) for a in existing_all]}

        # BOP 스토리 한국어 번역(키 있을 때만, 캐시 사용)
        try:
            import translate
            n = translate.translate_auctions(all_auctions)
            if n:
                print(f"스토리 번역: {n}건 신규")
        except Exception as e:
            print("스토리 번역 오류:", type(e).__name__, e)
        if all_auctions:
            # 카드 헤드라인: COE 최신 중앙값(대표값). 없으면 첫 경매 중앙값.
            metric = coe_metric or {
                "value": f"{all_auctions[-1]['medianBid']:.1f}", "unit": "$/lb",
                "changePct": 0.0, "history": [a["medianBid"] for a in all_auctions],
            }
            metrics["Specialty Auction"] = metric
            payload["coe_auctions"] = all_auctions
            total_lots = sum(len(a["lots"]) for a in all_auctions)
            print(f"Specialty Auction: COE {len([a for a in all_auctions if a['country']!='panama'])} "
                  f"+ BOP {len([a for a in all_auctions if a['country']=='panama'])} "
                  f"= {len(all_auctions)}개 경매 · 로트 {total_lots}건")
    except Exception as e:
        print("스페셜티 경매 스크레이프 오류:", type(e).__name__, e)

    payload["metrics"] = metrics
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    if os.path.exists(DATA):                       # 안전장치 ⑦ 덮어쓰기 전 백업
        try:
            shutil.copyfile(DATA, DATA + ".bak")
        except Exception as e:
            print("백업 실패(무시):", type(e).__name__, e)
    json.dump(payload, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("저장:", DATA)


if __name__ == "__main__":
    main()
