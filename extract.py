"""추출/정규화 레이어 — raw → 표준 GreenBean.

핵심 설계(FINDINGS §2): fetch 어댑터는 얇게, '의미 추출'은 여기서 공통 처리.
정규식은 깨지기 쉽다(판매가→환불정책, 농장→방문버튼, 검색 혼입). → LLM 권장.

두 경로:
  1. normalize_with_llm(...)  ← 운영 권장. Claude(Haiku)가 텍스트/이미지에서 문맥 판단 추출.
  2. normalize_with_rules(name) ← 의존성/키 0 폴백. 상품명에서 추출 가능한 만큼만.
normalize_with_llm 는 키/SDK 없거나 호출 실패 시 자동으로 rules 폴백.

의존성(LLM 모드): pip install anthropic  +  env ANTHROPIC_API_KEY
모델: 기본 claude-haiku-4-5 (저가). env BURLAP_LLM_MODEL 로 변경 가능.
"""
import os
import re
import json
import base64
from schema import GreenBean

# 추출 모델 — 저가 Haiku 기본 (Edan 선호). 필요 시 env 로 교체.
EXTRACTION_MODEL = os.environ.get("BURLAP_LLM_MODEL", "claude-haiku-4-5")

# 상세 설명 이미지로 추정되지 않는 것(로고·아이콘·배너·결제안내 등) 제외 패턴
_IMG_SKIP = re.compile(
    r"logo|icon|favicon|banner|btn|button|sns|share|sprite|blank|loading|spinner|"
    r"common|/skin/|top_|bottom_|header|footer|payment|delivery|shipping|notice|"
    r"policy|refund|exchange|guide|/t50_|\.svg|\.gif", re.I)
# 상세 설명 영역에 흔한 경로(있으면 우선)
_IMG_KEEP = re.compile(
    r"goods|editor|/se2?|/data/|upload|detail|product|content|board|/web/", re.I)


def detail_image_urls(html, base="", limit=5):
    """상세페이지 HTML → 설명/스펙 이미지로 추정되는 절대 URL 목록(문서 순서, 최대 limit)."""
    from urllib.parse import urljoin
    out, seen = [], set()
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I):
        src = m.group(1).strip()
        if not src or src.startswith("data:"):
            continue
        url = src if src.startswith("http") else \
              ("https:" + src if src.startswith("//") else urljoin(base + "/", src))
        if url in seen or _IMG_SKIP.search(url):
            continue
        seen.add(url)
        out.append((url, bool(_IMG_KEEP.search(url))))
    # 설명영역 경로 가진 이미지 우선, 그다음 등장 순서
    ranked = [u for u, keep in out if keep] + [u for u, keep in out if not keep]
    return ranked[:limit]

# --- 이름 표기 규칙 (커핑스푼 스타일: 영문 Title Case) ---
# 모두 대문자로 둘 약어 (COE, CO, XO 등). 필요 시 추가만.
NAME_ACRONYMS = {"COE", "CO", "XO", "EA", "CM", "EP", "RFA", "G1", "G2", "G3", "G4", "Q1", "Q2"}
# 이름 중간에서 소문자 유지하는 연결어 = 전치사/접속사만.
# (관사 El/La/Los/Las 는 농장명 일부이므로 대문자 유지 — El Carmen, La Suiza)
NAME_CONNECTORS = {"de", "del", "da", "do", "y", "e"}


def format_name(name: str) -> str:
    """영문 커피 이름 표기 정규화.
    - 단어별 첫 글자 대문자 (Title Case)
    - NAME_ACRONYMS 는 전부 대문자 (COE/CO/XO ...)
    - 숫자 포함 토큰(CGLE-17, 17/18 등)은 알파벳부 대문자 유지
    - 연결어(de/la ...)는 중간이면 소문자 (스페셜티 업계 관례) — 첫 단어면 대문자
    """
    words = name.split()
    out = []
    for idx, w in enumerate(words):
        bare = re.sub(r"[^A-Za-z]", "", w)
        upper = bare.upper()
        if not bare:
            out.append(w)  # 기호/숫자만
        elif upper in NAME_ACRONYMS or (any(c.isdigit() for c in w) and any(c.isalpha() for c in w)):
            out.append(w.upper())                       # COE, XO, CGLE-17 ...
        elif bare.lower() in NAME_CONNECTORS and idx != 0:
            out.append(w.lower())                       # de, la (중간)
        else:
            out.append(w[:1].upper() + w[1:].lower())   # Title Case
    return " ".join(out)


# LLM 추출 시스템 프롬프트 — 모든 항목에 재사용(프롬프트 캐싱 대상).
# ⚠️ Haiku 4.5 최소 캐시 프리픽스 = 4096 토큰. 이 프롬프트는 그보다 짧아
#    실제 캐시 적중은 안 될 수 있음(few-shot/사전 확장 시 적중). cache_control 은 올바른 위치에 둠.
_EXTRACT_SYSTEM = """You extract structured data about GREEN (unroasted) coffee beans from Korean coffee vendor product pages — given either raw page text or a spec-card image.

Return ONLY the requested fields. Rules:
- Output values in ENGLISH. Korean place/farm/variety names: use the standard Latin/Spanish spelling (e.g. 시다마→Sidama, 예가체프→Yirgacheffe, 카투라→Caturra, 워시드→Washed, 내추럴→Natural). Cup notes: translate to English (블루베리→Blueberry, 자스민→Jasmine).
- If a field is absent, return null. Do NOT guess.
- IGNORE unrelated text: shipping/delivery notices, refund policy, payment popups, recommended/related products, reviews/Q&A, "방문하기"/buttons. Never put those into any field.
- `origin` = country (e.g. Ethiopia, Colombia, Guatemala). Infer from the product name if needed.
- `is_green_bean` = false if the item is NOT a single green-bean lot (e.g. a gift/sample SET, a coffee-map set, roasted beans only, drip bags). Decaf green beans = true.
- `cup_notes` = array of individual English flavor notes.
- `name` = clean English product name (farm/region + variety + process), Title Case.
"""

# 구조화 출력 스키마 (json_schema). 모든 필드 nullable + additionalProperties:false.
def _nullable(t):
    return {"type": [t, "null"]}

_EXTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "is_green_bean": {"type": "boolean"},
        "name": _nullable("string"),
        "origin": _nullable("string"),
        "region": _nullable("string"),
        "farm": _nullable("string"),
        "producer": _nullable("string"),
        "altitude": _nullable("string"),
        "variety": _nullable("string"),
        "process": _nullable("string"),
        "grade": _nullable("string"),
        "cup_notes": {"type": "array", "items": {"type": "string"}},
        "price": _nullable("string"),
    },
    "required": ["is_green_bean", "name", "origin", "region", "farm", "producer",
                 "altitude", "variety", "process", "grade", "cup_notes", "price"],
}

# --- 규칙 기반 폴백 (상품명에서 추출 가능한 수준) ---
_VARIETIES = ["geisha", "gesha", "게이샤", "caturra", "카투라", "pink bourbon", "핑크 버번",
              "yellow bourbon", "옐로우 버번", "bourbon", "버번", "typica", "티피카",
              "heirloom", "kurume", "wolisho", "dega", "74158", "74110", "74112",
              "sidra", "시드라", "pacamara", "ombligon", "sudan rume"]
_PROCESSES = [("digital decaf", "Decaf"), ("디카페인", "Decaf"), ("decaf", "Decaf"),
              ("red honey", "Red Honey"), ("white honey", "White Honey"),
              ("black honey", "Black Honey"), ("허니", "Honey"), ("honey", "Honey"),
              ("anaerobic", "Anaerobic"), ("무산소", "Anaerobic"),
              ("carbonic", "Carbonic"), ("2중탄소", "Carbonic"), ("퍼먼티드", "Ferment"),
              ("워시드", "Washed"), ("washed", "Washed"),
              ("내추럴", "Natural"), ("natural", "Natural")]
_GRADES = ["G1", "G2", "G3", "G4", "Q1", "Q2", "EP", "그레이드 제로", "Grade Zero"]


def _find(name, table):
    low = name.lower()
    for t in table:
        if t.lower() in low:
            return t
    return None


def normalize_with_rules(vendor, url, name, origin_hint=None):
    """상품명만으로 best-effort 정규화. 폴백용. (LLM이 있으면 그쪽 우선)"""
    proc = None
    low = name.lower()
    for key, val in _PROCESSES:
        if key.lower() in low:
            proc = val
            break
    return GreenBean(
        vendor=vendor, url=url, raw_name=name,
        origin=origin_hint,
        variety=_find(name, _VARIETIES),
        process=proc,
        grade=_find(name, _GRADES),
    )


def _image_block(image_path):
    media = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


def normalize_with_llm(vendor, url, *, raw_text=None, image_path=None, name=None,
                       origin_hint=None, model=None):
    """운영 권장 경로. raw 텍스트 또는 스펙카드 이미지 → 표준 GreenBean (Claude/Haiku 추출).

    - 텍스트·이미지 동시 입력 가능(둘 다 주면 함께 판단).
    - 키/SDK 없거나 호출 실패 시 → normalize_with_rules 자동 폴백(예외 안 던짐).
    - 비(非)생두(세트/원두 등)로 판정되면 None 반환(필터).
    """
    def _fallback():
        return normalize_with_rules(vendor, url, name or (raw_text or "")[:80], origin_hint)

    if not raw_text and not image_path:
        return _fallback()
    try:
        import anthropic
    except ImportError:
        return _fallback()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _fallback()

    try:
        client = anthropic.Anthropic()
        content = []
        if image_path:
            content.append(_image_block(image_path))
        if raw_text:
            content.append({"type": "text", "text": raw_text[:8000]})
        hint = f"\n(Vendor: {vendor}. Likely origin: {origin_hint}.)" if origin_hint else ""
        content.append({"type": "text",
                        "text": "Extract the green coffee fields as JSON." + hint})

        resp = client.messages.create(
            model=model or EXTRACTION_MODEL,
            max_tokens=1024,
            system=[{"type": "text", "text": _EXTRACT_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],  # 재사용 프롬프트 캐싱(≥4096토큰 시 적중)
            messages=[{"role": "user", "content": content}],
            output_config={"format": {"type": "json_schema", "schema": _EXTRACT_SCHEMA}},
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = json.loads(text)
    except Exception:
        return _fallback()  # 네트워크/파싱/한도 등 모든 실패 → 폴백

    if data.get("is_green_bean") is False:
        return None  # 세트·원두 등 오탐 제거

    nm = data.get("name") or name or ""
    bean = GreenBean(
        vendor=vendor, url=url, raw_name=format_name(nm) if nm else (name or ""),
        origin=data.get("origin") or origin_hint,
        region=data.get("region"), farm=data.get("farm"),
        producer=data.get("producer"), altitude=data.get("altitude"),
        variety=data.get("variety"), process=data.get("process"),
        grade=data.get("grade"),
        cup_notes=data.get("cup_notes") or [],
        price=(str(data["price"]) if data.get("price") is not None else None),
    )
    return bean


def _s(v):
    """문자열 필드 정규화 — 리스트면 ', '로, 숫자면 str로, None은 유지."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def _split_origin(origin, region):
    """origin 에 콤마(예: 'Costa Rica, Ethiopia') → 첫 국가만 origin, 나머지는 region 으로."""
    if origin and "," in origin:
        parts = [p.strip() for p in origin.split(",") if p.strip()]
        if parts:
            rest = ", ".join(parts[1:])
            return parts[0], (region or (rest or None))
    return origin, region


def _bean_from_data(vendor, url, data, name, origin_hint):
    """LLM 응답(dict) → GreenBean. 비생두면 None."""
    if data.get("is_green_bean") is False:
        return None
    nm = data.get("name") or name or ""
    cn = data.get("cup_notes") or []
    if not isinstance(cn, list):
        cn = [str(cn)]
    origin, region = _split_origin(_s(data.get("origin")) or origin_hint, _s(data.get("region")))
    return GreenBean(
        vendor=vendor, url=url,
        raw_name=format_name(nm) if nm else (name or ""),
        origin=origin,
        region=region, farm=_s(data.get("farm")),
        producer=_s(data.get("producer")), altitude=_s(data.get("altitude")),
        variety=_s(data.get("variety")), process=_s(data.get("process")),
        grade=_s(data.get("grade")),
        cup_notes=[str(x) for x in cn],
        price=_s(data.get("price")),
    )


class QuotaExceeded(Exception):
    """Gemini 무료 한도(429) — 호출자가 백오프/중단 판단."""


# 페이지 텍스트 한도 — 길게(스펙·컵노트가 본문 하단에 있는 경우 대비). env 로 조정.
_TEXT_LIMIT = int(os.environ.get("EXTRACT_TEXT_LIMIT", "14000"))


def gemini_extract(*, raw_text=None, name=None, origin_hint=None, images=None, key=None, model=None):
    """Gemini REST 추출 → dict (실패 None, 429 시 QuotaExceeded).

    images: [(mime_type, bytes), ...] — 스펙/컵노트가 이미지로 박힌 페이지용(비전).
    """
    import urllib.request
    import urllib.error
    key = key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key or (not raw_text and not images):
        return None
    model = model or os.environ.get("BURLAP_GEMINI_MODEL", "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    prompt = (_EXTRACT_SYSTEM +
              "\n\nReturn ONLY a JSON object with these keys: is_green_bean(boolean), "
              "name, origin, region, farm, producer, altitude, variety, process, grade, "
              "cup_notes(array of strings), price. Use null when a value is absent.\n"
              "Some specs (variety/process/region) and cupping notes may appear only inside "
              "the attached product images — read text from images too.\n\n"
              "PRODUCT NAME: " + (name or "") +
              (f"\nLIKELY ORIGIN: {origin_hint}" if origin_hint else "") +
              "\n\nPAGE TEXT:\n" + (raw_text or "")[:_TEXT_LIMIT])
    parts = [{"text": prompt}]
    for mime, b in (images or []):
        parts.append({"inline_data": {"mime_type": mime,
                                      "data": base64.b64encode(b).decode("ascii")}})
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    import time
    req = urllib.request.Request(
        endpoint, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    resp = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise QuotaExceeded()
            if e.code in (500, 502, 503, 504) and attempt < 2:
                time.sleep(8 * (attempt + 1))   # 일시 과부하 → 백오프 재시도
                continue
            return None
        except Exception:
            if attempt < 2:
                time.sleep(5)
                continue
            return None
    if resp is None:
        return None
    try:
        return json.loads(resp["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        return None


def normalize_with_gemini(vendor, url, *, raw_text=None, name=None, origin_hint=None, key=None, model=None):
    """Gemini(무료) 추출 경로. 키/텍스트 없거나 실패·한도 시 규칙 폴백."""
    def _fallback():
        return normalize_with_rules(vendor, url, name or (raw_text or "")[:80], origin_hint)
    try:
        data = gemini_extract(raw_text=raw_text, name=name, origin_hint=origin_hint, key=key, model=model)
    except QuotaExceeded:
        return _fallback()
    if not data:
        return _fallback()
    return _bean_from_data(vendor, url, data, name, origin_hint)


def normalize_auto(vendor, url, *, raw_text=None, name=None, origin_hint=None):
    """가용한 키에 따라 자동 선택: Gemini(무료) → Claude → 규칙 폴백."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return normalize_with_gemini(vendor, url, raw_text=raw_text, name=name, origin_hint=origin_hint)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return normalize_with_llm(vendor, url, raw_text=raw_text, name=name, origin_hint=origin_hint)
    return normalize_with_rules(vendor, url, name or (raw_text or "")[:80], origin_hint)


def merge_spec(bean: GreenBean, spec: dict):
    """spec_ocr 결과(dict) → 기존 bean에 병합. SPEC_TO_FIELD 기준."""
    from schema import SPEC_TO_FIELD
    for k, v in (spec or {}).items():
        field = SPEC_TO_FIELD.get(k)
        if not field or v in (None, ""):
            continue
        if field == "cup_notes" and isinstance(v, str):
            v = [x.strip() for x in re.split(r"[,/·]", v) if x.strip()]
        setattr(bean, field, v)
    return bean
