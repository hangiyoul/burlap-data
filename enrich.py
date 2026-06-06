"""상세페이지 enrich — 컵노트·가격·품종·지역·농장 등을 채움.

각 생두 상세페이지 텍스트를 Gemini로 구조화 추출 → data/beans.json 갱신.
무료 등급 한도(분당/일일) 준수: 호출 간격(기본 4초) + 한도 도달 시 진행분 저장 후 중단.
다시 실행하면 아직 안 채운 것만 이어서(증분).

사용 (키는 터미널 env 로만, 채팅 금지):
  export GEMINI_API_KEY=...
  python3 enrich.py             # 증분 (컵노트 없는 것만)
  python3 enrich.py --all       # 전체 재추출
  python3 enrich.py --debug     # 첫 1건으로 호출 진단

기본 모델: gemini-2.5-flash. 변경: export BURLAP_GEMINI_MODEL=gemini-2.5-flash-lite (더 저렴)
호출 간격: export ENRICH_PACE=4   (초)
이후: cp data/beans.json Burlap/Burlap/beans.json  → 앱 재빌드
"""
import json
import os
import sys
import time
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get, get_bytes, strip_tags
from extract import gemini_extract, detail_image_urls, _bean_from_data, QuotaExceeded

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "beans.json")
FILL = ("region", "farm", "producer", "altitude", "variety", "process", "grade", "cup_notes", "price")
PACE = float(os.environ.get("ENRICH_PACE", "5"))   # 무료 RPM 준수 (≈12/min)
MAX_IMGS = int(os.environ.get("ENRICH_MAX_IMAGES", "4"))
_IMG_MAX_BYTES = 5_000_000        # 이미지 1장 최대
_REQ_MAX_BYTES = 14_000_000       # Gemini 인라인 요청 총량 가드(~20MB 한도)


def _save(payload):
    json.dump(payload, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def _base_of(url):
    s = urlsplit(url)
    return f"{s.scheme}://{s.netloc}" if s.scheme else ""


def _mime_of(url):
    u = url.lower()
    if ".png" in u:
        return "image/png"
    if ".webp" in u:
        return "image/webp"
    return "image/jpeg"


def _merge_fill(base_data, extra):
    """extra(비전 결과)로 base_data 의 빈 칸만 채움."""
    if not extra:
        return base_data
    if not base_data:
        return extra
    for k, v in extra.items():
        if v in (None, "", [], {}):
            continue
        if base_data.get(k) in (None, "", [], {}):
            base_data[k] = v
    return base_data


def _fetch_detail_images(html, page_url):
    """상세 설명 이미지 다운로드 → [(mime, bytes)] (최대 MAX_IMGS, 6MB 초과 제외)."""
    base = _base_of(page_url)
    imgs, total = [], 0
    for iu in detail_image_urls(html, base, limit=MAX_IMGS * 3):
        try:
            raw = get_bytes(iu, base=base, referer=page_url)
        except Exception:
            continue
        if not raw or len(raw) > _IMG_MAX_BYTES or total + len(raw) > _REQ_MAX_BYTES:
            continue
        imgs.append((_mime_of(iu), raw))
        total += len(raw)
        if len(imgs) >= MAX_IMGS:
            break
    return imgs


def _needs(b):
    """핵심 스펙(컵노트·품종·지역) 중 하나라도 비면 enrich 대상."""
    return not (b.get("cup_notes") and b.get("variety") and b.get("region"))


def enrich(force=False):
    os.environ.setdefault("BURLAP_GEMINI_MODEL", "gemini-2.5-flash")
    payload = json.load(open(DATA, encoding="utf-8"))
    beans = payload["beans"]
    n = len(beans)
    enriched = processed = 0

    # 0단계: 정규식 사전 채움 — LLM 호출 전에 raw_name 에서 잡을 수 있는
    # region/variety/process/grade 를 우선 채움. Vision OCR 빈도를 낮춰
    # 무료 한도를 더 오래 버티게 함.
    try:
        from name_parser import extract_from_name
        prefilled = 0
        for b in beans:
            r = extract_from_name(b.get("raw_name"), b.get("origin"))
            for k, v in r.items():
                if not b.get(k):
                    b[k] = v
                    prefilled += 1
        if prefilled:
            _save(payload)
            print(f"[0/N] 정규식 전처리: {prefilled}개 필드 사전 채움 → LLM 호출 절감")
    except Exception as e:
        print(f"정규식 전처리 건너뜀: {type(e).__name__}: {e}")

    todo = sum(1 for b in beans if force or _needs(b))
    has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                   or os.environ.get("ANTHROPIC_API_KEY"))
    print(f"enrich 시작: {todo}/{n}종 처리 예정 | 모델 {os.environ['BURLAP_GEMINI_MODEL']} "
          f"| 키 {'있음' if has_key else '없음(!)'} | 간격 {PACE}s", flush=True)
    if not has_key:
        print("⚠️ 이 터미널에 키가 없습니다. 같은 창에서 export GEMINI_API_KEY=... 후 다시 실행하세요.", flush=True)
        return

    for i, b in enumerate(beans):
        if not force and not _needs(b):
            continue
        try:
            html = get(b["url"])
            text = strip_tags(html)
        except Exception:
            html, text = None, None
        if not text:
            print(f"  {i + 1}/{n} 본문 못 받음 → 건너뜀", flush=True)
            continue

        # 429: 분당 한도면 대기 후 재시도, 연속 실패(일일 한도로 추정) 시 중단
        def _call(**kw):
            fails = 0
            while True:
                try:
                    return gemini_extract(name=b["raw_name"], origin_hint=b.get("origin"), **kw)
                except QuotaExceeded:
                    fails += 1
                    if fails >= 4:
                        _save(payload)
                        print(f"\n⚠️ 한도 지속(일일 한도로 추정) — {i}/{n}에서 중단·저장.")
                        print("   내일(한도 리셋) 또는 결제 활성화 후 'python3 enrich.py' 다시 실행 → 이어서 채웁니다.")
                        raise SystemExit(0)
                    print(f"  분당 한도 — 35초 대기 후 재시도 ({i + 1}/{n})...")
                    time.sleep(35)

        data = _call(raw_text=text)
        processed += 1

        # 텍스트 후에도 품종/컵노트가 비면(이미지형 페이지) → 상세 이미지 비전 판독
        got_variety = (data and data.get("variety")) or b.get("variety")
        got_notes = (data and data.get("cup_notes")) or b.get("cup_notes")
        if html and (not got_variety or not got_notes):
            imgs = _fetch_detail_images(html, b["url"])
            if imgs:
                vdata = _call(raw_text=text, images=imgs)
                data = _merge_fill(data, vdata)
                if vdata and (vdata.get("variety") or vdata.get("cup_notes")):
                    print(f"     ↳ 이미지 {len(imgs)}장 비전 판독", flush=True)
                time.sleep(PACE)

        if data:
            bean = _bean_from_data(b["vendor"], b["url"], data, b["raw_name"], b.get("origin"))
            if bean is None:
                b["_drop"] = True
            else:
                d = bean.to_dict()
                for k in FILL:
                    # 증분: 빈 칸만 채움(기존 좋은 값 보존). --all: 덮어쓰기.
                    if d.get(k) and (force or b.get(k) in (None, "", [], {})):
                        b[k] = d[k]
                if d.get("origin") and (force or not b.get("origin")):
                    b["origin"] = d["origin"]
                if b.get("cup_notes"):
                    enriched += 1

        notes = len(b.get("cup_notes") or [])
        print(f"  {i + 1}/{n} {b['raw_name'][:28]:28} → 컵노트 {notes}개"
              + (f" {b.get('price')}" if b.get("price") else ""), flush=True)
        if processed % 10 == 0:
            _save(payload)
        time.sleep(PACE)

    payload["beans"] = [b for b in beans if not b.get("_drop")]
    payload["count"] = len(payload["beans"])
    _save(payload)
    print(f"\nenrich 완료: {payload['count']}종 (컵노트 채움 {enriched}) → {DATA}")
    print("→ cp data/beans.json Burlap/Burlap/beans.json 후 앱 재빌드")


def debug_one():
    import urllib.request, urllib.error
    os.environ.setdefault("BURLAP_GEMINI_MODEL", "gemini-2.5-flash")
    b = json.load(open(DATA, encoding="utf-8"))["beans"][0]
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    print("GEMINI key set:", bool(key), "(len", len(key or ""), ") model:", os.environ["BURLAP_GEMINI_MODEL"])
    if not key:
        print("→ 키가 env에 없음. 같은 창에서 export GEMINI_API_KEY=... 후 재실행."); return
    model = os.environ["BURLAP_GEMINI_MODEL"]
    ep = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": "Reply with JSON {\"ok\":true}"}]}],
            "generationConfig": {"responseMimeType": "application/json"}}
    req = urllib.request.Request(ep, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            print("HTTP", getattr(r, "status", "?")); print(r.read().decode()[:600])
    except urllib.error.HTTPError as e:
        print("HTTPError", e.code); print(e.read().decode()[:900])
    except Exception as e:
        print("ERR", type(e).__name__, e)


if __name__ == "__main__":
    if "--debug" in sys.argv:
        debug_one()
    else:
        enrich(force="--all" in sys.argv)
