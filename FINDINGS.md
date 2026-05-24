# Green Bean Scraper — 사이트별 공략법 (FINDINGS)

> 한국 생두 수입사/로스터 사이트에서 생두 카탈로그·재고·스펙을 수집하기 위한 조사 결과.
> 작성: 2026-05 / 목적: 1~2주 뒤 본 개발 시 "재발견" 없이 바로 이어가기 위함.

---

## 0. 핵심 결론 (먼저 읽기)

1. **데이터는 2층으로 나눈다**
   - **카탈로그**(이름·지역·품종·가공·컵노트): 거의 안 변함 → 정적 크롤링 OK
   - **재고/가격**(실시간): 수시 변동 → **헤드리스 브라우저(Playwright) 필수**
2. **검색은 한글+영문 둘 다** 해야 함. (momos: "에티오피아" 2종 → "ethiopia" 포함 24종)
3. **전 페이지 순회 필수**. 1페이지만 보면 절반 이상 누락.
4. **사이트마다 상품명 위치가 다름** → 플랫폼별 어댑터 불가피.
5. **재고 판정은 정적 HTML로 불가한 사이트가 있음**(Cafe24/momos). 품절 배지·버튼이 HTML에 항상 존재하고 JS로 토글 → 헤드리스로 "실제 보이는 요소"를 봐야 함.
6. **스펙이 이미지로 박힌 사이트**(momos, royalcoffee) → 비전 OCR로 추출. 스펙표 이미지는 **저채도(회색 배경, saturation≈2.0)** 로 선별 가능.

---

## 1. 대상 사이트 플랫폼 분류

| 업체 | URL | 플랫폼 | 난이도 | 비고 |
|---|---|---|---|---|
| momos | momos.co.kr | Cafe24(slug 스킨) | 🟡 | 카탈로그=검색 OK, 재고=헤드리스, 스펙=이미지OCR |
| coffeelibre | coffeelibre.kr | Cafe24(detail 스킨) | 🟢 | **생두 판매함**(처음 0은 URL패턴 차이). 스펙=텍스트(영문 병기) |
| micoffee | micoffee.co.kr | Godo/NHN | 🟢 | 검색 OK, 상품명=링크텍스트 |
| newbean | newbean.co.kr | Godo/NHN | 🟢 | 상품명에 `[에티오피아]` prefix |
| wbeans | wbeans.com | Godo/NHN | 🟢 | 상품명=**alt 속성**(링크텍스트 비어있음) |
| royalcoffee | royalcoffeekorea.co.kr | Godo/NHN | 🟡 | 검색 느슨(타산지 혼입)→제목필터, 스펙=이미지OCR |
| cobeans | cobeans.com | 자체 PHP | 🟢 | 텍스트 풀스펙(가장 깔끔) |
| sewoonggc | sewoonggc.com | 영카트(youngcart) | 🟢 | `/shop/search.php?q=` |
| ayantu | ayantu.co.kr | imweb(SPA) | 🔴 | JS 렌더링 → 헤드리스 필요 |
| gimisa | gimisa.com | sixshop(JS) | 🔴 | 정적 HTML에 상품 0 → 헤드리스 |
| verde_trade | smartstore.naver.com/verde_trade | 네이버 스마트스토어 | 🔴 | 429 즉시 차단(안티봇) → 헤드리스+우회 |
| ryubeans | smartstore.naver.com/ryubeans | 네이버 스마트스토어 | 🔴 | 동일 |

🟢 정적 가능 / 🟡 정적+헤드리스/OCR 혼합 / 🔴 헤드리스 필수

---

## 2. 플랫폼별 어댑터 명세

### Cafe24 (momos, coffeelibre)
- 검색: `/{base}/product/search.html?keyword={kw}&page={n}`
- ⚠️ **상품 URL 스킨이 2가지** (실측 발견 — 어댑터가 둘 다 처리):
  - **A) slug 스킨** (momos): `/product/{slug}/{no}/category/{cat}/...` → 상품명 = slug (`생두-`/`원두-` prefix)
  - **B) detail 스킨** (coffeelibre): `/product/detail.html?product_no={no}` → 상품명 = 링크텍스트
  - **교훈**: 한 플랫폼이어도 스킨 따라 URL이 다름. 한쪽 패턴만 보면 "상품 0"으로 오판(coffeelibre가 그랬음). search()는 두 패턴 모두 스캔.
- green_only: A는 slug `생두-` prefix, B는 이름에 `생두` 포함으로 판정.
- 한글+영문 키워드 둘 다 검색(영문 slug 상품 누락 방지).
- 카테고리 목록(`list.html`)은 **JS 렌더링**이라 정적으론 일부만 보임 → 검색을 메인으로.
- **재고**: 정적 불가. 헤드리스 필요(아래 4번).
- **스펙 — 사이트마다 형식 다름**:
  - momos = **이미지**(상세 iframe/지연로딩). 헤드리스 렌더 → 스펙표(저채도 1000×~750) OCR.
  - coffeelibre = **텍스트**(라벨+영문 병기: 농장명/지역/재배고도/품종/가공방식). `cafe24.detail_text()`로 추출.
  - ⚠️ 컵노트는 '농장명' 앞 한글 토큰인데, 셀렉션/블렌드 로트는 레이아웃이 달라 결제팝업 텍스트가 잡힘 → LLM 권장(가드만 적용).
- momos 생두 카테고리 cat=180.

### Godo/NHN (micoffee, newbean, wbeans, royalcoffee)
- 검색: `/{base}/goods/goods_search.php?keyword={kw}&page={n}`
- 상세: `/goods/goods_view.php?goodsNo={id}`
- **상품명 위치(중요, 사이트마다 다름)**:
  - micoffee/newbean/royalcoffee: 검색목록의 `goods_view.php?goodsNo=NN ...>상품명</a>` (링크 텍스트)
  - **wbeans: 링크텍스트 비어있음 → `alt="상품명"` 속성에서 추출**
- royalcoffee: 검색이 느슨해 타 산지(엘살바도르 등) 혼입 → **상품명에 산지 키워드 있는 것만** 필터.
- 상품명에 `[품절]`,`[입고예정]`,`[프로모션]` 등 상태 prefix가 붙음.
- royalcoffee 스펙=이미지(상세 수십장) → OCR 필요. 단, 제목에 지역/품종/가공이 다 들어있어 제목 파싱만으로도 상당 부분 커버.

### cobeans (자체 PHP) — 가장 깔끔
- 검색: `/shop/search_result.php?search_str={kw}&page={n}`
- 상세: `/shop/detail.php?pno={32자리 HEX}`
- **상세페이지에 텍스트 표로 풀스펙**(지역/농장/고도/품종/가공/컵노트). 정규식 라벨 매칭으로 추출.
- 주의: 단순 라벨 매칭은 오탐 가능(예: "판매가"→환불정책 문구, "농장"→"방문하기" 버튼). **LLM 추출 권장**.
- "커피지도 세트" 같은 세트상품, "입고예정" 상품(스펙 미공개) 필터링 필요.

### 영카트 youngcart (sewoonggc)
- 검색: `/shop/search.php?q={kw}`
- 상세: `/shop/item.php?it_id={id}`
- 상품명: `it_id={id} ...>상품명</a>` (링크 텍스트). `[에티오피아]` prefix 형태.

### imweb (ayantu) — 헤드리스로 정복됨 (adapters/imweb.py)
- SPA. 정적 HTML에 상품 없음 → Playwright 필수. /greenbean?page=N 순회 + /?idx= 상세.

### gimisa — 알고보니 스마트스토어 (실측 2026-05)
- gimisa.com은 **브랜드 랜딩 사이트**(상품 0). "SHOP" 버튼이 **smartstore.naver.com/gimisa**로 연결.
- 즉 sixshop 크롤링 문제가 아니라 **스마트스토어 로그인 벽**(아래)과 동일 → blocked로 재분류.
- 교훈: 자체 도메인이어도 실제 판매는 스마트스토어로 funnel하는 업체가 있음 → "SHOP 링크의 최종 목적지"를 먼저 확인할 것.

### 🤝 제휴 피드 (partner feed) — 차단 업체의 정공법 (adapters/feed.py)
크롤링이 막힌 업체(스마트스토어)는 **판매자 직접 제휴**로 우회. 크롤링 대신 판매자가 데이터 제공.
- **방식**: 판매자가 구글시트 관리 → **서비스 계정**(로봇 이메일)에 view 공유 → Burlap 자동 구독.
  - 시트는 비공개 유지(선택적 공유 그대로). view-only라 우리가 수정 불가. 키 JSON은 백엔드 시크릿.
  - **수동 업로드 X** — 판매자가 시트 수정하면 다음 동기화에 자동 반영.
- **데이터 양식**: `config/partner_feed_template.csv` (상품명/국가/지역/농장/생산자/고도/품종/가공/등급/컵노트/가격/재고/상품링크) → 판매자에게 그대로 전달.
- **config**: `{ platform:"partner", source:"gsheet", sheet_id:"...", status:"active", partner_badge:true }`. (제휴 전엔 status:"partner_pending")
- **장점**: 재고/가격이 **판매자 검증 = 정확**(크롤링 best-effort보다 우위). 앱에 "공식 제휴 ✓" 배지 + 바로가기(트래픽 환원).
- **첫 제휴 후보**: gimisa (스마트스토어 차단 → 제휴로 전환). 표준 GreenBean이라 크롤링 업체와 동일 합류.

### 🔴 네이버 스마트스토어 (verde_trade, ryubeans) — 자동 크롤링 차단 확인 (2026-05 실측)
- 직접요청 429 / 헤드리스·스텔스·**실제 표시 브라우저**·영속세션 **전부 로그인 페이지로 리다이렉트**.
- 네이버가 자동화 세션을 강하게 감지(navigator.webdriver 외 CDP 지문 등). 데스크탑·모바일 동일.
- **현실 옵션**(전부 트레이드오프): ① 로그인 세션 쿠키 재사용(약관위반·만료·불안정) ② 네이버쇼핑 검색 경유 ③ 상용 스크래핑 API(proxy+CAPTCHA, 비용) ④ 판매자 협조 ⑤ **보류**.
- **권장**: MVP 보류. 12곳 중 2곳뿐이고 유일하게 로그인 벽 → ROI 낮음. 필요 시 Phase 3 "로그인 세션 전용 모듈"로 별도.

---

## 3. 검색·페이지네이션 규칙

- 키워드는 **["에티오피아","ethiopia"]** 처럼 한글+영문 모두 순회.
- 페이지: page=1..N, 신규 0건이면 중단(단 1페이지는 예외).
- URL은 한글 포함 → `urllib.parse.quote(u, safe=":/?=&%#")` 로 인코딩.
- grep/정규식은 UTF-8 로케일 주의(쉘 grep은 한글 범위에서 깨짐 → Python으로 처리).

### ⚠️ 헤드리스(SPA)도 페이지네이션 필수 — 스크롤 ≠ 다음 페이지
실측 발견(ayantu /greenbean): 헤드리스로 스크롤만 했더니 **1페이지 9종만** 잡고 끝. 실제는 **`?page=2`에 4종 더** (총 13).
- imweb/SPA 카테고리도 **`?page=N`을 직접 순회**해야 함. 무한스크롤처럼 보여도 다음 페이지는 별도 URL.
- 정적이든 헤드리스든 **"전 페이지 순회"는 공통 철칙** (momos 검색·ayantu 카테고리 둘 다 같은 실수 반복함 → 어댑터에 page 루프 내장).
- 패턴: `for n in 1..N: goto(.../{cat}?page={n}); 신규 idx 0건이면 중단`.

### ⚠️ 검색(search) ≠ 카테고리 목록(category listing) — 교차대조 필요
실측 발견(coffeelibre 과테말라): **검색은 15 unique, 사용자가 보는 카테고리 목록은 13**.
- **검색이 더 완전**하다 → 카테고리 목록/특정 페이지엔 안 뜨는 상품도 잡음
  (예: 고가 프리미엄 게이샤 ₩106,000 Santa Ana Geisha = '가격인하' 진열에서 빠짐 → 검색에만 잡힘)
- **그러나 검색은 노이즈도 섞임** → 타 카테고리·구crop·**중복**(Agua Tibia Geisha·Entre Volcanes 각 2회) 포함
- **권장 운영**: "검색"으로 폭넓게 수집 + "카테고리 목록"으로 교차대조 →
  - 검색에만 있고 목록에 없는 것 = 별도 진열/프리미엄/페이지 밖 (정상일 수 있음)
  - 중복은 product_no(또는 이름) 기준 dedupe, 최신 crop 우선
- 정확한 재고는 어차피 헤드리스(§4)로 최종 확인.

---

## 4. 재고 판정 (헤드리스 — 검증됨)

**문제**: Cafe24(momos)는 정적 HTML에 품절 배지(`sub_sold`)·품절 버튼(`btnSubmit`)·옵션 `[품절]` 태그가
**판매중/품절 무관하게 항상 존재**. JS+CSS로 실제 표시만 토글. → 정적 판정 전부 오답.

**해법(Playwright)**: 페이지 렌더 후 **실제 화면에 보이는(offsetParent !== null)** 요소만 검사.
```js
const vis = el => el && el.offsetParent !== null;
const all = [...document.querySelectorAll('button,a,span,strong')].filter(vis);
const action = all.filter(b => /품절|구매하기|sold ?out|buy/i.test(b.innerText));
const soldout = action.some(t=>/품절|sold/i.test(t)) || all.some(e=>e.children.length===0 && e.innerText.trim()==='품절');
```
- `wait_until="networkidle"` 은 추적 스크립트 때문에 **타임아웃** → `domcontentloaded` + `wait_for_timeout(2500)` 사용.
- **검증 결과**: momos 에티오피아 생두 21종 → 판매중 12 / 품절 9. 실제 홈페이지(사용자 확인)와 정확히 일치.

---

## 5. 스펙 이미지 OCR (헤드리스 + 채도선별 + 비전 — 검증됨)

momos/royalcoffee는 스펙(국가·지역·농장·생산자·고도·수분·밀도·품종·가공·점수·입항·컵노트)이 **이미지**.

**파이프라인**:
1. Playwright로 상세페이지 렌더 + 스크롤(지연로딩 유발).
2. 모든 `<img>`의 src/naturalWidth/Height 수집.
3. **스펙표 선별 = 저채도(회색 배경)**: PIL `convert("HSV")` 의 S 채널 평균 ≈ **2.0** (사진은 훨씬 높음). 크기는 대략 1000×(660~800).
4. 주의: "주문안내" 이미지도 회색(저채도) → 크기/내용으로 추가 구분(주문안내는 한글 본문, 스펙표는 ORIGIN/REGION 라벨).
5. 선별된 이미지를 비전 모델(Claude 등)로 OCR → 정형 JSON.

**검증**: momos 12종 전부 12필드 정확 추출 성공.

---

## 6. Cupping Spoon 연동 (스키마 매핑)

크롤링 필드 → Cupping Spoon 산지 모델. "발견→구매→커핑평가" 데이터 연결.

| 크롤링 | CuppingScore |
|---|---|
| origin | originCountry |
| region | originRegion |
| lot/farm | originFarm |
| producer | originFarmer |
| altitude | originAltitude |
| varietal | originVariety |
| process | originProcess |
| cupping note | (컵노트) |

---

## 7. 권장 아키텍처 (MVP)

```
[GitHub Actions cron]  하루 N회
   ├─ 카탈로그: 정적 어댑터(Cafe24/Godo/cobeans/youngcart)  ── 빠름·쌈
   └─ 재고/가격/이미지스펙: Playwright(channel="chrome")     ── 정확·느림
        └─ 스펙 이미지 → 비전 OCR(필요시만)
        ▼
[Supabase] Postgres + REST + Auth   ── 관리형, 운영 최소
        ▲
[iOS 앱(SwiftUI)] 검색·필터·딥링크·공유 + RevenueCat 구독
```
- 헤드리스는 **설치된 Chrome 재사용**(`channel="chrome"`) → 브라우저 다운로드 불필요.
- 비용: 정적은 매일, 헤드리스는 필요한 것만(재고). 비전 OCR은 스펙 변경분만.

---

## 8. 법적/운영 주의

- 네이버 스마트스토어 약관상 자동수집 금지(회색지대). 사실정보(국가/품종/가격)만, 원본으로 트래픽 유도.
- 사이트 구조 변경 시 어댑터 깨짐 → 상시 유지보수(업체 10곳이면 월 1~2개 보수 예상).
- 수집 빈도 점잖게(3회/일 충분), rate limit/UA 설정으로 차단 완화.
- 개인정보·결제정보는 절대 수집 금지.

---

## 9. 오늘 테스트 실측 결과 (참고)

- 에티오피아 전수: 정적 8개 업체 **119종** 수집(오탐 2건 제외). 헤드리스 4곳 추가 시 150종+.
- momos 에티오피아 생두: 카탈로그 21종, **판매중 12 / 품절 9**(헤드리스), 12종 전부 풀스펙 OCR 완료.
- 콜롬비아: 4개 업체 89종(momos25·코빈즈17·로얄24·micoffee23).
