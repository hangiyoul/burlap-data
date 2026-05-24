"""COE(Cup of Excellence) 경매 결과 스크레이핑 → market.json.

국가별 경매 페이지(allianceforcoffeeexcellence.org/{country}-{year}/)에서
입찰 결과 표(순위·농장·점수·낙찰가 $/lb·낙찰사)를 로트 단위로 수집하고,
같은 페이지의 상세 표(품종·가공·지역)를 점수/농장명으로 조인한다.

출력:
  market.json["metrics"]["COE Auction"]  → 홈 카드용 헤드라인(최신 경매 최고가 + 경매별 중앙값 이력)
  market.json["coe_auctions"]            → 상세 페이지용 경매별 로트 리스트

사용: python3 coe_scrape.py  (단독)  또는 market_scrape.py 에서 호출.
"""
import re
import os
import json
import unicodedata
import statistics
import urllib.request
from datetime import datetime, timezone
import html as ht

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "market.json")


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")


def _auction_slugs():
    home = _fetch("https://cupofexcellence.org/")
    return sorted(set(re.findall(r"allianceforcoffeeexcellence\.org/([a-z][a-z-]*-20\d\d)/", home)))


def _cells(tr):
    return [ht.unescape(re.sub("<[^>]+>", "", c)).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]


def _num(s):
    """'$55.10/lb' → 55.10,  '198.42lbs' → 198.42,  '91,37' → 91.37."""
    if s is None:
        return None
    t = s.strip()
    if "," in t and "." not in t:                  # 점수형 콤마 소수점: '91,37'
        t = t.replace(",", ".")
    t = re.sub(r"[^0-9.]", "", t)
    if t.count(".") > 1:                           # '1.234.56' 류 → 첫 점만 유지
        first = t.index(".")
        t = t[:first + 1] + t[first + 1:].replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def _norm_farm(name):
    """조인용 농장명 정규화 — 악센트 제거 + 접두어 제거 + 소문자."""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    n = n.lower().strip()
    n = re.sub(r"^(fazenda|sitio|finca|hacienda|granja|el|la)\s+", "", n)
    return re.sub(r"\s+", " ", n)


def _col(heads, *keys, avoid=()):
    """헤더 목록에서 키워드를 포함하는 컬럼 인덱스(피해야 할 키워드는 제외)."""
    for i, h in enumerate(heads):
        hu = h.upper()
        if any(a in hu for a in avoid):
            continue
        if any(k in hu for k in keys):
            return i
    return None


def _detail_lookup(tables):
    """품종/가공/지역 상세표 → ({정규화농장명: info}, {점수문자열: info})."""
    by_farm, by_score = {}, {}
    for heads, rows in tables:
        vi = _col(heads, "VARIETY", "VARIETAL")
        pi = _col(heads, "PROCESS")
        if vi is None or pi is None:
            continue
        fi = _col(heads, "FARM", "CWS")
        ri = _col(heads, "REGION")
        wi = _col(heads, "FARMER", "PRODUCER")
        si = _col(heads, "SCORE")
        for cells in rows:
            if fi is None or len(cells) <= fi:
                continue
            info = {
                "variety": cells[vi] if vi is not None and len(cells) > vi else "",
                "process": cells[pi] if pi is not None and len(cells) > pi else "",
                "region":  cells[ri] if ri is not None and len(cells) > ri else "",
                "farmer":  cells[wi] if wi is not None and len(cells) > wi else "",
            }
            if not any(info.values()):
                continue
            by_farm.setdefault(_norm_farm(cells[fi]), info)
            if si is not None and len(cells) > si:
                sc = _num(cells[si])
                if sc is not None:
                    by_score.setdefault(f"{sc:.2f}", info)
    return by_farm, by_score


def _lots_from(tables, detail_farm, detail_score):
    """입찰 결과표(들) → 로트 리스트. 같은 경매의 분할표를 모두 합친다."""
    lots = []
    for heads, rows in tables:
        bi = _col(heads, "BID", avoid=("TOTAL",))
        fi = _col(heads, "FARM", "CWS")
        if bi is None or fi is None:                 # 입찰표가 아님(심사위원/요약 표 등)
            continue
        ri = _col(heads, "RANK", "LOT", "#")
        sci = _col(heads, "SCORE")
        wi = _col(heads, "WEIGHT", "POUNDS", "LB")
        ti = _col(heads, "TOTAL")
        ci = _col(heads, "COMPANY", "BUSINESS", "BUYER")
        for cells in rows:
            if len(cells) <= max(bi, fi):
                continue
            bid = _num(cells[bi])
            farm = cells[fi].strip()
            if bid is None or not farm or not (0.5 <= bid <= 1000):
                continue
            score = _num(cells[sci]) if sci is not None and len(cells) > sci else None
            det = (detail_score.get(f"{score:.2f}") if score is not None else None) \
                  or detail_farm.get(_norm_farm(farm)) or {}
            lots.append({
                "rank":     (cells[ri].strip() if ri is not None and len(cells) > ri else ""),
                "farm":     farm,
                "score":    round(score, 2) if score is not None else None,
                "bid":      round(bid, 2),
                "weightLb": _num(cells[wi]) if wi is not None and len(cells) > wi else None,
                "total":    _num(cells[ti]) if ti is not None and len(cells) > ti else None,
                "company":  (cells[ci].strip() if ci is not None and len(cells) > ci else ""),
                "variety":  det.get("variety", ""),
                "process":  det.get("process", ""),
                "region":   det.get("region", ""),
                "farmer":   det.get("farmer", ""),
            })
    lots.sort(key=lambda x: x["bid"], reverse=True)   # 낙찰가 높은 순(상위 로트)
    return lots


def _country_label(country, year):
    name = " ".join(w.capitalize() for w in country.split("-"))
    return f"COE {name} {year}"


def _scrape_one(country, year, slug):
    """경매 1개 페이지 → 경매 dict(또는 None). 예외는 호출측에서 처리."""
    html = _fetch(f"https://allianceforcoffeeexcellence.org/{slug}/")
    tables = []
    for t in re.findall(r"<table.*?</table>", html, re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I)
        if len(rows) < 2:
            continue
        heads = [c.upper() for c in _cells(rows[0])]
        body = [_cells(r) for r in rows[1:]]
        tables.append((heads, body))
    d_farm, d_score = _detail_lookup(tables)
    lots = _lots_from(tables, d_farm, d_score)
    if len(lots) < 5:
        return None
    bids = [l["bid"] for l in lots]
    med = round(statistics.median(bids), 2)
    if med > 200:                                # 파싱 이상치(총액 혼입 등) → 제외
        return None
    return {
        "country": country, "year": year,
        "label": _country_label(country, year),
        "topBid": round(max(bids), 2), "medianBid": med, "lots": lots,
    }


def scrape(existing=None):
    """변화 감지 후 델타만 크롤. existing=기존 COE 경매 리스트(재사용/보존용).

    안전장치: ①인덱스 실패→전체 보존  ②경매별 실패→기존 폴백
              ③회귀(로트 감소)→기존 유지  ④인덱스에서 빠진 기존 경매도 보존
    """
    existing = existing or []
    ex_map = {(a.get("country"), a.get("year")): a for a in existing}
    try:
        slugs = _auction_slugs()
    except Exception as e:
        print("COE 인덱스 조회 실패 → 기존 데이터 유지:", type(e).__name__, e)
        return list(existing)

    live = []
    for slug in slugs:
        m = re.match(r"(.+)-(\d{4})$", slug)
        if m:
            live.append((m.group(1), int(m.group(2)), slug))
    if not live:
        print("COE 슬러그 0개 → 기존 데이터 유지")
        return list(existing)

    latest_year = max(y for _, y, _ in live)
    result = {}
    for country, year, slug in live:
        key = (country, year)
        prev = ex_map.get(key)
        if prev and year < latest_year:          # 이전 연도는 동결(결과 확정)
            result[key] = prev
            continue
        try:
            a = _scrape_one(country, year, slug)
        except Exception as e:
            a = None
            print(f"  COE {slug} 크롤 실패:", type(e).__name__, e)
        if a is None:
            if prev:
                result[key] = prev               # 실패 → 기존 유지
            continue
        if prev and len(a["lots"]) < len(prev.get("lots", [])):
            result[key] = prev                   # 회귀 방지: 적게 나오면 기존
        else:
            result[key] = a
    for key, a in ex_map.items():                # 인덱스에서 빠진 기존 경매 보존
        result.setdefault(key, a)

    auctions = list(result.values())
    auctions.sort(key=lambda a: (a["year"], a["country"]))   # 오래된→최신
    return auctions


def to_metric(existing=None):
    """(metric_dict, auctions) 반환 — market_scrape.py 에서 호출."""
    auctions = scrape(existing)
    if not auctions:
        return None, None
    latest_year = max(a["year"] for a in auctions)
    latest = [a["medianBid"] for a in auctions if a["year"] == latest_year]
    value = statistics.median(latest) if latest else auctions[-1]["medianBid"]
    history = [a["medianBid"] for a in auctions]   # 경매별 중앙값(시간순) → 미니 스파크라인
    metric = {
        "value": f"{value:.1f}",
        "unit": "$/lb",
        "changePct": 0.0,
        "history": history,
    }
    return metric, auctions


def main():
    metric, auctions = to_metric()
    if not metric:
        print("COE 데이터 없음"); return
    payload = {"metrics": {}}
    if os.path.exists(DATA):
        try:
            payload = json.load(open(DATA, encoding="utf-8"))
        except Exception:
            pass
    payload.setdefault("metrics", {})["COE Auction"] = metric
    payload["coe_auctions"] = auctions
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    json.dump(payload, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"COE Auction: {metric['value']} $/lb · 경매 {len(auctions)}개")
    for a in auctions:
        print(f"  {a['label']:18} lots {len(a['lots']):3}  top ${a['topBid']:.1f}  median ${a['medianBid']:.1f}")
    print("저장:", DATA)


if __name__ == "__main__":
    main()
