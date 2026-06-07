"""한국어/영어 raw_name → 구조화 필드(region/variety/process/grade) 정규식 추출.

enrich.py 의 Gemini 호출 전 단계 — LLM 없이 즉시 잡을 수 있는 것은 사전에 채움.
효과: Vision OCR 호출 빈도 ↓ (variety 미충족 시 이미지 비전 콜 발동) → 무료 한도 더 오래 버팀.
또한 LLM 키 없이도 단독 실행으로 데이터 일부 즉시 채울 수 있음.

사용 (단독 실행):
    python3 name_parser.py              # data/beans.json 빈 칸 정규식 채움
    python3 name_parser.py --dry-run    # 변경 보고만, 저장 안 함

import 해서 단일 호출:
    from name_parser import extract_from_name
    out = extract_from_name("콜롬비아 우일라 엘 미라도르 핑크 부르봉 허니", origin="Colombia")
    # → {"region": "Huila", "variety": "Pink Bourbon", "process": "Honey"}
"""
import json
import os
import re
import sys

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "beans.json")

# ─────────────────────────────────────────────────────────────────
# 사전 — 한국어 ↔ 영문 정규명.
# 키는 매칭용 (대소문자 무시), 값은 표준 영문 표기.
# 우선순위 = 길이 내림차순으로 매칭 (e.g., "핑크 부르봉" 이 "부르봉" 보다 먼저).
# ─────────────────────────────────────────────────────────────────

PROCESS = {
    # Honey 계열 — 다양한 표기
    "코퍼먼티드": "Co-fermented", "co-fermented": "Co-fermented", "co fermented": "Co-fermented",
    "카보닉 메서레이션": "Anaerobic", "carbonic maceration": "Anaerobic",
    "무산소": "Anaerobic", "anaerobic": "Anaerobic", "thermal shock": "Thermal Shock",
    "더블 패스트": "Double Pass", "double pass": "Double Pass",
    "세미 워시드": "Semi-washed", "semi washed": "Semi-washed", "semi-washed": "Semi-washed",
    "펄프드 내추럴": "Pulped Natural", "pulped natural": "Pulped Natural",
    "펄프드 워시드": "Pulped Washed", "pulped washed": "Pulped Washed",
    "워시드 ea": "EA Decaf", "ea 디카페인": "EA Decaf", "ea decaf": "EA Decaf",
    "슈가케인 디카페인": "Sugarcane Decaf", "slugar cane": "Sugarcane Decaf",
    "스위스 워터": "Swiss Water", "swiss water": "Swiss Water",
    "디카페인": "Decaf", "decaf": "Decaf",
    "내추럴": "Natural", "natural": "Natural", "건식": "Natural",
    "워시드": "Washed", "washed": "Washed", "수세": "Washed",
    "허니": "Honey", "honey": "Honey",
}

VARIETY = {
    "핑크 부르봉": "Pink Bourbon", "pink bourbon": "Pink Bourbon",
    "옐로우 부르봉": "Yellow Bourbon", "yellow bourbon": "Yellow Bourbon",
    "레드 부르봉": "Red Bourbon", "red bourbon": "Red Bourbon",
    "비야 사르치": "Villa Sarchi", "villa sarchi": "Villa Sarchi",
    "카투라 치로소": "Caturra Chiroso", "caturra chiroso": "Caturra Chiroso",
    "치로소": "Chiroso", "chiroso": "Chiroso",
    "파카마라": "Pacamara", "pacamara": "Pacamara",
    "마라고지페": "Maragogype", "maragogype": "Maragogype",
    "에티오피아 헤어룸": "Heirloom", "heirloom": "Heirloom", "헤어룸": "Heirloom",
    "게이샤": "Geisha", "geisha": "Geisha", "게샤": "Geisha", "gesha": "Geisha",
    "타이피카": "Typica", "typica": "Typica",
    "카투라": "Caturra", "caturra": "Caturra",
    "카투아이": "Catuai", "catuai": "Catuai",
    "카티모르": "Catimor", "catimor": "Catimor",
    "부르봉": "Bourbon", "bourbon": "Bourbon",
    "sl28": "SL28", "sl-28": "SL28",
    "sl34": "SL34", "sl-34": "SL34",
    "ruiru 11": "Ruiru 11", "루이루 11": "Ruiru 11",
    "batian": "Batian", "바티안": "Batian",
    "74158": "74158", "74112": "74112",
    "wush wush": "Wush Wush", "워쉬워쉬": "Wush Wush",
    "moka": "Mocha", "모카": "Mocha",
    "마일드": "Mild",
}

# 산지별 region 사전 (origin 코드 기준).
# 한국 vendor 들이 흔히 쓰는 한글 표기 + 영문 표기 둘 다 매핑.
REGION_BY_ORIGIN = {
    "colombia": {
        "우일라": "Huila", "후일라": "Huila", "huila": "Huila",
        "나리뇨": "Nariño", "나리노": "Nariño", "narino": "Nariño", "nariño": "Nariño",
        "안티오키아": "Antioquia", "antioquia": "Antioquia",
        "카우카": "Cauca", "cauca": "Cauca",
        "톨리마": "Tolima", "tolima": "Tolima",
        "리사랄다": "Risaralda", "risaralda": "Risaralda",
        "칼다스": "Caldas", "caldas": "Caldas",
        "퀸디오": "Quindío", "quindio": "Quindío", "quindío": "Quindío",
        "보야카": "Boyacá", "boyaca": "Boyacá", "boyacá": "Boyacá",
        "산탄데르": "Santander", "santander": "Santander",
        "메델린": "Medellín", "medellin": "Medellín",
        "포파얀": "Popayán", "popayan": "Popayán",
        "피탈리토": "Pitalito", "pitalito": "Pitalito",
        "부에사코": "Buesaco", "buesaco": "Buesaco",
        "아폰테": "Aponte", "aponte": "Aponte",
        "옌탈": "Yacuanquer", "yacuanquer": "Yacuanquer",
    },
    "ethiopia": {
        "예가체프": "Yirgacheffe", "yirgacheffe": "Yirgacheffe",
        "시다모": "Sidamo", "sidamo": "Sidamo", "시다마": "Sidama",
        "코체레": "Kochere", "kochere": "Kochere",
        "구지": "Guji", "guji": "Guji",
        "아리차": "Aricha", "aricha": "Aricha",
        "함벨라": "Hambela", "hambela": "Hambela",
        "리무": "Limu", "limu": "Limu",
        "하라": "Harrar", "harrar": "Harrar", "harar": "Harrar",
        "벤사": "Bensa", "bensa": "Bensa",
        "넨세보": "Nensebo", "nensebo": "Nensebo",
        "워카": "Worka", "worka": "Worka",
        "게뎁": "Gedeb", "gedeb": "Gedeb",
        "아다도": "Adado", "adado": "Adado",
        "우라가": "Uraga", "uraga": "Uraga",
        "고티티": "Gotiti", "gotiti": "Gotiti",
        "반코": "Banko", "banko": "Banko",
        "코체": "Koche", "koche": "Koche",
        "보나": "Bona", "bona": "Bona",
    },
    "kenya": {
        "니에리": "Nyeri", "nyeri": "Nyeri",
        "키암부": "Kiambu", "kiambu": "Kiambu",
        "엠부": "Embu", "embu": "Embu",
        "무랑가": "Murang'a", "muranga": "Murang'a", "murang'a": "Murang'a",
        "키리냐가": "Kirinyaga", "kirinyaga": "Kirinyaga",
    },
    "brazil": {
        "세하도": "Cerrado", "cerrado": "Cerrado",
        "모지아나": "Mogiana", "mogiana": "Mogiana",
        "술 데 미나스": "Sul de Minas", "sul de minas": "Sul de Minas",
        "바이아": "Bahia", "bahia": "Bahia",
        "미나스 제라이스": "Minas Gerais", "minas gerais": "Minas Gerais",
        "에스피리투 산투": "Espírito Santo", "espirito santo": "Espírito Santo",
    },
    "guatemala": {
        "안티구아": "Antigua", "antigua": "Antigua",
        "후에후에테낭고": "Huehuetenango", "huehuetenango": "Huehuetenango",
        "코반": "Cobán", "coban": "Cobán",
        "아티틀란": "Atitlán", "atitlan": "Atitlán",
        "아카테낭고": "Acatenango", "acatenango": "Acatenango",
        "산 마르코스": "San Marcos", "san marcos": "San Marcos",
        "프라이하네스": "Fraijanes", "fraijanes": "Fraijanes",
    },
    "panama": {
        "보케테": "Boquete", "boquete": "Boquete",
        "볼칸": "Volcán", "volcan": "Volcán",
        "치리키": "Chiriqui", "chiriqui": "Chiriqui",
    },
    "costa_rica": {
        "타라수": "Tarrazú", "tarrazu": "Tarrazú",
        "오로시": "Orosi", "orosi": "Orosi",
        "트레스 리오스": "Tres Ríos", "tres rios": "Tres Ríos",
    },
}

# 등급 (Grade) — 콜롬비아 Supremo, 에티오피아 G1~G5 등.
GRADE = {
    "수프리모": "Supremo", "supremo": "Supremo",
    "엑셀소": "Excelso", "excelso": "Excelso",
    "shb": "SHB", "scr": "SCR", "ehb": "EHB", "ehp": "EHP",
    "aa faq": "AA FAQ", "aa": "AA", "ab": "AB",
    "g1": "G1", "g2": "G2", "g3": "G3", "g4": "G4",
    "ny2/3": "NY 2/3", "ny2": "NY 2", "sc14/16": "Screen 14/16",
}


def _norm(s):
    """소문자 + 다중 공백 정리."""
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _match_dict(text_norm, mapping):
    """매핑에서 텍스트에 포함된 첫 키 찾기 (길이 내림차순 우선)."""
    # 매번 정렬은 비싸므로 모듈 로드 시 한 번만 정렬하는 게 이상적이지만,
    # 데이터 크기가 작아 직접 정렬.
    for key in sorted(mapping.keys(), key=lambda k: -len(k)):
        # 단어 경계 — 영문은 word boundary, 한국어는 그대로 contains
        if any("a" <= c <= "z" or c.isdigit() for c in key):
            if re.search(r"\b" + re.escape(key) + r"\b", text_norm, re.I):
                return mapping[key]
        else:
            if key in text_norm:
                return mapping[key]
    return None


# ─────────────────────────────────────────────────────────────────
# 표시용 영문 이름 (display_name) — raw_name 의 한글 토큰을 영문으로 치환.
# 예) "25 과테말라 SHB EP 워시드" → "Guatemala SHB EP Washed"
#     "[6월 추천생두] 콜롬비아 아폰테 카투라 허니" → "Colombia Aponte Caturra Honey"
# ─────────────────────────────────────────────────────────────────

# 자주 등장하는 단일 토큰 — 농장명, 흔한 재료어, 마케팅 (실데이터 빈도순)
EXTRA_TOKENS = {
    # 흔한 가공·재료어
    "슈가케인": "Sugarcane",
    "체리": "Cherry",
    "스트로베리": "Strawberry",
    "피치": "Peach",
    "리치": "Lychee",
    "워터멜론": "Watermelon",
    "벨벳": "Velvet",
    "자바": "Java",
    "아히": "Aji",
    "피베리": "Peaberry",
    "아나에어로빅": "Anaerobic",
    "마운틴워터": "Mountain Water",
    "버번": "Bourbon",
    "디카페인": "Decaf",
    "생두": "",            # 토큰 제거 (= green bean, redundant)
    # 농장명 (자주 등장)
    "페르가미노": "Pergamino",
    "아폰테": "Aponte",
    "타블론": "Tablón",
    "고메즈": "Gómez",
    "부에사코": "Buesaco",
    "야쿠앙케르": "Yacuanquer",
    "콘사카": "Consacá",
    "팜본도": "Pamplona",
    "산타펠리사": "Santa Felisa",
    "옴블리곤": "Ombligón",
    "키야라": "Kiyara",
    "오로라": "Aurora",
    "풀리": "Puli",
    "봄베": "Bombe",
    "첼첼레": "Chelchele",
    "모틸론": "Motilón",
    "샤키소": "Shakiso",
    "시드라": "Sidra",
    "에이미": "Aimee",
    "곤조베": "Gonzobe",
    "와다리": "Wadari",
    "아디수": "Addisu",
    "키다네": "Kidane",
    "두바": "Duba",
    "보체사": "Bochesa",
    "아르베고나": "Arbegona",
    "파노라마": "Panorama",
    "메디나": "Medina",
    "겔레나": "Gelena",
    "아바야": "Abaya",
    "물루게타": "Mulugeta",
    "문타샤": "Muntasha",
    "바샤베켈레": "Bashabekele",
    "비타": "Vita",
    "카파": "Kaffa",
    "리브레": "Libre",
    "셀렉션": "Selection",
    "컬렉션": "Collection",
    "할로": "Halo",
    "베리티": "Bariti",
    "가타": "Gata",
    "코빈즈": "Cobeans",
    "마르": "Mar",
    # 잔존 빈도 높은 농장·품종·표기 (2차)
    "옐로우": "Yellow",
    "블루제이드": "Blue Jade",
    "하트만": "Hartmann",
    "다테하": "Datterra",
    "캐러멜": "Caramel",
    "사워솝": "Soursop",
    "블루베리": "Blueberry",
    "코코넛": "Coconut",
    "아이리시": "Irish",
    "구지": "Guji",
    "시다마": "Sidama",
    "케라모": "Keramo",
    "솔로모": "Solomo",
    "고구구": "Gogugu",
    "고로": "Goro",
    "무다": "Muda",
    "루무": "Rumudamo",
    "코케": "Koke",
    "첼바": "Chelba",
    "문타사": "Muntasha",
    "우라가": "Uraga",
    "벤사": "Bensa",
    "조히": "Johi",
    "할인": "",
    "코퍼먼티드": "Co-fermented",
    # 핀카 = Finca (스페인어 농장), 파젠다 = Fazenda (포르투갈어 농장)
    "핀카": "Finca",
    "파젠다": "Fazenda",
    "엄": "Em",
    "레리다": "Lérida",
    "엘": "El",           # 단일 토큰 그대로
    # 마케팅·시즈널 — 제거
    "추천생두": "",
    "행사": "",
    "세일": "",
    "이벤트": "",
    "신상품": "",
    "한정수량": "",
    "프리미엄": "",
    "온라인전용": "",
    "신규": "",
    "라인업": "",
    "재입고": "",
    "런칭": "",
    # 산지 한글 1-회용
    "에티오피아": "Ethiopia",
    "콜롬비아": "Colombia",
}


# 국가 — 한글 → 영문 (raw_name 안에서 빈도 높음)
COUNTRY_KO = {
    "콜롬비아": "Colombia",
    "에티오피아": "Ethiopia",
    "케냐": "Kenya",
    "과테말라": "Guatemala",
    "파나마": "Panama",
    "브라질": "Brazil",
    "코스타리카": "Costa Rica",
    "엘살바도르": "El Salvador",
    "온두라스": "Honduras",
    "니카라과": "Nicaragua",
    "예멘": "Yemen",
    "탄자니아": "Tanzania",
    "르완다": "Rwanda",
    "부룬디": "Burundi",
    "인도": "India",
    "인도네시아": "Indonesia",
    "베트남": "Vietnam",
    "페루": "Peru",
    "볼리비아": "Bolivia",
    "에콰도르": "Ecuador",
    "도미니카": "Dominican Republic",
    "자메이카": "Jamaica",
    "쿠바": "Cuba",
    "멕시코": "Mexico",
}


def _multi_word_replace(text):
    """다중 단어 표현을 먼저 치환 (긴 표현 우선)."""
    multi = [
        ("핑크 부르봉", "Pink Bourbon"),
        ("핑크 버번", "Pink Bourbon"),
        ("옐로우 부르봉", "Yellow Bourbon"),
        ("옐로우 버번", "Yellow Bourbon"),
        ("레드 부르봉", "Red Bourbon"),
        ("레드 버번", "Red Bourbon"),
        ("세미 워시드", "Semi-washed"),
        ("펄프드 내추럴", "Pulped Natural"),
        ("펄프드 워시드", "Pulped Washed"),
        ("워시드 EA", "EA Washed"),
        ("EA 디카페인", "EA Decaf"),
        ("슈가케인 디카페인", "Sugarcane Decaf"),
        ("스위스 워터", "Swiss Water"),
        ("카보닉 메서레이션", "Anaerobic"),
        ("무산소 발효", "Anaerobic"),
        ("후에후에 테낭고", "Huehuetenango"),
        ("후에후에테낭고", "Huehuetenango"),
        ("산타 바바라", "Santa Bárbara"),
        ("산타 아나", "Santa Ana"),
        ("산 아구스틴", "San Agustín"),
        ("산 어거스틴", "San Agustín"),
        ("커피 지도 세트", ""),       # 비-생두
        ("커피 지도", ""),
        # 흔한 농장명·로트명 (다단어)
        ("엘 미라도르", "El Mirador"),
        ("라스 라하스", "Las Lajas"),
        ("라스 마가리타스", "Las Margaritas"),
        ("라 마리나", "La Marina"),
        ("라 테라사", "La Terraza"),
        ("라 플라타", "La Plata"),
        ("로스 파티오스", "Los Patios"),
        ("카페 로사리오", "Café Rosario"),
        ("엘 파라이소", "El Paraíso"),
        ("엘 디비소", "El Diviso"),
        ("엘 소코로", "El Socorro"),
        ("엘 오브라헤", "El Obraje"),
        ("핀카 마타레돈다", "Finca Mataredonda"),
        ("산토 도밍고", "Santo Domingo"),
        ("산 펠리페", "San Felipe"),
        ("란초 그란데", "Rancho Grande"),
        ("쟈딘즈", "Jardines"),  # momos 가 흔히 씀
        # 자주 등장하는 다중-단어 농장명
        ("핀카 메디나", "Finca Medina"),
        ("핀카 레리다", "Finca Lérida"),
        ("핀카 마타레돈다", "Finca Mataredonda"),
        ("아구아 티비아", "Agua Tibia"),
        ("라스 플로레스", "Las Flores"),
        ("리브레 셀렉션", "Libre Selection"),
        ("파젠다 엄", "Fazenda Em"),
        ("산타펠리사 레드", "Santa Felisa Red"),
        ("모틸론 스페셜티", "Motilón Specialty"),
        ("생두 바샤베켈레", "Bashabekele"),
        ("아디수 키다네", "Addisu Kidane"),
        ("겔레나 아바야", "Gelena Abaya"),
        ("물루게타문타샤", "Mulugeta Muntasha"),
        ("레드 카투카이", "Red Catucaí"),
        ("크라운쥬얼 카보닉", "Crown Jewel Carbonic"),
        ("에드윈 노레냐", "Edwin Noreña"),
        ("트리플 에이", "Triple A"),
        ("더블 에이", "Double A"),
    ]
    for ko, en in multi:
        text = text.replace(ko, en)
    return text


def _load_learned_tokens():
    """data/learned_tokens.json — Gemini 가 학습한 한글→영문 음역 사전."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "learned_tokens.json")
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    return {}


def _build_token_map():
    """단일 토큰 한글 → 영문 사전 (PROCESS/VARIETY/REGION/EXTRA/learned 통합)."""
    m = {}
    # 국가
    for ko, en in COUNTRY_KO.items():
        m[ko] = en
    # 가공/품종/등급
    for src in (PROCESS, VARIETY, GRADE):
        for ko, en in src.items():
            if not any("a" <= c <= "z" for c in ko):
                m[ko] = en
    # 모든 산지의 region 사전
    for origin, regions in REGION_BY_ORIGIN.items():
        for ko, en in regions.items():
            if not any("a" <= c <= "z" for c in ko):
                m[ko] = en
    # 추가 토큰 (수동 사전)
    for ko, en in EXTRA_TOKENS.items():
        m[ko] = en
    # 학습 사전 (Gemini 누적 결과 — 자동 + 영구)
    # 수동 사전이 우선이므로 learned 가 덮어쓰지 않도록 setdefault
    for ko, en in _load_learned_tokens().items():
        if ko not in m and en and isinstance(en, str):
            m[ko] = en
    return m


_TOKEN_MAP = None


def translate_to_english(raw_name):
    """raw_name 의 한글 토큰을 영문으로 치환한 표시용 문자열 반환.

    1) 선두 [...] / (...) 마케팅 brackets 제거
    2) " - " 또는 " · " 뒤 컵노트/세일 표기 제거
    3) 선두 1-4자리 숫자 SKU 제거 (예: "25 과테말라" → "과테말라")
    4) 다중 단어 표현 치환 ("핑크 부르봉" → "Pink Bourbon")
    5) 단어별 토큰 치환 (한글 → 영문)
    """
    global _TOKEN_MAP
    if _TOKEN_MAP is None:
        _TOKEN_MAP = _build_token_map()

    if not raw_name:
        return ""
    s = raw_name.strip()

    # 0) 변형 선택자(U+FE0E / U+FE0F) 로 감싼 마케팅 라벨 제거.
    # 일부 vendor(royalcoffee 등) 가 '︎이벤트︎', '︎온라인전용︎' 식으로 감싸 표기.
    s = re.sub(r"[︎️]([^︎️]+)[︎️]\s*", "", s)
    s = s.replace("︎", "").replace("️", "")

    # 1) 선두 brackets 제거
    while s.startswith(("[", "(")):
        close = "]" if s.startswith("[") else ")"
        idx = s.find(close)
        if idx < 0:
            break
        s = s[idx + 1:].strip()

    # 2) 컵노트·세일 꼬리 제거
    for sep in (" - ", " -", " · "):
        i = s.find(sep)
        if i > 0:
            s = s[:i].strip()
            break

    # 3) 선두 숫자 SKU 제거 (1-4자리)
    s = re.sub(r"^\d{1,4}\s+", "", s)

    # 4) 다중 단어 치환 (수동 + 학습 사전)
    s = _multi_word_replace(s)
    # 학습 사전의 다중 단어 (공백 포함) 도 미리 치환
    learned = _load_learned_tokens()
    multi_learned = [(k, v) for k, v in learned.items()
                     if " " in k and isinstance(v, str) and v]
    multi_learned.sort(key=lambda x: -len(x[0]))
    for ko, en in multi_learned:
        s = s.replace(ko, en)

    # 5) 단어별 치환 — 공백으로 split 후 매핑
    tokens = s.split()
    out = []
    for t in tokens:
        # 콤마/쉼표 등 끝에 붙은 구두점 분리 처리
        prefix, core, suffix = "", t, ""
        while core and not (core[0].isalnum() or "가" <= core[0] <= "힯"):
            prefix += core[0]; core = core[1:]
        while core and not (core[-1].isalnum() or "가" <= core[-1] <= "힯"):
            suffix = core[-1] + suffix; core = core[:-1]
        # 직접 매핑 시도 (대소문자 무시)
        for key, val in _TOKEN_MAP.items():
            if core == key:
                core = val
                break
        out.append(prefix + core + suffix)

    s = " ".join(out)
    # 중복 공백 정리
    s = re.sub(r"\s+", " ", s).strip()

    # Title Case 후처리 — momos 처럼 모두 소문자 영문으로 저장된 케이스 보정.
    # 단, 이미 대문자가 섞인 단어(SHB, EP, G1, Yirgacheffe 등)는 손대지 않음.
    titled = []
    for w in s.split():
        if any(c.isupper() for c in w):
            titled.append(w)              # 이미 대소문자 섞인 단어 → 보존
        elif w and w[0].isascii() and w[0].isalpha():
            titled.append(w[0].upper() + w[1:])   # 소문자 영문 → 첫 글자 대문자
        else:
            titled.append(w)
    s = " ".join(titled)

    # 영문+한글 중복 제거 (royalcoffee 패턴)
    # 예: "Ethiopia Yirgacheffe Addisu Kidane Natural G1 Ethiopia 아디수 키다네 Natural G1"
    #     → "Ethiopia Yirgacheffe Addisu Kidane Natural G1"
    # 산지 영문명이 두 번 등장하면, 두 번째 등장 이전까지만 유지.
    for country_en in set(COUNTRY_KO.values()) | {"Colombia", "Ethiopia", "Guatemala", "Brazil", "Kenya", "Panama"}:
        idx = s.find(country_en)
        if idx >= 0:
            second = s.find(country_en, idx + len(country_en))
            if second > 0:
                s = s[:second].rstrip()
                break
    return s


def extract_from_name(raw_name, origin=None):
    """raw_name 에서 region/variety/process/grade 정규식 추출.

    origin 이 주어지면 해당 산지의 region 사전만 사용 → 오매칭 방지
    (예: '바이아' 가 다른 산지에서 다른 의미일 가능성 차단).
    """
    if not raw_name:
        return {}
    t = _norm(raw_name)
    out = {}
    if v := _match_dict(t, PROCESS):
        out["process"] = v
    if v := _match_dict(t, VARIETY):
        out["variety"] = v
    if v := _match_dict(t, GRADE):
        out["grade"] = v
    # 지역은 origin 매핑된 사전만 사용
    if origin:
        key = origin.lower().replace(" ", "_")
        rm = REGION_BY_ORIGIN.get(key)
        if rm and (v := _match_dict(t, rm)):
            out["region"] = v
    return out


# ─────────────────────────────────────────────────────────────────
# 단독 실행 — data/beans.json 의 빈 칸을 정규식으로 채움.
# ─────────────────────────────────────────────────────────────────

def _save(payload):
    json.dump(payload, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def main(dry_run=False):
    payload = json.load(open(DATA, encoding="utf-8"))
    beans = payload["beans"]
    filled = {"region": 0, "variety": 0, "process": 0, "grade": 0, "display_name": 0}
    touched = 0
    for b in beans:
        result = extract_from_name(b.get("raw_name"), b.get("origin"))
        changed = False
        for k, v in result.items():
            if not b.get(k):
                b[k] = v
                filled[k] += 1
                changed = True
        # display_name — 표시용 영문 정규화 이름. 항상 갱신(raw_name 이 바뀌면 따라감).
        if rn := b.get("raw_name"):
            dn = translate_to_english(rn)
            if dn and dn != b.get("display_name"):
                b["display_name"] = dn
                filled["display_name"] += 1
                changed = True
        if changed:
            touched += 1

    print(f"정규식 사전 채움 결과 — {touched}/{len(beans)}종 보강")
    for k, n in filled.items():
        print(f"  {k:14s}: +{n}")
    if dry_run:
        print("(dry-run — 저장 안 함)")
    else:
        _save(payload)
        print(f"저장: {DATA}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
