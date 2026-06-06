"""한글 농장/로트명 → 영문 음역 (Gemini Flash-Lite, 학습형 사전).

설계:
  - 결과를 data/learned_tokens.json 에 영구 저장
  - 같은 토큰은 캐시 hit → Gemini 재호출 0
  - 신규 농장만 호출 → 출시 후 운영 시 월 ₩100-200 수준

사용:
    export GEMINI_API_KEY=...
    python3 gemini_translit.py                     # 잔존 한글 자동 추출 + 음역
    python3 gemini_translit.py --tokens "다테하,코케"  # 특정 토큰만
    python3 gemini_translit.py --apply             # 음역 후 name_parser 재실행
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "beans.json")
LEARNED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "learned_tokens.json")
BATCH_SIZE = 30
MODEL = os.environ.get("BURLAP_TRANSLIT_MODEL", "gemini-2.5-flash-lite")

# 무시할 토큰 (의미 없는 fragment)
SKIP_TOKENS = {"일", "월", "년", "원", "개", "종", "건"}


def load_learned():
    if os.path.exists(LEARNED):
        try:
            return json.load(open(LEARNED, encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_learned(d):
    os.makedirs(os.path.dirname(LEARNED), exist_ok=True)
    json.dump(d, open(LEARNED, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, sort_keys=True)


def extract_korean_tokens():
    """beans.json display_name 들에서 잔존 한글 토큰 추출 (빈도순).
    다중 단어 표현도 한 토큰으로 묶어 추출 (예: "산타 펠리사" → 하나).
    """
    d = json.load(open(DATA, encoding="utf-8"))
    tokens = Counter()
    for b in d["beans"]:
        dn = b.get("display_name", "")
        if not dn:
            continue
        # 한글 단어 (다중 단어 표현 포함). 1자 단독은 노이즈 가능성 ↑
        for w in re.findall(r"[가-힯]+(?:\s+[가-힯]+){0,3}", dn):
            w = w.strip()
            if len(w) >= 2 and w not in SKIP_TOKENS:
                tokens[w] += 1
    return tokens


def gemini_batch(tokens):
    """토큰 리스트 → 한글:영문 dict. 실패 시 빈 dict."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 환경변수 필요")

    prompt = f"""You are a specialty coffee terminology expert. Convert these Korean coffee names (farm names, lot names, region names, varieties, producers) into their proper original spelling.

Rules:
- If the Korean is a phonetic transliteration of a Spanish/Portuguese/Amharic/English/Bahasa name, use the ORIGINAL language's correct spelling
  · "다테하" → "Datterra" (Brazilian farm)
  · "산타펠리사" → "Santa Felisa" (Guatemalan farm)
  · "에드윈 노레냐" → "Edwin Noreña" (Colombian producer)
  · "옴블리곤" → "Ombligón" (variety)
- Preserve diacritics: é, ñ, á, ô, ü, ç
- For Ethiopian/East African names, use established English Romanization
  · "벤사" → "Bensa", "구지" → "Guji", "예가체프" → "Yirgacheffe"
- If you're not confident (rare/unknown farm), use simple phonetic Romanization
- Return ONLY a JSON object — no markdown fence, no explanation

Korean tokens:
{json.dumps(tokens, ensure_ascii=False)}

Return JSON map like: {{"다테하":"Datterra","코케":"Koke"}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(body).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"HTTP {e.code}: {body[:200]}")

    text = resp["candidates"][0]["content"]["parts"][0]["text"]
    # responseMimeType=application/json 이면 보통 순수 JSON 반환
    return json.loads(text)


def main():
    args = sys.argv[1:]
    learned = load_learned()
    print(f"기존 학습 사전: {len(learned)}개 토큰")

    # 토큰 수집
    if "--tokens" in args:
        idx = args.index("--tokens") + 1
        tokens = [t.strip() for t in args[idx].split(",") if t.strip()]
        print(f"수동 토큰: {len(tokens)}개")
    else:
        counter = extract_korean_tokens()
        total_occur = sum(counter.values())
        tokens = [t for t, _ in counter.most_common()]
        print(f"잔존 한글 토큰: {len(tokens)}개 (총 {total_occur}회 등장)")

    # 캐시 미스만 추출
    new_tokens = [t for t in tokens if t not in learned]
    print(f"신규 (캐시 미스): {len(new_tokens)}개")
    print(f"캐시 히트(스킵): {len(tokens) - len(new_tokens)}개")

    if not new_tokens:
        print("✓ 모두 캐시됨 — Gemini 호출 불필요")
        if "--apply" in args:
            _apply_to_beans()
        return

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY 미설정 — 같은 창에서 export 후 재실행")
        print("    학습 사전은 그대로 유지되며, 다음 회차 자동 진행.")
        return

    # 배치 호출
    batches = [new_tokens[i:i + BATCH_SIZE] for i in range(0, len(new_tokens), BATCH_SIZE)]
    print(f"\n배치 {len(batches)}개 ({BATCH_SIZE}개/배치, 모델 {MODEL}) 호출")
    added = 0
    for i, batch in enumerate(batches):
        try:
            result = gemini_batch(batch)
            hit = 0
            for ko, en in result.items():
                ko = ko.strip()
                if isinstance(en, str) and en.strip() and ko in batch:
                    learned[ko] = en.strip()
                    added += 1
                    hit += 1
            print(f"  배치 {i+1}/{len(batches)}: +{hit}/{len(batch)}")
            save_learned(learned)
            time.sleep(2)
        except Exception as e:
            print(f"  배치 {i+1} 실패: {type(e).__name__}: {str(e)[:120]}")
            time.sleep(5)

    print(f"\n학습 완료: +{added}개 토큰 → {LEARNED}")

    if "--apply" in args:
        _apply_to_beans()


def _apply_to_beans():
    """학습 사전 갱신 후 name_parser 재실행 → display_name 갱신."""
    print("\nname_parser 재실행으로 display_name 갱신...")
    import importlib
    import name_parser
    importlib.reload(name_parser)   # 사전 다시 로드
    name_parser.main()


if __name__ == "__main__":
    main()
