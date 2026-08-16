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

**D-2 — 테스트 러너.** 새 devDependency 없이 Node 24 내장 `node --test` 사용.
Node 24가 `.ts`를 네이티브로 type-strip 하는 걸 확인하고 나서 골랐다 — `scoreScale.ts`를 리임플리
먼트하지 않고 실제 프로덕션 모듈을 그대로 import 해서 검증한다. `console/tests/join.test.mjs`,
4개 테스트: (1) 실제 샘플 → `setFeatureState` 키 생성, (2) ADR-005가 요구하는 모양(속성에
`region_id`)의 합성 타일로 조인 성공을 못박는 회귀 가드, (3) A의 현재(수정 전) 실 타일 픽스처로
0/5를 못박는 테스트 — **A/C가 ADR-005를 반영하면 이 테스트가 실패로 돌아선다. 그게 버그가 아니라
D-5(실제 아티팩트 통합) 착수 신호다. "고치지" 말고 D-5로 넘어갈 것.** (4) `scoreScale.ts`의
fill expression이 실제 `score_range`를 쓰는지. `npm test`로 실행, 실행 결과는 총괄자 보고에 첨부.

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

다음 지시 대기.
