"""어제 대비 변화 계산 — 직전 스냅샷(beans_prev.json)과 현재 beans.json 비교.

산출(beans.json["changes"]):
  - new       : 어제 없던 신규 상품(URL)
  - sold_out  : 어제 판매중 → 오늘 품절
  - price_down: 어제 대비 가격 하락

URL(판매처 상품) 단위로 비교 → 앱이 URL로 생두를 찾아 표시·딥링크.
크롤 파이프라인: (크롤 전) cp beans.json beans_prev.json → 크롤 → 재고 → make_changes.

사용: python3 make_changes.py
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "beans.json")
PREV = os.path.join(HERE, "data", "beans_prev.json")

CAP = 30   # 종류별 최대 표시 수


def _price(p):
    if not p:
        return None
    d = "".join(c for c in str(p) if c.isdigit())
    v = int(d) if d else 0
    return v if v > 0 else None


def _index(beans):
    return {b.get("url"): b for b in beans if b.get("url", "").startswith("http")}


def compute(cur_beans, prev_beans):
    cur, prev = _index(cur_beans), _index(prev_beans)
    new, sold_out, price_down = [], [], []
    for url, b in cur.items():
        old = prev.get(url)
        if old is None:
            new.append({"url": url, "type": "new"})
            continue
        # 어제 판매중(=품절 아님) → 오늘 품절
        if b.get("in_stock") is False and old.get("in_stock") is not False:
            sold_out.append({"url": url, "type": "sold_out"})
        # 가격 하락
        np, op = _price(b.get("price")), _price(old.get("price"))
        if np is not None and op is not None and np < op:
            price_down.append({"url": url, "type": "price_down", "old": op, "new": np})
    return (new[:CAP], sold_out[:CAP], price_down[:CAP])


def main():
    payload = json.load(open(DATA, encoding="utf-8"))
    if not os.path.exists(PREV):
        payload["changes"] = {"new": [], "sold_out": [], "price_down": []}
        json.dump(payload, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("이전 스냅샷 없음 — changes 비움(다음 크롤부터 채워짐)")
        return
    prev = json.load(open(PREV, encoding="utf-8"))
    new, sold_out, price_down = compute(payload["beans"], prev.get("beans", []))
    payload["changes"] = {"new": new, "sold_out": sold_out, "price_down": price_down}
    json.dump(payload, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"어제 대비 변화 — 신규 {len(new)} · 품절 {len(sold_out)} · 가격↓ {len(price_down)} → {DATA}")


if __name__ == "__main__":
    main()
