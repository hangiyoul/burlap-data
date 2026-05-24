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
ORIGIN_KEYWORDS = {
    "ethiopia":  ["에티오피아", "ethiopia"],
    "colombia":  ["콜롬비아", "colombia"],
    "kenya":     ["케냐", "kenya"],
    "guatemala": ["과테말라", "guatemala"],
    "panama":    ["파나마", "panama"],
    "brazil":    ["브라질", "brazil"],
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
