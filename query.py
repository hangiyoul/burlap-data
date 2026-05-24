"""필터/검색 — 수집·정규화된 GreenBean 위에서 자유 조합 필터링.

설계(로키 정리): '필터 크롤링' 대신 '데이터 내 필터링'.
넓게 1회 수집 → 표준 GreenBean 저장 → 여기서 즉시 조합 필터.
로스터 사용 패턴: 국가 + 가공 + (구체 컵노트 or 맛 카테고리) 조합.

운영 시엔 이 로직이 DB 쿼리(Supabase)로, 앱에선 필터 UI로 그대로 매핑됨.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flavor import matches_flavor, categories_of_notes  # noqa: E402


def _has(text, needle):
    return needle.lower() in (text or "").lower()


def filter_beans(beans,
                 country=None,        # 국가 (origin 부분일치)
                 region=None,         # 지역 부분일치
                 process=None,        # 가공 (Washed/Natural/Honey/Anaerobic...)
                 variety=None,        # 품종 부분일치
                 cup_note=None,       # 구체 컵노트 부분일치 (예: "blueberry")
                 flavor=None,         # 맛 카테고리 (예: "Floral", "Chocolate")
                 altitude_min=None,   # 고도 하한(m)
                 altitude_max=None,   # 고도 상한(m) — min~max 범위 필터
                 price_max=None,      # 최대 가격(숫자)
                 in_stock=None):      # True=판매중만
    """모든 조건 AND. None인 조건은 무시. return: 필터된 [GreenBean]."""
    out = []
    for b in beans:
        if country and not _has(b.origin, country):
            continue
        if region and not _has(b.region, region):
            continue
        if process and not _has(b.process, process):
            continue
        if variety and not _has(b.variety, variety):
            continue
        if cup_note and not any(_has(n, cup_note) for n in (b.cup_notes or [])):
            continue
        if flavor and not matches_flavor(b.cup_notes, flavor):
            continue
        lo, hi = _altitude_range(b.altitude)
        # 범위 겹침 판정: 커피 고도대 [lo,hi] 가 필터 [min,max] 와 겹치면 통과
        if altitude_min is not None and hi is not None and hi < altitude_min:
            continue
        if altitude_max is not None and lo is not None and lo > altitude_max:
            continue
        if price_max is not None and _price_num(b.price) is not None \
                and _price_num(b.price) > price_max:
            continue
        if in_stock is True and b.in_stock is False:
            continue
        out.append(b)
    return out


def _altitude_range(alt):
    """'1,900~2,200m' → (1900, 2200). 단일값 '2,000m' → (2000, 2000). 실패 시 (None, None)."""
    import re
    nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]{3,}", str(alt or ""))]
    if not nums:
        return (None, None)
    return (min(nums), max(nums))


def _price_num(price):
    import re
    m = re.search(r"[\d,]{3,}", str(price or ""))
    return int(m.group(0).replace(",", "")) if m else None


if __name__ == "__main__":
    # 데모: 실제 추출 데이터 일부(ayantu/micoffee/coffeelibre)로 필터 시연
    from schema import GreenBean
    sample = [
        GreenBean(vendor="ayantu", url="", raw_name="Gonzobe Samuel Natural",
                  origin="Ethiopia", region="Sidama, Bensa", altitude="2,500~2,600m",
                  variety="74158", process="Natural", price="38,000", in_stock=True,
                  cup_notes=["Blueberry", "Jam", "Lime", "Floral"]),
        GreenBean(vendor="micoffee", url="", raw_name="Agua Tibia Geisha",
                  origin="Colombia", region="Pinula", altitude="1,530m",
                  variety="Geisha", process="Washed", price="…", in_stock=True,
                  cup_notes=["Earl Grey", "Jasmine", "Green Grape", "Lemon Peel", "Apricot"]),
        GreenBean(vendor="micoffee", url="", raw_name="Pergamino Caturra Washed",
                  origin="Colombia", region="Inza, Cauca", altitude="1,700~1,900m",
                  variety="Caturra", process="Washed", in_stock=True,
                  cup_notes=["Orange", "Apple", "Hazelnut", "Milk Chocolate"]),
        GreenBean(vendor="coffeelibre", url="", raw_name="Palo Blanco",
                  origin="Guatemala", region="Pala, Cubulco", altitude="1,600m",
                  variety="Catimor", process="Washed", in_stock=True,
                  cup_notes=["Orange", "Apple", "Peach", "Maple Syrup", "Caramel", "Milk Chocolate"]),
    ]
    def show(label, res):
        print(f"\n[{label}] {len(res)}건")
        for b in res:
            print(f"   - {b.raw_name} ({b.origin}/{b.process}) {b.cup_notes}")
    show("국가=Colombia", filter_beans(sample, country="Colombia"))
    show("Washed + Floral 계열", filter_beans(sample, process="Washed", flavor="Floral"))
    show("Chocolate 계열", filter_beans(sample, flavor="Chocolate"))
    show("품종=Geisha", filter_beans(sample, variety="Geisha"))
    show("지역=Cauca", filter_beans(sample, region="Cauca"))
    show("고도 1,500~1,800m", filter_beans(sample, altitude_min=1500, altitude_max=1800))
    show("Ethiopia + 고도 2000m↑", filter_beans(sample, country="Ethiopia", altitude_min=2000))
    show("컵노트 'jasmine'", filter_beans(sample, cup_note="jasmine"))
