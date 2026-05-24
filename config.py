"""vendors.json 로더 + 헬퍼.

업체 = 설정. 코드는 platform 만 보고 동작.
"""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "vendors.json")


def load_vendors():
    with open(_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["vendors"]


def active_vendors():
    """정적 어댑터로 수집 가능한 업체만."""
    return {k: v for k, v in load_vendors().items() if v.get("status") == "active"}


def vendors_by_platform(platform):
    return {k: v for k, v in load_vendors().items() if v.get("platform") == platform}


if __name__ == "__main__":
    vs = load_vendors()
    print(f"등록 업체 {len(vs)}개")
    for k, v in vs.items():
        print(f"  {k:14} {v['platform']:11} {v.get('status')}")
