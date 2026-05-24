"""컵노트 → 맛 카테고리 매핑 (SCA 향미 휠 기반, 간이판).

목적: "floral 계열 커피", "chocolate 계열" 처럼 카테고리 필터를 가능하게.
구체 노트(Jasmine, Blueberry...)를 카테고리(Floral, Berry...)로 분류.
한 노트가 여러 카테고리에 속할 수 있음(bergamot = Floral + Citrus).

운영 시엔 LLM이 더 정교하게 태깅 가능. 여기는 의존성 0 키워드 맵.
"""

# 카테고리 → 키워드(부분일치, 한/영)
FLAVOR_CATEGORIES = {
    "Floral":    ["floral", "플로럴", "꽃", "jasmine", "자스민", "재스민", "rose", "장미",
                  "lavender", "라벤더", "bergamot", "베르가못", "hibiscus", "히비스커스",
                  "chamomile", "캐모마일", "elderflower", "lily", "릴리", "blossom"],
    "Berry":     ["berry", "베리", "blueberry", "블루베리", "strawberry", "딸기",
                  "raspberry", "라즈베리", "blackberry", "블랙베리", "cranberry", "크랜베리",
                  "currant", "커런트", "boysenberry"],
    "Citrus":    ["citrus", "시트러스", "lemon", "레몬", "lime", "라임", "orange", "오렌지",
                  "grapefruit", "자몽", "mandarin", "귤", "tangerine", "yuzu", "유자",
                  "bergamot", "베르가못", "lemongrass", "레몬그라스"],
    "StoneFruit": ["peach", "복숭아", "백도", "황도", "apricot", "살구", "plum", "자두",
                   "nectarine", "천도복숭아", "cherry", "체리"],
    "Tropical":  ["tropical", "열대", "mango", "망고", "pineapple", "파인애플", "passion",
                  "패션", "lychee", "리치", "papaya", "파파야", "melon", "멜론",
                  "watermelon", "수박", "guava", "구아바", "muscat", "머스캣", "shine muscat"],
    "OtherFruit": ["apple", "사과", "grape", "포도", "pear", "배", "fig", "무화과",
                   "raisin", "건포도", "lulo", "룰로", "starfruit", "스타프룻"],
    "Chocolate": ["chocolate", "초콜릿", "초콜렛", "cocoa", "코코아", "cacao", "카카오",
                  "mocha", "모카"],
    "Nutty":     ["nut", "넛", "견과", "almond", "아몬드", "hazelnut", "헤이즐넛",
                  "walnut", "호두", "peanut", "땅콩", "pecan", "피칸", "cashew", "캐슈"],
    "Sweet":     ["caramel", "캐러멜", "honey", "꿀", "maple", "메이플", "brown sugar",
                  "흑설탕", "갈색 설탕", "molasses", "당밀", "vanilla", "바닐라",
                  "toffee", "토피", "sugarcane", "사탕수수", "cane sugar", "케인슈가",
                  "marshmallow", "마시멜로", "수정과"],
    "Spice":     ["spice", "스파이스", "스파이시", "cinnamon", "시나몬", "clove", "정향",
                  "nutmeg", "넛맥", "herb", "허브", "rosemary", "로즈마리"],
    "Tea":       ["tea", "티", "홍차", "녹차", "earl grey", "얼그레이", "rooibos", "루이보스",
                  "black tea", "green tea"],
    "WineFerment": ["wine", "와인", "winey", "와이니", "cognac", "꼬냑", "whiskey", "위스키",
                    "fermented", "발효", "boozy", "champagne", "샴페인", "사이다", "cider",
                    "애플사이다", "감식초"],
    "Roasted":   ["roasted", "로스티드", "볶은", "구운", "toasted", "malt", "몰트", "맥아",
                  "grain", "곡물", "cereal", "시리얼", "biscuit", "비스킷", "누룽지", "군고구마", "고구마"],
}


def categories_of(note):
    """단일 노트 → 속하는 카테고리 집합."""
    low = str(note).lower()
    out = set()
    for cat, kws in FLAVOR_CATEGORIES.items():
        if any(k.lower() in low for k in kws):
            out.add(cat)
    return out


def categories_of_notes(notes):
    """컵노트 리스트 → 전체 카테고리 집합."""
    out = set()
    for n in notes or []:
        out |= categories_of(n)
    return out


def matches_flavor(notes, category):
    """컵노트가 특정 카테고리에 해당하는가."""
    return category in categories_of_notes(notes)


if __name__ == "__main__":
    samples = [["Blueberry", "Jam", "Lime", "Floral"],
               ["Earl Grey", "Jasmine", "Green Grape", "Lemon Peel"],
               ["Orange", "Apple", "Hazelnut", "Milk Chocolate"]]
    for s in samples:
        print(f"{s}\n  → {sorted(categories_of_notes(s))}")
