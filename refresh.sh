#!/usr/bin/env bash
#
# refresh.sh — 맥북(한국 IP)에서 전체 생두 데이터를 신선하게 갱신 후 GitHub 에 푸시.
#
# 왜 필요? Royal Coffee Korea(royalcoffeekorea.co.kr)는 GitHub 데이터센터(미국) IP 를
# 차단해서 클라우드 자동 크롤로는 갱신이 안 됨. 한국 IP(이 맥북)에서 돌려야 신선해짐.
# 나머지 판매처는 어차피 하루 3번 클라우드에서 자동 갱신되므로, 이 스크립트는
# 주 1회 정도 royalcoffee 신선화 용으로 가볍게 돌리면 충분.
#
# 사용:
#   ./refresh.sh
#   (시장지표/스토리 번역까지 갱신하려면 먼저: export GEMINI_API_KEY="...")
#
set -e
cd "$(dirname "$0")"

echo "▶ 최신 원격 반영 (봇 커밋과 충돌 방지)"
git pull --rebase --autostash origin main

echo "▶ 0/4 직전 스냅샷 (어제 대비 변화 계산용)"
cp data/beans.json data/beans_prev.json 2>/dev/null || true

echo "▶ 1/4 전체 크롤 (royalcoffee 포함 · 한국 IP)"
python3 crawl_run.py

echo "▶ 2/4 재고 확인"
python3 stock_run.py || echo "  (재고 확인 건너뜀)"

echo "▶ 3/4 어제 대비 변화 계산"
python3 make_changes.py || echo "  (변화 계산 건너뜀)"

echo "▶ 4/4 시장지표 + 스토리 번역"
if [ -n "$GEMINI_API_KEY" ]; then
  python3 market_scrape.py || echo "  (시장 스크레이프 건너뜀)"
else
  echo "  GEMINI_API_KEY 미설정 → 이 단계 건너뜀 (export GEMINI_API_KEY=... 후 재실행하면 포함)"
fi

echo "▶ 커밋 & 푸시"
git add data/beans.json data/market.json
[ -f data/story_translations.json ] && git add data/story_translations.json
if git diff --cached --quiet; then
  echo "  변경 없음 — 푸시 생략"
else
  git commit -m "refresh(local): $(date -u +'%Y-%m-%dT%H:%MZ')"
  git push
  echo "✅ 완료 — 앱이 다음 실행 때 최신본을 받아요."
fi
