"""실제 크롤 실행 진입점 (스케줄/수동 공용).

전 산지 × active 업체(정적) 카탈로그를 수집 → 표준 GreenBean → data/beans.json 저장.
※ 재고/스펙/컵노트(헤드리스·OCR·LLM) enrich 는 후속 단계. 현재는 카탈로그(정적) 기준.

사용: python3 crawl_run.py            # 전 산지
      python3 crawl_run.py ethiopia   # 특정 산지만
"""
import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import run

ORIGINS = ["ethiopia", "colombia", "kenya", "guatemala", "panama", "brazil"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "beans.json")


def crawl(origins):
    all_beans, summary = [], {}
    for o in origins:
        beans, per_vendor = run(o)
        all_beans.extend(beans)
        summary[o] = {"total": len(beans), "per_vendor": per_vendor}
        print(f"[{o}] {len(beans)}종  {per_vendor}")

    # (vendor, url) 중복 제거
    seen, deduped = set(), []
    for b in all_beans:
        key = (b.vendor, b.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(b)
    return deduped, summary


# 이전 크롤에서 보존할 보강(enrich) 필드 — 새 크롤은 이름·가격·재고만 신선, 나머진 이어받음
_ENRICH_FIELDS = ("region", "farm", "producer", "altitude", "variety", "process", "grade", "cup_notes")


def _load_prev_beans():
    """직전 beans.json 의 beans 리스트 (없으면 빈 리스트)."""
    if os.path.exists(OUT):
        try:
            return json.load(open(OUT, encoding="utf-8")).get("beans", [])
        except Exception:
            return []
    return []


# 한 판매처가 이전에 이만큼 이상 있었는데 이번에 0건이면 '증발'로 간주(차단/일시장애)
_VANISH_MIN = 5


def _preserve_vanished_vendors(bean_dicts, prev_beans):
    """이전엔 다수 있었으나 이번 크롤에서 0건이 된 판매처 → 직전 데이터 그대로 유지.

    royalcoffee 처럼 특정 IP(예: GitHub 데이터센터)를 차단하는 사이트가
    클라우드에서만 0건이 되어 판매처가 통째로 사라지는 것을 방지.
    """
    import collections
    new_count = collections.Counter(d.get("vendor") for d in bean_dicts)
    prev_by_vendor = collections.defaultdict(list)
    for ob in prev_beans:
        prev_by_vendor[ob.get("vendor")].append(ob)
    for vendor, prevs in prev_by_vendor.items():
        if len(prevs) >= _VANISH_MIN and new_count.get(vendor, 0) == 0:
            print(f"⚠️  {vendor}: 이번 0건(이전 {len(prevs)}건) → 직전 데이터 유지(차단/장애 추정)")
            bean_dicts.extend(prevs)
    return bean_dicts


def _merge_prev(bean_dicts, prev_beans, today):
    """이전 beans.json 과 (vendor,url) 매칭 → 보강 필드·입고일(first_seen) 보존."""
    prev = {(ob.get("vendor"), ob.get("url")): ob for ob in prev_beans}
    for d in bean_dicts:
        old = prev.get((d.get("vendor"), d.get("url")))
        if old:
            for f in _ENRICH_FIELDS:               # 빈 칸만 이전 값으로 채움(enrich 결과 보존)
                if not d.get(f) and old.get(f):
                    d[f] = old[f]
            if not d.get("price") and old.get("price"):
                d["price"] = old["price"]
            d["added_at"] = old.get("added_at") or today
        else:
            d["added_at"] = today                  # 처음 발견 → 오늘(first_seen)
    return bean_dicts


def main():
    origins = sys.argv[1:] or ORIGINS
    beans, summary = crawl(origins)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prev_beans = _load_prev_beans()
    bean_dicts = _merge_prev([b.to_dict() for b in beans], prev_beans, today)
    bean_dicts = _preserve_vanished_vendors(bean_dicts, prev_beans)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(bean_dicts),
        "origins": origins,
        "summary": summary,
        "beans": bean_dicts,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {OUT}  ({len(bean_dicts)}종)")


if __name__ == "__main__":
    main()
