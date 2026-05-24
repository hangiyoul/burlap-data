"""Best of Panama(BOP) 경매 결과 → COE와 동일한 로트 스키마로 변환.

파나마는 COE에 참가하지 않고 자체 대회(Best of Panama)를 운영한다.
경매 플랫폼(mCultivo) API에서 이벤트별 로트(순위·농장·점수·낙찰가/lb·낙찰사·품종·가공·지역)를 가져온다.

  목록:  GET /auction/get-all-event-urls
  상세:  GET /auction/get-event-by-url/{slug}  → relatedProducts[]

출력(to_auctions): coe_scrape 와 동일한 dict 리스트 → market.json["coe_auctions"] 에 합쳐 적립.
최근 N개(기본 2개)의 '실제' 경매만 사용(테스트 이벤트 제외).
"""
import re
import json
import html as ht
import urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
API = "https://bestofpanama-api.mcultivo.com/api"
TEST_RE = re.compile(r"test|performance|copy|laura|m-?cultivo|demo", re.I)


def _get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": UA, "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore"))


def _clean_html(s):
    """구글독스 붙여넣기 HTML(<span>·<p>·inline style·&nbsp; 등) → 순수 텍스트."""
    if not s:
        return ""
    s = re.sub(r"(?i)<\s*(br|/p|/div|/li|/tr|/h[1-6])\s*/?>", " ", s)  # 블록 종료 → 공백
    s = re.sub(r"<[^>]+>", "", s)                                       # 남은 태그 제거
    s = ht.unescape(s).replace("\xa0", " ")                            # 엔티티·nbsp 정리
    return re.sub(r"\s+", " ", s).strip()


def _num(v):
    if v is None:
        return None
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v)) or "nan")
    except ValueError:
        return None


def _year(iso):
    try:
        return int(iso[:4])
    except (TypeError, ValueError):
        return None


def _real_events():
    """테스트 이벤트 제외 → [(start_date, name, url)] 최신순."""
    out = []
    for e in _get("/auction/get-all-event-urls"):
        name = e.get("name", "")
        url = e.get("event_url", "")
        if not url or TEST_RE.search(name) or TEST_RE.search(url):
            continue
        out.append((name, url))
    return out


def _details(pid):
    """로트 상세(컵노트·스토리) — product-details/{id}. 실패 시 빈 값."""
    try:
        d = _get(f"/auction/product-details/{pid}")
    except Exception:
        return "", ""
    spec = d.get("product_specifications") or {}
    notes = _clean_html(spec.get("Cupping Notes", ""))
    story = _clean_html(spec.get("Coffee Story", "")) or _clean_html(d.get("long_description", ""))
    return notes, story


def _event_signature(products):
    """이벤트 변화 감지용 서명 — 낙찰 로트 수·낙찰가 합·마감여부."""
    ws = [p for p in products if p.get("has_winner") and _num(p.get("final_price"))]
    n = len(ws)
    s = round(sum(_num(p["final_price"]) for p in ws)) if ws else 0
    closed = all(not p.get("is_active") for p in ws) if ws else False
    return f"{n}|{s}|{int(closed)}"


def _lots_from(products, prev_lots=None, with_details=True):
    """로트 변환. 변동 없는 로트는 기존 컵노트/스토리/번역을 재사용(상세 호출 절약)."""
    by_pid, by_key = {}, {}
    for l in (prev_lots or []):
        if l.get("_pid") is not None:
            by_pid[l["_pid"]] = l
        by_key[(l.get("rank"), l.get("farm"))] = l
    lots = []
    for p in products:
        spec = p.get("product_specifications") or {}
        bid = _num(p.get("final_price"))
        if not bid or bid <= 0 or not p.get("has_winner"):
            continue
        rank = str(spec.get("Rank", "")).strip()
        farm = (p.get("name") or "").strip()
        pid = p.get("id")
        prev = by_pid.get(pid) or by_key.get((rank, farm))
        reuse = (prev and abs((prev.get("bid") or -1) - round(bid, 2)) < 0.01
                 and (prev.get("cupNotes") or prev.get("story")))
        storyko = None
        if reuse:                                       # 변동 없음 → 재사용(상세 호출 X)
            notes, story = prev.get("cupNotes", ""), prev.get("story", "")
            storyko = prev.get("storyKo")
        elif with_details and pid:
            notes, story = _details(pid)
        else:
            notes, story = "", ""
        lot = {
            "rank":     rank,
            "farm":     farm,
            "score":    _num(spec.get("Score")),
            "bid":      round(bid, 2),
            "weightLb": _num(spec.get("Weight") or p.get("weight")),
            "total":    _num(p.get("final_total_price")),
            "company":  (p.get("winner_name") or "").strip(),
            "variety":  str(spec.get("Variety", "")).strip(),
            "process":  str(spec.get("Process", "")).strip(),
            "region":   str(spec.get("Region", "")).strip(),
            "farmer":   "",
            "cupNotes": notes,
            "story":    story,
            "_pid":     pid,
        }
        if storyko:
            lot["storyKo"] = storyko
        lots.append(lot)
    lots.sort(key=lambda x: x["bid"], reverse=True)
    return lots


def to_auctions(existing=None, limit=2):
    """최근 limit개 BOP 경매 → COE 스키마 dict 리스트. existing=기존 BOP 경매(재사용/보존).

    안전장치: ①인덱스 실패→전체 보존  ②이벤트 서명 동일→상세 호출 없이 재사용
              ③회귀(로트 감소)→기존 유지  ④목록에서 빠진 기존 연도 보존
    """
    existing = existing or []
    ex_map = {a.get("year"): a for a in existing if a.get("country") == "panama"}
    try:
        events = _real_events()
    except Exception as e:
        print("BOP 인덱스 조회 실패 → 기존 데이터 유지:", type(e).__name__, e)
        return list(existing)

    built = []   # (start_date, auction)
    for name, url in events:
        try:
            ev = _get(f"/auction/get-event-by-url/{url}")
        except Exception as e:
            print(f"  BOP {url} 조회 실패:", type(e).__name__, e)
            continue
        if ev.get("is_practice"):
            continue
        products = ev.get("relatedProducts") or []
        start = ev.get("event_start_date") or ""
        year = _year(start) or 0
        sig = _event_signature(products)
        prev = ex_map.get(year)
        if prev and prev.get("_sig") == sig and len(prev.get("lots", [])) >= 5:
            built.append((start, prev))           # 변화 없음 → 상세 호출 없이 재사용
            continue
        lots = _lots_from(products, prev_lots=(prev or {}).get("lots"))
        if len(lots) < 5:
            if prev:
                built.append((start, prev))        # 파싱 빈약 → 기존 유지
            continue
        if prev and len(lots) < len(prev.get("lots", [])):
            built.append((start, prev))            # 회귀 방지
            continue
        bids = sorted(l["bid"] for l in lots)
        built.append((start, {
            "country": "panama", "year": year,
            "label": f"Best of Panama {year}" if year else f"Best of Panama · {name}",
            "topBid": round(max(bids), 2),
            "medianBid": round(bids[len(bids) // 2], 2),
            "lots": lots,
            "_sig": sig,
        }))

    built.sort(key=lambda x: x[0], reverse=True)              # 최신순
    chosen = [a for _, a in built[:limit]]
    have = {a["year"] for a in chosen}
    for y, a in ex_map.items():                               # 목록에서 빠진 기존 연도 보존
        if y not in have:
            chosen.append(a)
    chosen.sort(key=lambda a: a["year"])                      # 오래된→최신
    return chosen


def main():
    auctions = to_auctions()
    if not auctions:
        print("BOP 데이터 없음"); return
    for a in auctions:
        print(f"  {a['label']:22} lots {len(a['lots']):3}  top ${a['topBid']:,.0f}  median ${a['medianBid']:,.0f}")
        top = a["lots"][0]
        print(f"     1위: {top['farm'][:36]:36} {top['score']}점  ${top['bid']:,.0f}/lb  {top['company']}")


if __name__ == "__main__":
    main()
