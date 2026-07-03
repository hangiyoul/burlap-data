"""공통 유틸 — HTTP fetch, HTML 정리, 키워드 상수.

모든 어댑터가 공유. 한글 URL 인코딩 처리 포함.
"""
import urllib.request
import ssl
import re
import html as _html
from urllib.parse import quote

# 인증서 검증 생략(일부 사이트 체인 문제 회피). 운영 시 검토.
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 산지 검색 키워드: 한글+영문 둘 다 필수 (영문 slug 상품 누락 방지)
# name_parser.COUNTRY_KO 가 분류 가능한 전 산지 포함 — 생산국 제한 없이 수집.
# (검색으로 잡힌 상품은 name_parser 가 상품명에서 산지를 재분류하므로 키 라벨은 힌트일 뿐)
ORIGIN_KEYWORDS = {
    "ethiopia":            ["에티오피아", "ethiopia"],
    "colombia":            ["콜롬비아", "colombia"],
    "kenya":               ["케냐", "kenya"],
    "guatemala":           ["과테말라", "guatemala"],
    "panama":              ["파나마", "panama"],
    "brazil":              ["브라질", "brazil"],
    "costa rica":          ["코스타리카", "costa rica"],
    "el salvador":         ["엘살바도르", "el salvador"],
    "honduras":            ["온두라스", "honduras"],
    "nicaragua":           ["니카라과", "nicaragua"],
    "yemen":               ["예멘", "yemen"],
    "tanzania":            ["탄자니아", "tanzania"],
    "rwanda":              ["르완다", "rwanda"],
    "burundi":             ["부룬디", "burundi"],
    "india":               ["인도", "india"],
    "indonesia":           ["인도네시아", "indonesia"],
    "vietnam":             ["베트남", "vietnam"],
    "peru":                ["페루", "peru"],
    "bolivia":             ["볼리비아", "bolivia"],
    "ecuador":             ["에콰도르", "ecuador"],
    "dominican republic":  ["도미니카", "dominican"],
    "jamaica":             ["자메이카", "jamaica"],
    "cuba":                ["쿠바", "cuba"],
    "mexico":              ["멕시코", "mexico"],
    "papua new guinea":    ["파푸아뉴기니", "파푸아", "뉴기니", "papua new guinea"],
    "hawaii":              ["하와이", "코나", "hawaii", "kona"],
}


def get(url, timeout=25, referer=None):
    """URL → 텍스트(HTML). 한글 경로 자동 인코딩."""
    u = quote(url, safe=":/?=&%#")
    headers = {"User-Agent": UA, "Accept-Language": "ko"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(u, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read().decode("utf-8", "ignore")


def get_bytes(url, timeout=30, referer=None, base=None):
    """URL → bytes(이미지 등). // 와 / 상대경로 처리."""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/") and base:
        url = base.rstrip("/") + url
    u = quote(url, safe=":/?=&%#")
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(u, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()


def strip_tags(t):
    """HTML 조각 → 정리된 텍스트."""
    t = re.sub(r"<script.*?</script>", "", t, flags=re.S)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", t))).strip()


def unescape(t):
    return _html.unescape(t)


def matches(name, keywords):
    """상품명이 키워드(산지) 중 하나라도 포함하는지."""
    low = name.lower()
    return any(k.lower() in low for k in keywords)
