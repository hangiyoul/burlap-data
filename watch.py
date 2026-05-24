"""워치리스트 + 재입고 알림 코어.

유저가 찜한 커피를 지정 슬롯(≤3회/일)에 타겟 재고체크 → '품절→판매중' 전환 감지 → 알림 이벤트.
- 전체 크롤링이 아니라 '워치한 항목만' 체크 → 가볍고 점잖음(차단위험↓).
- 재고 정확도(stock_check 검증)가 곧 알림 정확도.

여기는 '재고체크 + 상태 diff' 코어(테스트 가능).
유저별 저장(Supabase)·푸시(APNs)·스케줄(슬롯)은 백엔드 단계 — 자리만 표시.
"""
from dataclasses import dataclass, field
from typing import Optional, Callable, List

# 플랫폼별 재고 확인 방식 (FINDINGS §4 참조)
HEADLESS_PLATFORMS = {"cafe24", "imweb"}      # 렌더 후 보이는 버튼/배지로 판정
STATIC_PLATFORMS = {"godo", "youngcart", "cobeans"}  # 상세 HTML 품절 신호


@dataclass
class WatchItem:
    user_id: str
    vendor: str
    platform: str
    url: str
    name: str
    last_in_stock: Optional[bool] = None   # 직전 관측 재고 (None=미관측)


@dataclass
class AlertEvent:
    kind: str                 # "restock" | "price_drop" | "new_lot"
    item: WatchItem
    message: str
    deeplink: str             # 바로 구매 (GreenBean.url)


def current_stock(url, platform):
    """단일 상품의 현재 재고(True/False/None). 플랫폼별 dispatch.
    headless(cafe24·imweb)는 Playwright, static은 HTML 품절신호."""
    if platform in HEADLESS_PLATFORMS:
        from stock_check import check_many
        res = check_many([(url, url)])
        sold = res.get(url)
        return None if sold is None else (not sold)
    if platform in STATIC_PLATFORMS:
        from common import get
        try:
            h = get(url)
        except Exception:
            return None
        head = h.split("상세정보")[0] if "상세정보" in h else h[:6000]
        sold = ("품절" in head) or ('class="soldout' in h.lower()) or ("sold out" in head.lower())
        return not sold
    # partner(feed): 재고는 시트 in_stock 필드 → 워치는 피드 동기화 시 처리
    return None


def check_watchlist(items: List[WatchItem], stock_fn: Callable = current_stock) -> List[AlertEvent]:
    """워치 항목들 재고 확인 → 품절→판매중 전환 시 알림 이벤트 생성.
    items의 last_in_stock 을 현재값으로 갱신(다음 비교용).
    stock_fn 주입 가능(테스트용)."""
    alerts = []
    for it in items:
        now = stock_fn(it.url, it.platform)
        if now is None:
            continue
        # 전환 감지: 직전 품절(False) → 현재 판매중(True)
        if it.last_in_stock is False and now is True:
            alerts.append(AlertEvent(
                kind="restock", item=it, deeplink=it.url,
                message=f"🎉 기다리던 '{it.name}' 지금 살 수 있어요!"))
        it.last_in_stock = now   # 상태 갱신
    return alerts


# --- 백엔드 단계 자리 (지금은 인터페이스만) ---
def send_push(alert: AlertEvent):
    """iOS APNs 푸시 발송 지점. 예쁜 UI 카드 + 바로가기 버튼.
    개발 시 백엔드에서 구현."""
    raise NotImplementedError("APNs 푸시 연결 필요 (백엔드)")


if __name__ == "__main__":
    # 데모: 네트워크 없이 diff 로직 검증 (가짜 stock_fn)
    items = [
        WatchItem("u1", "ayantu", "imweb", "https://ayantu.co.kr/?idx=359",
                  "Tadese Nensebo Natural", last_in_stock=False),   # 직전 품절
        WatchItem("u1", "momos", "cafe24", "https://momos.co.kr/.../2721/",
                  "Ethiopia Duwancho Natural G1", last_in_stock=False),  # 직전 품절
        WatchItem("u1", "micoffee", "godo", "https://www.micoffee.co.kr/...",
                  "Colombia El Nogal Caturra Washed", last_in_stock=True),  # 직전 판매중
    ]
    # 가짜: 1번은 재입고됨(True), 2번 여전히 품절(False), 3번 여전히 판매중(True)
    fake = {items[0].url: True, items[1].url: False, items[2].url: True}
    alerts = check_watchlist(items, stock_fn=lambda url, plat: fake.get(url))
    print(f"알림 {len(alerts)}건 (품절→판매중 전환만):")
    for a in alerts:
        print(f"  [{a.kind}] {a.message}\n     → {a.deeplink}")
    print("\n상태 갱신 확인:")
    for it in items:
        print(f"  {it.name[:34]:34} last_in_stock={it.last_in_stock}")
