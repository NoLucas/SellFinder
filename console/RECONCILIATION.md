# RECONCILIATION — /console (에이전트 D · 의사결정 콘솔)

작성일: 2026-08-15
작성자: 에이전트 D (`/console` 담당)

---

## 1. 지금까지 내가 만든 것

`/console` 폴더에는 `.gitkeep` 외 아무 파일도 없다. 이 폴더 안에서 만든 것은 없음.

다만 저장소에는 목적이 겹치는 기존 작업이 하나 있다: `/frontend` (Next.js 앱, 지도 컴포넌트
`KoreaMap.tsx`/`RegionDetailPanel.tsx`/`CategorySelector.tsx`, 목 데이터 생성기, 자체 추측
계약 `types/prediction.ts` 포함). 이건 `/console`이 생기기 전, "지역×카테고리 추천 대시보드"라는
구 가정 하에 다른 에이전트가 만든 것으로 보이며, `shared/contracts/README.md`의 폴더 소유권
표에는 `/frontend`가 아예 없다 — 즉 이번 재정렬의 소유권 밖이다. `/console` 담당으로서 이 폴더를
읽거나 옮기지 않았고, 앞으로도 지시 없이는 손대지 않는다. (아래 §6 참고)

## 2. 계약과 일치하는 것 → 유지

해당 없음 (`/console` 안에 코드 없음).

## 3. 계약과 어긋나는 것 → 리팩터링 방향

해당 없음. 참고로 `/frontend`(소유권 밖)는 신제품 계약과 근본적으로 어긋난다:
지역×카테고리 단위 vs. 신계약의 (제품×지역×채널×기간) 단위, 테넌트/SKU/objective/Tier 개념
전무, `expected_revenue_krw` T0 null 규칙 없음, 요인 분해(factors) 없음.

## 4. 계약에 없어서 버려야 하는 것

- **`/frontend` 폴더 전체 폐기 (2026-08-15 추가 결정, jin 승인).** §6에 남겨뒀던 미결 사항 —
  "폐기할지, 재사용 가능한 부분만 포팅할지" — 에 대해 jin이 "필요없는 기존코드 전면 폐기"로
  답해, 재사용 검토 없이 폴더 전체(트래킹 28개 파일 + `node_modules`/`.next` 등 미트래킹 산출물)를
  삭제했다. §3에서 정리한 대로 신계약과 근본 모델이 달라(지역×카테고리 단위 vs.
  제품×지역×채널×기간, 테넌트/SKU/Tier 개념 부재) 부분 포팅도 실익이 적다고 판단.

## 5. 계약에 있는데 아직 없는 것 → 착수 순서

브리프의 "핵심 화면 4개"를 다음 순서로 진행 예정:

1. **타입/클라이언트 레이어** — `04_api_contract.yaml`에서 타입을 생성(손으로 안 씀).
   `/backend`가 아직 실제 엔드포인트를 준비하지 못했다면 계약의 example 응답을 목 데이터로 사용.
2. **지도 뷰** — ~~벡터타일(`/predictions/{run_id}/tiles/{z}/{x}/{y}.mvt`) 기반~~ **구현 완료
   (2026-08-15, 아래 참고).** `GET /basemap/regions/manifest` + `GET /predictions/{run_id}/scores`
   조합으로 재구현. 상단 제품(SKU)·채널·objective 선택 컨트롤은 아직 없음(다음 착수 항목).
3. **지역 상세 패널** — `/predictions/{run_id}/regions/{region_id}` 응답 기반. p10/p50/p90 구간,
   요인 분해 waterfall, evidence 문장 그대로 노출, 유사 지역 비교, 잠식(cannibalization) 경고,
   risks, data_freshness.
4. **Tier별 정직성 규칙 공통 컴포넌트** — `expected_revenue_krw === null`(T0)일 때 금액 자리 대신
   "자사 판매 데이터를 업로드하면 매출 추정을 제공합니다" 안내 + 상대 랭킹만 표시. T0/T1/T2별
   문구 분기, 구간이 p50 대비 ±60% 초과 시 금액 흐림 처리 — 이건 여러 화면에서 재사용되므로
   개별 화면보다 먼저 공통 로직으로 뺀다.
5. **시나리오 시뮬레이터** — `/scenarios`, `/scenarios/{id}:compare`. 기준 예측과 나란히 비교.
6. **관리자** — 제품 등록(+ `/products:classify` 미리보기, `needs_review` 처리 UI), 데이터 업로드
   + 컬럼 매핑(`/datasets/sales:import`), 사용자/권한.
7. **내보내기** — `/exports` 비동기 트리거 + 완료 후 다운로드 링크.
8. **색상 시스템** — 점수는 순차형, 요인 기여도는 발산형 팔레트로 화면 전체 통일.

## 6. 다른 에이전트/사람(jin)에게 확인이 필요한 사항

- ~~`/frontend`를 어떻게 할지~~ → **해결.** jin이 전면 폐기를 지시해 §4에 기록한 대로 삭제 완료.
- **`/backend` 진행 상태** — 브리프상 "C가 아직 준비 안 됐으면 mock을 먼저 만들어 D가 시작할 수
  있게 하라"고 되어 있다. 방금 확인한 MEMORY 갱신 로그에 `scope_backend_role.md`가 새로 생긴 걸
  보면 에이전트 C도 이번 재정렬로 막 착수한 것 같다 — 실제 엔드포인트가 아직이면 `04_api_contract.yaml`의
  example을 목으로 쓰고 시작하겠다. mock/실제 전환 시점을 알려주면 반영한다.
- **인증/토큰 발급 방식** — `tenant_id`가 토큰에서만 파생된다는 규칙은 명확하지만, `/console`이
  로그인/토큰 발급을 어떻게 받는지(자체 구현 vs `/backend` 제공 엔드포인트)는 `04_api_contract.yaml`에
  명시가 없어 `/backend` 담당에게 확인이 필요하다.
- ~~벡터타일 서버 소스~~ → **해결(ADR-001, 2026-08-15).** A/C/D 세 곳이 독립적으로 같은 질문을
  제기해 jin이 `shared/contracts/ADR-001-map-tiles.md`로 확정: 경계 지오메트리(A 생성, PMTiles
  아티팩트)와 예측 점수(C 서빙, 경량 JSON)를 분리하고 클라이언트(D)에서 `setFeatureState`로
  조인한다. `04_api_contract.yaml` v0.2.1에 `GET /basemap/regions/manifest` +
  `GET /predictions/{run_id}/scores` 신설, 기존 `.mvt` 타일 엔드포인트는 폐기. §7에 이번 지도 뷰
  구현 세부와 미해결 사항을 기록.

## 7. 지도 뷰 구현 기록 (2026-08-15, ADR-001 반영)

`console/src/components/PredictionMap.tsx` + `lib/api/client.ts` + `lib/color/scoreScale.ts` +
`lib/map/hatchPattern.ts`로 구현. 흐름: `GET /predictions/{run_id}/scores`로 `region_level` /
`boundary_vintage` / `score_range` 확보 → `GET /basemap/regions/manifest`(같은 level·vintage로
조회, "최신" 금지)로 PMTiles URL·`source_layer`·`feature_id_property` 확보 → `pmtiles://` 프로토콜로
벡터 소스 등록 → 점수 배열을 `setFeatureState`로 조인 → `fill-color`는 `score_range` 고정 도메인의
순차형(sequential blue, dataviz 스킬 `references/palette.md`) 표현식 → `confidence_level='low'`는
별도 해칭 레이어(`fill-opacity`를 feature-state로 온오프, **`filter`가 아니라 `paint`** — MapLibre가
feature-state를 filter에서는 지원하지 않아서). 지역 상세는 클릭 시에만 `/predictions/{run_id}/regions/
{region_id}` 조회. `region_level='custom_catchment'`인 경우 `custom_geometries` GeoJSON을 벡터 소스
대신 직접 사용하는 분기도 넣어뒀다(테스트는 안 해봄 — 지금 mock 데이터엔 이 케이스가 없음).

`next build` 정상 통과 확인. 실제 backend 응답으로는 아직 검증 못했다 — 아래 미해결 사항 참고.

**중요 — 계약과 backend 실제 구현이 다르다 (2026-08-15 발견, jin이 계약 기준으로 진행 지시):**
`backend/CONTRACT_CHANGE_REQUEST.md`에 "jin의 직접 지시로" 구현했다고 적힌 내용이 병합된
`ADR-001`/`04_api_contract.yaml` v0.2.1과 다르다.
- 계약: `/basemap/regions/manifest`가 `level`/`vintage` 쿼리로 **PMTiles** 1개 반환
  (`tile_url`이 `.pmtiles`, `source_layer`/`feature_id_property`/`minzoom`/`maxzoom` 포함).
  backend 실제: 쿼리 파라미터 없이 **레벨별 GeoJSON URL 목록**(`{level, format, url}[]`)을 한 번에
  반환. PMTiles 관련 필드 전혀 없음.
- 계약: 지도 전용 `GET /predictions/{run_id}/scores`(튜플 배열 + `score_range`), `/regions`와 별도.
  backend 실제: 이 엔드포인트 자체가 없음. 기존 `/predictions/{run_id}/regions`(커서 페이지네이션,
  금액 포함)에 `boundary_vintage`만 얹어서 재사용.

이 구현은 jin이 이번 세션에서 "ADR-001 계약 기준(PMTiles)"으로 진행하라고 확정해줘서 계약 그대로
만들었다. **단, backend가 이 계약대로 아직 안 만들었으므로 실제 backend에 붙여서 통합 테스트는
못 했다** — 계약 예시 데이터 모양으로만 타입/빌드 검증함. backend(C) 세션이 ADR-001에 맞춰
`/scores` + PMTiles manifest를 구현하거나, 반대로 jin이 계약을 backend의 GeoJSON 방식으로
갱신하기 전까지는 이 상태가 유지된다 — 둘 중 하나로 수렴시켜 달라고 jin에게 요청.

---

`/console` 자체는 삭제할 코드가 없었고, jin의 전면 폐기 지시에 따라 `/frontend`만 삭제했다.
`/data-platform`·`/intelligence`·`/backend` 소유 폴더의 레거시 코드(구 `/model`,
`/data-pipeline`, 구 `shared/contracts` 파일 등)는 이 세션의 권한 밖이라 손대지 않았다.

---

## 8. DISPATCH.md §4 D-2~D-4 (2026-08-16)

**D-2 — 테스트 러너.** Node 24 내장 `node --test` 사용 (`.ts` 네이티브 type-strip 확인 후 채택 —
`scoreScale.ts`를 리임플리먼트하지 않고 실제 프로덕션 모듈을 그대로 import). 첫 버전은 합성
타일 픽스처와 `verification/fixtures/a_tile_features.json`(A의 수정 전 스냅샷)에 기대 두고
있었는데, 총괄자 2차 지시로 **실제 통합 경로**(`data-platform/fixtures/regions-sigungu-fixture.pmtiles`
+ `manifest-fixture.json`)를 직접 읽도록 다시 짰다. `pmtiles` + `@mapbox/vector-tile` + `pbf`로
`.pmtiles`를 실제로 디코드한다 — 셋 다 이미 `maplibre-gl`의 전이 의존성으로 설치돼 있던 걸 확인하고
`@mapbox/vector-tile`/`pbf`만 정확한 설치 버전(1.3.1 / 3.3.0)으로 devDependencies에 명시 고정했다
(호이스팅에 기대지 않기 위해 — `pmtiles`는 이미 직접 의존성이었다).

`console/tests/join.test.mjs` 3개 테스트: (1) 실제 샘플 → `setFeatureState` 키 생성,
(2) **A의 실제 커밋된 `.pmtiles`를 디코드해 C의 실제 `scores.json`과 끝까지 조인** — 매칭 건수를
`scores.scores.length`와 정확히 단언(현재 5/5, 실제 회귀 가드: 조인 키가 되돌려지거나 타일에서
`region_id`가 빠지면 즉시 실패), (3) `scoreScale.ts`의 fill expression이 실제 `score_range`를
쓰는지. `resolveManifest()`가 "한 곳에서 주입" 지점이다 — `backend/samples/manifest.json`이
이 run의 level/vintage와 맞으면 그걸 쓰고, 아니면(지금처럼 `adm_dong`/`2026-01-01`로 어긋나 있으면)
`data-platform/fixtures/manifest-fixture.json`로 자동 폴백한다. **C가 매니페스트를 고치면 이
함수가 코드 변경 없이 자동으로 갈아탄다.** `tile_url`도 하드코딩하지 않고 매니페스트 값의
basename으로 `data-platform/fixtures/`·`output/tiles/`에서 로컬 파일을 찾는다.
`npm test`로 실행, 실행 결과는 총괄자 보고에 첨부.

**참고 — `verification/fixtures/a_tile_features.json`은 더 안 쓴다.** 이 세션이 처음 D-2를 만들
때는 그 파일(A의 구 sido 파이프라인 스냅샷)로 "여전히 0/5"를 못박는 테스트를 넣었는데, 이후
검증팀이 그 파일을 sigungu·`region_id` 포함 버전으로 갱신하면서(A가 실제로 고쳤다는 뜻) 그 assert가
저절로 깨졌다 — 트립와이어가 정상 작동한 것. 총괄자 2차 지시로 그 테스트 자리를 진짜 `.pmtiles`
디코드로 교체했으므로 더는 그 파일에 기대지 않는다.

**D-3 — 레벨 선택 UI.** 계약(`04_api_contract.yaml` v0.2.2)엔 `/predictions/{run_id}/scores`에
`level` 쿼리 파라미터가 없다 — `region_level`은 run 생성 시 고정되고 응답이 그걸 알려줄 뿐이다.
그래서 "레벨 선택"을 이 run의 점수를 다른 레벨로 다시 조회하는 기능으로 만들 수는 없었다(계약에
없는 걸 지어내는 것 — D-10 위반). 대신 **베이스맵(경계 타일) 자체를 사용자가 시도/시군구/행정동
중 골라 바꿔 보는 기능**으로 구현했다(`PredictionMap.tsx`의 `LevelPicker`) — `/basemap/regions/
manifest?level=...`은 계약상 세 값 모두 받으므로 이건 실제 계약 범위 안이다. run 자신의 레벨이
아닌 걸 고르면 점수 조인은 그대로 시도되지만 `region_id`가 안 맞아 전부 `NO_DATA_FILL`로 칠해진다
— `scoreFillExpression`의 기존 null-guard가 이미 하는 일이라 별도 분기를 안 넣었다. 줌 이벤트로
레벨을 바꾸는 코드는 어디에도 없다(D-14). **불확실해서 임의로 결정한 지점 — jin 확인 필요:**
"레벨 선택"이 이 의미가 맞는지, 아니면 향후 run 생성 UI(§5-2 예정 항목)에서 `region_level`을
고르는 걸 말한 건지 확실하지 않다. 계약이 후자를 뒷받침하지 않아 전자로 진행했다.

**D-4 — 토큰을 `localStorage`에 넣지 않기.** 확인 결과 애초에 어디에도 저장하지 않고 있었다
(`page.tsx`의 `useState`뿐, 새로고침하면 날아간다) — `grep -rn "localStorage\|sessionStorage"
console/src/` 0건. 규칙은 이미 지켜지고 있어서 코드 변경은 회귀 방지 주석 하나만 추가했다.
httpOnly 쿠키 기반의 실제 영속 로그인은 `/backend`의 로그인/`dev-token` 엔드포인트가 나와야
붙일 수 있다 — 그 전까지는 지금 상태(비영속 입력창)가 맞다고 보고 진행했다.

**확인 명령 (총괄자 보고에 그대로 첨부):**
```
npm test         # D-2 — 4 tests, 4 pass
npm run typecheck # tsc --noEmit, exit 0
npm run build     # next build, 정상 완료
```

---

## 9. DISPATCH-2.md §6 D-1~D-4 (2026-08-16, 2차 사이클)

C-2(잡 워커가 B의 `predict_batch` 호출)가 아직 안 들어와서 `GET /predictions/{run_id}/regions/
{region_id}`는 backend에 라우트 자체가 없다(`grep -n '"/predictions' backend/app/routers/
predictions.py`로 확인 — `/regions`·`/scores` 두 개뿐). 그래서 D-1은 그 사실을 그대로 반영해서
짰다: 지금은 항상 실패하는 진짜 호출 뒤에 스캐폴드가 자동으로 받쳐 준다.

**D-1 — 지역 상세 패널, 요인 8개 분해.**
- `src/lib/api/sampleDetail.ts` — `05_scoring_spec.md` §1의 8개 `factor_key` 그대로, §6의
  evidence 규칙(실제 값 인용 + 비교 기준, 인과 주장 금지)을 지켜 쓴 **하나짜리 고정 픽스처**.
  런타임에 값을 지어내지 않는다 — 클릭한 region_id/run_id만 채워 넣고 나머지는 고정.
- `src/lib/api/regionDetail.ts`의 `resolveRegionDetail()`이 "한 곳에서 주입" 지점이다.
  진짜 `GET .../regions/{region_id}`를 먼저 시도하고, 실패하면(지금은 항상 실패 — 라우트가
  없으니까) 픽스처로 폴백한다. **C-2가 라우트를 만들면 이 함수가 코드 변경 없이 자동으로
  진짜 데이터를 쓰기 시작한다.** `PredictionMap.tsx`는 이 함수만 호출하고 `sampleDetail.ts`를
  직접 import하지 않는다.
- `RegionDetailPanel.tsx`는 `factors` 배열을 있는 그대로 렌더한다(라벨·값·evidence 추가 가공
  없음). `isSample` 플래그가 true면 노란 배너로 "예시 데이터입니다 — 실제 예측이 아닙니다"를
  화면에 그대로 노출한다 — 코드에서만 정직한 게 아니라 화면에서도 정직해야 한다는 원칙.
  **주의**: 이 배너는 C-2 이후에도, 만약 그 진짜 호출이 (라우트 부재가 아닌) 다른 이유로
  실패하면 계속 뜬다 — 의도한 동작이다. 조용히 가짜를 진짜처럼 보여주는 것보다 낫다.

**D-2 — T0 문구를 테스트로 강제.**
- `RevenueBlock`의 인라인 로직을 `src/lib/format/revenue.ts`의 순수 함수
  `formatRevenueDisplay()`로 뽑아냈다 — node:test가 React 렌더 없이 직접 단언할 수 있게.
- `tests/revenue-display.test.mjs`: `expected_revenue_krw === null`이면 반드시
  `kind: "unavailable"` 분기를 타고, 메시지가 계약 문구 "상대적 유망도 랭킹"을 포함하며,
  `"0"`이나 `"-"`가 아님을 단언한다. 값이 있는 경우엔 반대로 숫자 분기를 타는지도 같이 확인.

**D-3 — confidence=low가 색이 아니라 패턴인지 회귀 테스트.**
- `tests/confidence-hatch.test.mjs`가 실제 `scoreScale.ts`/`hatchPattern.ts` 모듈이 만드는
  MapLibre 표현식 트리를 직접 검사한다: `fill-color` 표현식에 `confidence_level`이 전혀
  등장하지 않고, 해칭 `fill-opacity` 표현식은 `confidence_level === 'low'`에만 반응하며
  `score`를 전혀 참조하지 않는다. 누가 "낮은 신뢰도는 색을 옅게" 식으로 고치면 이 테스트가
  바로 깨진다.

**D-4 — 매직링크 로그인 + region_scope 반영.**
- backend에 매직링크 발송/검증 엔드포인트가 없다(DISPATCH-2 C-1~C-5 범위 밖). 그래서
  `LoginPanel.tsx`의 이메일+매직링크 UI는 **비활성 버튼으로 존재만 하고, 안 보내는 이메일을
  보낸 척하지 않는다** — 툴팁/안내 문구로 "backend 미구현"을 명시. 실제로 동작하는 경로는
  ADR-003 "개발 중 임시 조치"인 `POST /v1/dev/token`(`backend/app/routers/dev_auth.py`,
  `SELLFINDER_ENV=development`에서만 등록) — 이걸로 tenant_id·role·region_scope를 실제로
  발급받는다. `client.ts`에 `requestDevToken()` 추가(인증 전 호출이라 `postJSONUnauthenticated`
  헬퍼를 새로 뺐다).
- `region_scope` 반영: 로그인 폼에서 사용자가 입력한 `region_scope`를 세션 상태에 그대로
  들고 있다가 헤더에 "범위: 41, 11" 또는 "전체 지역"으로 표시한다. 토큰을 클라이언트에서
  디코드해서 얻지 않는다 — ADR-003 §3 "애플리케이션 코드는 TokenClaims만 본다, 토큰 원문을
  다른 곳에서 파싱하지 마라"는 서버 얘기지만 같은 정신을 클라이언트에도 적용했다: 콘솔이
  `/v1/dev/token`에 보낸 요청 바디 값을 그대로 세션에 echo하는 것이지, 토큰을 열어보는 게
  아니다. 실제 서버 측 `region_scope` 강제(조회·타일·내보내기 전 경로)는 C 담당이고 D는
  이 세션 밖 범위다.
- **`tests/token-hygiene.test.mjs`**를 새로 추가해서 D-4를 테스트로도 강제했다(DISPATCH-2가
  명시적으로 요구하진 않았지만 D-2/D-3 패턴과 맞춰 일관되게). `console/src` 전체를 정적
  스캔해서 `localStorage.`/`sessionStorage.` 실사용이 0건인지 확인 — 주석에 그 단어가 나와도
  오탐하지 않도록 정규식을 property-access 형태로 제한했다(처음엔 문장부호 `.` 때문에 두 번
  오탐 났다가 고쳤다).

**실행 결과 (그대로 첨부):**
```
npm test          # 9 tests, 9 pass (D-2 조인 3 + fill-color/hatch 3 + T0 문구 2 + 토큰 위생 1)
npm run typecheck # tsc --noEmit, exit 0
npm run build     # next build, 정상 완료 (222 kB)
```

**jin 확인 필요 — 확신 없이 임의로 결정한 지점:**
1. §8에 이미 적은 "레벨 선택" 해석 문제, 아직 미해결.
2. D-1의 `isSample` 배너 — C-2 이후 진짜 호출이 실패했을 때도 계속 뜨는 설계가 맞는지.
   (개인적으로는 "조용히 가짜를 보여주는 것"보다 안전하다고 보고 이대로 진행했다.)

다음 지시 대기.
