"""재고 수집 — data/beans.json 의 각 상품 URL 을 헤드리스로 확인해 in_stock 갱신.

품절 판정(stock_check)을 전체 카탈로그에 적용:
  in_stock = True(판매중) / False(품절) / None(확인 실패는 그대로 둠)
청크 단위로 진행하며 중간 저장(중단 대비). 다시 실행하면 처음부터 재확인.

사용 (의존성: pip install playwright ; playwright install chromium  또는 시스템 Chrome):
  python3 stock_run.py            # 전체
  python3 stock_run.py 60         # 앞 60개만(테스트)
이후: cp data/beans.json Burlap/Burlap/beans.json → 앱 재빌드(또는 원격 fetch)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "beans.json")
CHUNK = int(os.environ.get("STOCK_CHUNK", "40"))


def _save(payload):
    json.dump(payload, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def main():
    try:
        from stock_check import check_many
    except Exception as e:
        print("Playwright 미설치로 추정 — pip install playwright && playwright install chromium")
        print("  (", type(e).__name__, e, ")")
        return

    payload = json.load(open(DATA, encoding="utf-8"))
    beans = payload["beans"]
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else len(beans)

    # 확인 대상(중복 URL 1회) — http(s) URL 만
    by_url = {}
    for b in beans[:limit]:
        u = b.get("url", "")
        if u.startswith("http") and u not in by_url:
            by_url[u] = True
    urls = list(by_url.keys())
    print(f"재고 확인 시작: {len(urls)}개 URL (청크 {CHUNK})", flush=True)

    result = {}
    for i in range(0, len(urls), CHUNK):
        chunk = [(u, u) for u in urls[i:i + CHUNK]]
        res = check_many(chunk)
        result.update(res)
        # 부분 반영·저장
        for b in beans:
            v = result.get(b.get("url"))
            if v is True:
                b["in_stock"] = False
            elif v is False:
                b["in_stock"] = True
        _save(payload)
        done = min(i + CHUNK, len(urls))
        sold = sum(1 for v in result.values() if v is True)
        avail = sum(1 for v in result.values() if v is False)
        err = sum(1 for v in result.values() if v is None)
        print(f"  {done}/{len(urls)}  판매중 {avail} · 품절 {sold} · 실패 {err}", flush=True)

    payload["count"] = len(beans)
    _save(payload)
    sold = sum(1 for b in beans if b.get("in_stock") is False)
    avail = sum(1 for b in beans if b.get("in_stock") is True)
    print(f"\n재고 수집 완료: 판매중 {avail} · 품절 {sold} · 미확인 {len(beans) - sold - avail} → {DATA}")
    print("→ cp data/beans.json Burlap/Burlap/beans.json 후 앱 재빌드(또는 원격 fetch)")


if __name__ == "__main__":
    main()
