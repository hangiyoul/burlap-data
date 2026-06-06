"""ICO (International Coffee Organization) — 일간 indicator 가격.

신뢰성 1순위. ICO 는 1963년 설립 정부간기구이며, 1965년부터 일간 가격 발표.
국제 커피 거래계약의 공식 기준가로 사용됨.

페이지: https://ico.org/coffee-prices/
포맷(HTML):
  > I-CIP 233.72 -1.6
  > Colombian Milds 297.49 -1.8
  > Other Milds 284.98 -1.8
  > Brazilian Naturals 260.00 -2.1
  > Robustas 159.94 -0.6

5개 모두 US cents/lb. 우리는 Burlap 메인 페이지에 두 개만 사용:
  - Arabica · Daily = "Other Milds" (스페셜티 사용자에게 가장 의미 있는 indicator)
  - Robusta · Daily = "Robustas"
"""
import re
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
PRICES_URL = "https://ico.org/coffee-prices/"


def _fetch(url, timeout=20):
    """ICO 페이지가 WordPress 라우팅 이슈로 200 대신 404 를 반환할 때가 있음.
    HTTPError 의 body 도 동일하게 가격 데이터 포함하므로 함께 처리.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return e.read().decode("utf-8", "ignore")
        raise


def fetch_daily():
    """반환 (모두 ¢/lb 단위):
      {
        "composite": 233.72,       # I-CIP
        "colombian_milds": 297.49,
        "other_milds": 284.98,
        "brazilian_naturals": 260.00,
        "robustas": 159.94,
        "source_url": "...",
      }
    실패 시 RuntimeError.
    """
    html = _fetch(PRICES_URL)
    # 페이지 구조: <span>I-CIP</span> ... <span>233.72</span>
    # 라벨 등장 후 최대 ~500자 안에서 첫 번째 ">소수.XX<" 패턴 추출.
    indicators = {
        "composite":          r"I-CIP",
        "colombian_milds":    r"Colombian Milds",
        "other_milds":        r"Other Milds",
        "brazilian_naturals": r"Brazilian Naturals",
        "robustas":           r"Robustas?",
    }
    out = {"source_url": PRICES_URL}
    for key, label in indicators.items():
        pat = label + r"<.{0,500}?>(\d{2,4}\.\d{2})<"
        m = re.search(pat, html, re.S)
        if not m:
            raise RuntimeError(f"ICO indicator missing: {key}")
        out[key] = float(m.group(1))
    return out


if __name__ == "__main__":
    r = fetch_daily()
    for k, v in r.items():
        if isinstance(v, float):
            print(f"  {k:22s}: {v:7.2f} ¢/lb")
    print(f"  source: {r['source_url']}")
