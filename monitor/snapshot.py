"""모니터 — 사이트 개편/차단 감지 (스냅샷 비교).

운영 핵심비용은 '사이트 구조 변경 시 어댑터 깨짐'(FINDINGS §5,8).
업체별 수집 건수를 baseline 과 비교 → 급감(예: 평소 20종 → 0종)이면 경보.
깨지면 그 platform 어댑터 하나만 고치면 같은 플랫폼 전부 복구.

사용:
  python3 monitor/snapshot.py save     # 현재 수집수를 baseline 으로 저장
  python3 monitor/snapshot.py check    # baseline 대비 점검(급감 경보)
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import run

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline.json")
DROP_RATIO = 0.5   # 평소의 50% 미만이면 경보


def _counts(origin="ethiopia"):
    _, per_vendor = run(origin)
    return {k: v for k, v in per_vendor.items() if isinstance(v, int)}


def save(origin="ethiopia"):
    counts = _counts(origin)
    with open(BASELINE, "w", encoding="utf-8") as f:
        json.dump({"origin": origin, "counts": counts}, f, ensure_ascii=False, indent=2)
    print("baseline 저장:", counts)


def check(origin="ethiopia"):
    if not os.path.exists(BASELINE):
        print("baseline 없음 → 먼저 'save'"); return
    base = json.load(open(BASELINE, encoding="utf-8"))["counts"]
    now = _counts(origin)
    alerts = []
    for v, b in base.items():
        n = now.get(v, 0)
        if b > 0 and n < b * DROP_RATIO:
            alerts.append(f"⚠️ {v}: {b} → {n} (급감, 어댑터 점검)")
    print("현재:", now)
    if alerts:
        print("\n".join(alerts))
    else:
        print("✅ 이상 없음")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    (save if cmd == "save" else check)()
