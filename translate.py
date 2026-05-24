"""BOP 경매 로트 스토리 영어 → 한국어 번역 (Gemini) → market.json["coe_auctions"][].lots[].storyKo.

한국인 전용 앱이므로 긴 영어 스토리를 한국어로 미리 번역해 저장한다.
- 번역 캐시(data/story_translations.json, 원문 해시 기준) → 하루 3회 크롤마다 재번역 방지(비용 0).
- GEMINI_API_KEY(또는 GOOGLE_API_KEY) 없으면 건너뜀 → 영어 원문 유지(앱이 fallback).

사용:
  GEMINI_API_KEY=... python3 translate.py        # 기존 market.json 스토리 번역(재크롤 X)
  market_scrape.py 에서 translate_auctions() 호출 → 크롤과 함께 갱신
"""
import os
import re
import json
import time
import hashlib
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "market.json")
CACHE = os.path.join(HERE, "data", "story_translations.json")
MODEL = os.environ.get("TRANSLATE_MODEL", "gemini-2.5-flash")
PROMPT = (
    "다음은 스페셜티 커피 경매 로트의 영어 소개 글이다. 자연스럽고 매끄러운 한국어로 번역하라. "
    "농장명·품종·지역 등 고유명사는 원어를 적절히 유지하고, 톤은 살리되 과장 없이. "
    "번역문만 출력(설명·따옴표·머리말 없이).\n\n원문:\n"
)


def _key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _load_cache():
    if os.path.exists(CACHE):
        try:
            return json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(c):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(c, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def _hash(text):
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()


def _gemini(text, key):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
           f":generateContent?key={key}")
    body = json.dumps({"contents": [{"parts": [{"text": PROMPT + text}]}]}).encode("utf-8")
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            r = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
            d = json.loads(r)
            return d["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:                      # 쿼터 → 대기 후 재시도
                time.sleep(20); continue
            if 500 <= e.code < 600:
                time.sleep(5 * (attempt + 1)); continue
            raise
        except Exception:
            time.sleep(3)
    return ""


def translate_auctions(auctions, key=None, pace=0.5, verbose=False):
    """BOP(파나마) 로트의 story → storyKo 채움. 번역 수(int) 반환."""
    key = key or _key()
    if not key:
        if verbose:
            print("번역 키 없음 — 스토리 번역 건너뜀(영어 유지)")
        return 0
    cache = _load_cache()
    done = 0
    for a in auctions:
        if a.get("country") != "panama":
            continue
        for lot in a.get("lots", []):
            src = (lot.get("story") or "").strip()
            if not src:
                continue
            h = _hash(src)
            ko = cache.get(h)
            if ko is None and (lot.get("storyKo") or "").strip():
                ko = lot["storyKo"].strip()   # 이미 번역돼 있으면 캐시 시드(재번역 방지)
                cache[h] = ko
                _save_cache(cache)
            if ko is None:
                ko = _gemini(src, key)
                if ko:
                    cache[h] = ko
                    _save_cache(cache)        # 진행 중 저장(중단 대비)
                    done += 1
                    if verbose:
                        print(f"  번역 {done}: {lot.get('farm','')[:30]}")
                    time.sleep(pace)
            if ko:
                lot["storyKo"] = ko
    return done


def main():
    payload = json.load(open(DATA, encoding="utf-8"))
    n = translate_auctions(payload.get("coe_auctions", []), verbose=True)
    json.dump(payload, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"번역 완료: {n}건 신규 → 저장 {DATA}")


if __name__ == "__main__":
    main()
