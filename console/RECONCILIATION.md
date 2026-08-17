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

---

## 10. 총괄자 지시 4차 — "골격에 진짜를 흘려보내라" 실제 검증 결과 (2026-08-16)

**결론부터: 세 가지 확인 항목 중 어느 것도 화면까지 온전히 갈 수 없었다.** 골격(D-1~D-4)은
맞게 짰지만, 예상보다 이른 지점에서 세 개의 독립적인 이음매 결함에 부딪혔다. 추측으로
파서를 맞추지 않고, 실제로 backend 서버를 띄우고(`uvicorn`, `localhost:8000`) 실제
`POST /v1/predictions`로 run을 만들고, 실제 HTTP 응답을 콘솔의 **진짜 프로덕션 코드**
(`resolveRegionDetail`, `formatRevenueDisplay`, `client.ts` — 재구현 아님, `tsc`로 그대로
컴파일해 돌렸다)로 직접 통과시켜 확인했다. 브라우저로도 시도했다.

### 발견 1 (신규, 가장 심각) — backend에 CORS 설정이 전혀 없다

`grep -rn "CORS\|cors" backend/app/*.py` → 0건. 실제 브라우저(`localhost:3000` → 콘솔
개발서버, `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000/v1`)에서 로그인 폼으로
`POST /v1/dev/token`을 호출하니 **"Failed to fetch"** — 브라우저의 CORS 차단이다.
같은 요청을 `curl`과 Node의 `fetch`(CORS를 안 지키는 환경)로 하면 정상 응답한다 —
서버는 멀쩡히 살아있고 응답도 맞다, **브라우저만 막힌다.**

- 개발 환경(`:3000` ↔ `:8000`)도, 운영 환경(콘솔 도메인 ↔ `api.sellfinder.kr`)도 **오리진이
  다르므로 항상 걸린다.** 지금 이 상태로는 콘솔이 브라우저에서 backend를 단 하나도 호출하지
  못한다 — 로그인은 물론 지도·상세 패널 전부.
- 콘솔 쪽에서 우회(프록시 rewrite 등)로 해결하지 않았다. 실제 배포에서도 콘솔·API가 다른
  도메인인 이상 프록시로 덮으면 운영 이슈를 개발 환경에서만 숨기는 꼴이라 판단했다.
- **backend(C)가 `CORSMiddleware`를 등록해야 하는 문제다.** `console/` 밖이라 내가 고치지
  않았다. 1차·2차 사이클 내내 아무도 브라우저로 실제 통합을 띄워본 적이 없어서 지금까지
  아무도 못 잡은 것으로 보인다 — 스크립트/curl 기반 검증은 이 문제를 절대 못 잡는다
  (CORS는 브라우저만 강제한다).

### 발견 2 — 요인 8개 분해가 화면까지 갈 경로가 아직 없다 (D-1 관련)

`grep -n '"/predictions' backend/app/routers/predictions.py` → `/regions`(목록)·`/scores`
둘뿐, **`GET /v1/predictions/{run_id}/regions/{region_id}` 단건 상세 라우트 자체가 없다.**
실제로 쳐봤다: `curl .../regions/91001001` → `404 {"detail":"Not Found"}` (FastAPI 기본
404, 계약이 정한 에러 봉투 형태가 아니다 — `client.ts`가 이걸 `res.statusText`로 우아하게
받아넘기는 것까지 확인했다).

- 목록(`/regions`) 응답의 `RegionScoreItem`에도 `factors` 필드가 없다(`backend/app/
  schemas.py`에 factors/evidence 관련 클래스 자체가 없음).
- 하지만 **B의 실제 모델은 요인 8개를 만들고 있다.** `intelligence/scoring/model.py`의
  `PredictionResult.factors`가 그것이다. C의 `job_runner.py`→`prediction_store.compute_
  regions()`가 `result.factors`를 **아예 읽지 않고 버린다** — `RegionScore` dataclass에
  `factors` 필드가 없다. B→C 경계에서 데이터가 만들어지자마자 사라진다.
- 결과: 지금 콘솔에서 어떤 지역을 클릭해도 `resolveRegionDetail()`은 항상 404를 만나
  **항상 `sampleDetail.ts` 픽스처로 폴백한다.** 설계한 그대로(`isSample: true` + 배너)
  동작하는 것은 확인했지만, **요인 8개가 실제 모델 출력으로 렌더되는 걸 오늘은 확인할 수
  없다** — 화면까지 가는 경로가 아예 없어서다. C-2 다음 단계로 "단건 상세 라우트 + B의
  factors를 실제로 실어 나르는 것"이 필요하다.

### 발견 3 — T0 실제 응답 확인 불가 (D-2 관련) · 구조적으로 T0를 만들 방법이 없다

`backend/app/schemas.py`의 `PredictionRequest`에 `data_tier` 필드 자체가 없고,
`routers/predictions.py`의 `create_prediction()`은 주석으로도 명시했듯
**"매 run이 T1로 고정 생성된다."** 실제로 run 세 개를 만들어 봤는데 전부 `data_tier: "T1"`
이었다. **T0 테넌트로 같은 경로를 타보라는 지시를 오늘은 이행할 방법이 없다** — API가 T0를
요청할 방법 자체를 안 준다. 추측해서 T0인 척 만들지 않았다.

대신 확인한 것: 실제 T1 run의 `expected_revenue_krw`도 어차피 전부 `null`이었다
(B의 5단계 매출 모델이 아직 없어서 — `intelligence_client.py` 주석 "always None today").
그 실제 null 값을 콘솔의 진짜 `formatRevenueDisplay()`에 통과시키니 계약 문구
`"자사 판매 데이터를 업로드하면... 상대적 유망도 랭킹만 참고하세요"`가 정확히 나왔다 —
**tier와 무관하게 null이면 항상 정직한 문구를 낸다는 설계는 실동작으로 확인됐다.**
`confidence.level`도 실제로는 전 지역이 `"low"`로 고정돼 있었다(C가 아직 신뢰도 산식을
구현 안 해서 — `prediction_store.py` 주석 "no real signal to report... never fabricate").
**`"high"` 배지가 뜨는지 확인해 달라는 항목도 오늘은 관측 불가** — `"low"` 밖에 안 나온다.
다만 `_confidence_for_tier()`의 T0 상한 로직 자체는 코드 리뷰로 맞게 짜여 있는 걸 확인했다
(`_CONFIDENCE_ORDER["low"] > _CONFIDENCE_ORDER["medium"]`이 거짓이라 강등이 안 걸릴 뿐).

### 발견 4 — evidence 문장은 B 쪽에서는 규칙을 지키고 있다 (화면 확인은 아직 불가)

라우트가 없어 화면으로는 못 봤지만, `intelligence_client.run_prediction()`을 직접 호출해
B의 실제 evidence 문자열을 읽었다:
```
addressable_demand: "타깃 인구 규모 562,349명 - 비교대상 지역 평균 562,349명 대비 1.00배"
category_penetration: "해당 지역·채널의 소비 신호 데이터 없음(또는 suppressed) - 중립(1.0)으로 처리"
price_acceptance: "소득 6분위 (비교지역 평균 6.0분위), 가격대 'mid'"
```
- 값 인용(§6.1)·비교 기준 동반(§6.2) — 지켜지고 있다.
- 인과 단정(§6.3 금지) — 안 보인다. 데이터가 없는 요인은 "데이터 없음 - 중립 처리"로
  정직하게 적고 있다(지어내지 않음).
- **다만 이 run(adm_dong 91001001)은 8개 요인 전부 `log_contribution=0.0000`,
  `total_multiplier=1.0`이었다** — 완전 중립. `addressable_demand`의 "비교대상 지역 평균
  대비 1.00배"도 자기 자신과만 비교되는 것처럼 보이는 결과다. 이게 이 지역의 실제
  피처가 그런 것인지, 비교집단 표본이 너무 작아서(합성 데이터셋이 5개 지역뿐) 생기는
  퇴화(degenerate) 현상인지는 B가 확인할 문제라 여기서 판단하지 않고 사실만 남긴다.
- **§6 규칙이 화면에서 깨지는지는 여전히 확인 불가** — 발견 2 때문에 문장이 아직 화면에
  안 온다. B가 언급한 "§6 테스트 붙이는 중"과는 별개로, 콘솔 쪽 검증은 라우트가 생겨야
  재개할 수 있다.

### 검증 방법 (재현 가능)

```
# 1) backend 실행 (dev)
cd backend && ./.venv/Scripts/python -m uvicorn app.main:app --port 8000

# 2) 토큰 발급 + run 생성 + 목록 조회 (실제 응답 그대로)
curl -X POST http://127.0.0.1:8000/v1/dev/token -H "Content-Type: application/json" \
  -d '{"tenant_id":"tnt_verify","role":"analyst","region_scope":[]}'
curl -X POST http://127.0.0.1:8000/v1/predictions -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"product_ids":["prd_demo"],"objective":"distribution_push","region_level":"adm_dong"}'
curl http://127.0.0.1:8000/v1/predictions/<run_id>/regions -H "Authorization: Bearer <token>"
curl -i http://127.0.0.1:8000/v1/predictions/<run_id>/regions/<region_id> -H "Authorization: Bearer <token>"  # 404 확인

# 3) 콘솔의 진짜 코드(재구현 아님)를 그 응답에 직접 통과 — tsc로 컴파일해 node로 실행
#    (parameter-property를 쓰는 client.ts의 ApiError 클래스가 Node 네이티브 TS 스트리핑
#    지원 범위 밖이라 tsc 컴파일이 필요했다. 상세 명령은 이 세션에만 있던 임시 스크립트라
#    재현하려면 tsc -p tsconfig.json --outDir <tmp> 후 결과 .js를 node로 실행)

# 4) 브라우저 재현 (CORS 확인)
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000/v1 npm run dev
# localhost:3000 접속 → 로그인 폼 제출 → "Failed to fetch"
```

### jin·C·B 확인 필요 (즉시 보고 대상, 추정 아님)

1. **CORS 미설정 (backend, S1급)** — 지금 상태로 콘솔은 브라우저에서 backend를 전혀 호출
   못한다. `CORSMiddleware`를 backend에 등록해야 한다. console/에서 고칠 수 있는 범위 밖.
2. **B의 `factors`가 C의 `prediction_store.RegionScore`에서 버려짐 + 단건 상세 라우트 부재**
   — D-1이 실제 데이터로 검증되려면 이 둘이 먼저 있어야 한다.
3. **T0 run을 만들 방법이 API에 없음** — `PredictionRequest`에 `data_tier` 관련 필드가 없다.
   D-2/D-3의 T0·confidence 상한 검증은 그때까지 코드 리뷰 수준에 머무른다.
4. (참고, 판단 보류) B의 evidence가 이 particular run에서 전부 중립(1.0)이었던 것 —
   버그인지 데이터셋이 작아서인지 B가 확인 바람.

**요인 8개 렌더·T0 실제 응답·evidence 화면 검증 세 가지 다 오늘은 "골격은 맞고 정직하게
동작하지만, 아직 진짜 값이 화면까지 도달할 길이 없다"로 결론 낸다. 추측으로 통과 처리하지
않았다.**

---

## 11. 총괄자 지시 5차 — CI 확인 + region_scope (2026-08-17)

### CI (`2791644`) 확인 결과 — 문제 하나 찾아서 고쳤다

1. **`package-lock.json` 추적 확인** — `git ls-files console/package-lock.json` 정상 출력.
   `npm ci` 는 문제없이 동작한다(클린 재설치로 직접 재현: `rm -rf node_modules && npm ci`).
2. **테스트 글롭 패턴 확인 — 여기서 진짜 문제를 찾았다.** `package.json`의
   `"test": "node --test tests/**/*.test.mjs"`를 `sh -c 'echo tests/**/*.test.mjs'`로
   재현했더니 **셸이 전혀 확장하지 못하고 리터럴 문자열 그대로 넘어갔다** (`**`는 POSIX
   `sh`가 지원하는 글롭이 아니다 — `bash`의 `globstar` 옵션 없이는 `**`가 재귀 매칭이 안
   된다). 다행히 Node 자체의 `--test`가 인자를 받아 자체 글롭 매칭을 하는 걸 확인해서(로컬
   에선 두 패턴 다 9/9 통과) 오늘 당장 깨지진 않았지만, **셸/Node 버전에 따라 달라지는
   동작에 기대는 건 위험하다** — CI 실패가 gh runner 의 정확한 셸·Node 조합에 좌우되는
   재현 불가능한 버그가 될 수 있다. **모든 테스트가 `tests/` 바로 아래 평평하게 있어서
   재귀가 애초에 필요 없으므로**, `tests/*.test.mjs`(단일 `*`, 모든 POSIX 셸이 지원)로
   바꿨다. `package.json`.
3. **더 심각한 걸 확인 과정에서 찾았다 — CI 의 Node 버전과 내 테스트의 실제 요구사항이
   맞지 않는다.** `.github/workflows/ci.yml:87`(console 잡)이 `node-version: '20'`을 쓴다.
   내 조인/해칭/T0 테스트(`join.test.mjs`, `confidence-hatch.test.mjs`,
   `revenue-display.test.mjs`, `region-scope.test.mjs`)는 전부 `../src/lib/.../*.ts`를
   **Node 의 네이티브 TypeScript 스트리핑**으로 직접 import 한다 — 이 기능은 Node 22.6에서
   플래그로, **23.6부터 기본 활성화**됐다(D-2 세션 때 이걸 발견하고 새 devDependency 없이
   테스트 러너를 짤 수 있었던 이유이기도 하다). **Node 20 은 이 기능이 아예 없다.** `.ts`
   확장자를 인식하는 로더 자체가 없어서 import 시점에 즉시 실패할 것으로 강하게 예상된다
   (Docker 가 이 환경에 없어서 Node 20 으로 직접 재현은 못 했다 — 이 부분은 코드 리뷰 수준의
   확신이지 실행 확인이 아니다, jin/총괄자가 실제 CI 로그로 확인해 주길 요청).
   - **`.github/workflows/ci.yml`은 `console/` 밖이라 내가 고치지 않았다.** 대신
     `console/package.json`에 `"engines": {"node": ">=23.6.0"}`를 추가하고
     `console/.npmrc`에 `engine-strict=true`를 추가했다 — 이러면 Node 20 에서
     `npm ci` 단계 자체가 **바로, 명확한 이유로** 실패한다("Unsupported engine"),
     지금처럼 `npm test` 안쪽 깊은 곳에서 알 수 없는 import 에러로 실패하는 것보다 훨씬
     디버깅하기 쉽다. **근본 해결은 `ci.yml`의 `node-version: '20'`을 `'24'`(또는 최소
     `'23.6'`)로 올리는 것 — 이건 jin/총괄자가 해줘야 한다.**

### region_scope 반영 (ADR-003 §1 / D-16)

지시대로 **화면에서 가리는 건 방어가 아니다**를 전제로 짰다 — 서버 강제는 C 담당(§10에서
이미 확인했듯 아직 안 됨: `/scores`가 region_scope 로 필터링하는지는 이번 검증 범위 밖).
콘솔이 할 일은 두 가지: (1) 범위 밖 지역이 "데이터 없음"으로 오해되지 않게 표시,
(2) 좁은 범위 사용자가 빈 화면을 안 보게.

**새 모듈 2개, 둘 다 `PredictionMap.tsx`의 실제 페인트 경로에 연결:**

- `src/lib/map/regionScope.ts` — `isRegionIdInScope()`(접두사 매칭, 빈 배열=전체),
  `withRegionScopeGuard()`가 `scoreScale.ts`의 `scoreFillExpression()` 결과를 감싸서
  **범위 밖 판정이 `NO_DATA_FILL` 분기보다 먼저** 평가되게 만든다(`["case", 범위밖조건,
  OUT_OF_SCOPE_FILL, <원래 점수 표현식 통째로>]` 형태로 중첩 — `scoreScale.ts` 자체는
  안 건드렸다, 그쪽 테스트·계약은 점수만 다루는 채로 유지). `OUT_OF_SCOPE_FILL`은
  `NO_DATA_FILL`과 다른 색(차가운 슬레이트 톤 vs 따뜻한 베이지) — 범례에도 조건부로
  추가했다(`regionScope`가 비어있지 않을 때만 표시, 전체 접근 사용자에게 불필요한 범례
  줄을 안 늘리려고).
- `src/lib/map/initialViewport.ts` — `computeInitialViewport()`. 시도 단위 대략 중심/줌
  표(공개된 잘 알려진 지리 정보, 모델 출력이 아니다 — 초기 카메라 프레이밍에만 쓰고
  점수·조인 등 데이터 경로엔 전혀 안 들어간다)로 region_scope 접두사를 매핑한다.
  접두사가 시군구/행정동 길이라도 앞 2자리(시도 코드)로 안전하게 찾는다(한국 행정코드는
  계층적이라 앞 2자리가 항상 시도). **인식 못 하는 접두사는 추측하지 않고 전국 기본
  뷰포트로 폴백한다.** 처음엔 실제 타일 데이터에서 bounding box 를 동적으로 계산하는
  방식(`map.querySourceFeatures` + fitBounds)도 고려했는데, 타일 로드 타이밍에 좌우되는
  불안정성이 있어 결정론적인 정적 표 방식으로 갔다 — 정밀한 경계가 아니라 "처음 열었을 때
  빈 화면이 아니다"가 목표라 이 정도 근사로 충분하다고 판단했다.

**클릭 가드도 추가했다.** `PredictionMap.tsx`의 클릭 핸들러가 `resolveRegionDetail()`을
부르기 **전에** `isRegionIdInScope()`를 확인한다 — 범위 밖 지역을 클릭하면 (지금은 상세
라우트가 없어 어차피 404 → 샘플 픽스처로 폴백하는데) **그 폴백을 아예 안 타게 막았다.**
안 그러면 "권한이 없는 지역"에 대해 그럴듯한 가짜 상세 데이터를 보여주는 꼴이 된다 —
§10 에서 이미 세운 정직성 원칙(진짜 없으면 있는 척 안 한다)에 정면으로 어긋나는 경우라
반드시 막아야 했다. `page.tsx`에 `restrictedRegionId` 상태를 새로 두고
`RegionDetailPanel`이 "권한 밖"과 "상세 없음"/"샘플 데이터"를 서로 다른 문구·색으로
렌더한다("데이터가 없는 것이 아니라 권한이 없는 것입니다" 문장을 명시적으로 넣었다 —
총괄자 지시 문구 그대로).

**테스트 (신규 2개 파일, 총 11개 케이스):**
- `tests/region-scope.test.mjs` — 접두사 매칭, `withRegionScopeGuard`가 원본 점수
  표현식을 안 건드리고 감싸기만 하는지, `OUT_OF_SCOPE_FILL !== NO_DATA_FILL`.
- `tests/initial-viewport.test.mjs` — 빈 범위→전국 기본값, 단일 시도→해당 시도 프레이밍,
  시군구 길이 접두사→시도 표로 정확히 폴백, 복수 시도→중심 평균+줌아웃, 미인식 접두사→
  추측하지 않고 기본값.

**실행 결과 (그대로 첨부):**
```
npm test          # 20 tests, 20 pass (기존 9 + region-scope 6 + initial-viewport 5)
npm run typecheck # tsc --noEmit, exit 0
npm run build     # next build 정상 완료 (223 kB)
```

**jin·총괄자 확인 필요:**
1. **`ci.yml`의 `node-version: '20'` → `'24'`(또는 `'23.6'` 이상)로 올려야 함.** 안 그러면
   console 잡이 다음 push 부터 깨질 가능성이 높다(Docker 없어 직접 재현은 못 함, 강한
   근거 있는 추정 — CONFIRMED 아님, 반드시 CI 로그로 재확인 요망).
2. 서버(C)가 `/scores`·`/regions`를 region_scope 로 실제 필터링하는지는 이번에 확인하지
   않았다 — §10 의 미해결 항목(C-2 라우트 부재 등)과 별개로 남아 있다.

---

## 12. 총괄자 지시 6차(최우선) — CI 첫 실행 실패 수정 (2026-08-17)

**원인 진단은 맞았다.** CI 첫 실행은 `2791644` 직후, 즉 `test` 스크립트가 아직
`node --test tests/**/*.test.mjs`였던 시점의 것 — 그 뒤 5차 지시 때 이미 `tests/*.test.mjs`
(별표 하나)로 고쳐서 커밋(`02a4c69`)했는데, 총괄자가 본 CI 로그가 그 커밋 이전 실행분이었던
것으로 보인다. 그래서 "그대로 고쳐라"로 지시된 `node --test tests`(디렉터리만 넘기기)를
**그대로 적용하기 전에 로컬에서 먼저 확인했는데, 이 환경에서 그 방법 자체가 동작하지
않았다:**

```
$ node --test tests
Error: Cannot find module 'C:\...\console\tests'   (MODULE_NOT_FOUND — CJS 로더가
                                                      "tests"를 모듈 이름으로 취급)
$ node --test ./tests
Could not find './tests'                            (테스트 러너 쪽 에러로 바뀌지만
                                                      여전히 실패)
```

**"Node 18+ 테스트 러너가 디렉터리를 인자로 받으면 재귀 탐색한다"는 전제가 이 Node 24
환경에서는 안 맞았다** — 위치 인자로 준 디렉터리는 재귀 탐색 대상이 아니라 실행할
파일(글롭)로 취급되는 것으로 보인다. 대신 **인자를 아예 안 주면** Node 가 현재 작업
디렉터리(`npm test`가 실행되는 `console/`) 아래를 **자체적으로** 재귀 탐색해서 기본
패턴(`**/*.test.{js,mjs,cjs}` 등, `node_modules` 자동 제외)에 맞는 파일을 전부 찾는다 —
셸 글롭도, Node 의 위치 인자 글롭도 전혀 관여하지 않는 제일 안전한 형태라 이걸로 고쳤다:

```json
"test": "node --test"
```

**확인 (지시대로 로컬에서 `npm test` 직접 실행, 파일 개수까지):**
```
$ rm -rf node_modules && npm ci     # 클린 설치로 CI 절차 재현
$ npm test
```
`console/tests/` 의 6개 파일 **전부** 실행됨을 개별 파일의 모듈 워닝 헤더로 확인했다
(`confidence-hatch.test.mjs`→scoreScale/hatchPattern, `initial-viewport.test.mjs`→
initialViewport, `join.test.mjs`→scoreScale, `region-scope.test.mjs`→regionScope,
`revenue-display.test.mjs`→format/revenue, `token-hygiene.test.mjs`→모듈 import 없음,
정적 스캔이라 워닝 자체가 없음 — 파일명 대신 테스트 이름으로 확인):

| 파일 | 케이스 수 |
|---|---|
| confidence-hatch.test.mjs | 3 |
| initial-viewport.test.mjs | 5 |
| join.test.mjs | 3 |
| region-scope.test.mjs | 6 |
| revenue-display.test.mjs | 2 |
| token-hygiene.test.mjs | 1 |
| **합계** | **20** |

```
ℹ tests 20
ℹ pass 20
ℹ fail 0
```
**6개 파일 전부, 20개 케이스 전부 — 한 파일만 돌고 통과하는 게 아니라는 걸 파일별 합산으로
직접 확인했다.** `npm run typecheck`(exit 0)·`npm run build`(정상 완료)도 클린 설치
상태에서 재확인.

**받아들인 교훈 (그대로 적용):** 앞으로 `console/package.json`의 스크립트에 셸 글롭을 쓰지
않는다. `*`든 `**`든 셸이 확장하게 두는 형태는 전부 후보에서 제외 — 필요하면 Node 자체
인자 없는 기본 탐색(이번 선택)이나, 정 안 되면 `"tests/*.test.mjs"`처럼 **따옴표로 감싸서
Node 에 그대로 넘기는** 형태만 쓴다(단, 이번에 확인했듯 Node 의 위치 인자 처리 자체도
환경에 따라 다를 수 있으므로 실제로 로컬에서 실행해 파일 개수까지 세어보지 않고는 안
믿는다).

다음 지시 대기.
