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
    filled = {"region": 0, "variety": 0, "process": 0, "grade": 0}
    touched = 0
    for b in beans:
        result = extract_from_name(b.get("raw_name"), b.get("origin"))
        changed = False
        for k, v in result.items():
            if not b.get(k):
                b[k] = v
                filled[k] += 1
                changed = True
        if changed:
            touched += 1

    print(f"정규식 사전 채움 결과 — {touched}/{len(beans)}종 보강")
    for k, n in filled.items():
        print(f"  {k:10s}: +{n}")
    if dry_run:
        print("(dry-run — 저장 안 함)")
    else:
        _save(payload)
        print(f"저장: {DATA}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
