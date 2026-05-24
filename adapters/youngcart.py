"""영카트(youngcart) 어댑터 (sewoonggc).

- 검색: /shop/search.php?q={kw}
- 상세: /shop/item.php?it_id={id}
- 상품명 = 링크 텍스트 ('[에티오피아] ...' 형태)

검증: sewoonggc 에티오피아 20종.
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import get, strip_tags, matches  # noqa: E402


def search(base, keywords):
    """return: [(it_id, name)]"""
    seen = {}
    for kw in keywords:
        try:
            s = get(f"{base}/shop/search.php?q={kw}")
        except Exception:
            continue
        for it, c in re.findall(r"it_id=(\d+)[^>]*>(.{0,160}?)</a>", s, re.S):
            nm = strip_tags(c)
            if it in seen or not nm:
                continue
            if matches(nm, keywords):
                seen[it] = nm
    return list(seen.items())


def item_url(base, it_id):
    return f"{base}/shop/item.php?it_id={it_id}"


if __name__ == "__main__":
    rows = search("https://www.sewoonggc.com", ["에티오피아", "ethiopia"])
    print(f"sewoonggc 에티오피아 {len(rows)}종")
    for _, nm in rows[:10]:
        print("  -", nm[:50])
