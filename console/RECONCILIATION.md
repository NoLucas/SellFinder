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

해당 없음 (`/console` 자체에는 버릴 것도 없음).

## 5. 계약에 있는데 아직 없는 것 → 착수 순서

브리프의 "핵심 화면 4개"를 다음 순서로 진행 예정:

1. **타입/클라이언트 레이어** — `04_api_contract.yaml`에서 타입을 생성(손으로 안 씀).
   `/backend`가 아직 실제 엔드포인트를 준비하지 못했다면 계약의 example 응답을 목 데이터로 사용.
2. **지도 뷰** — 벡터타일(`/predictions/{run_id}/tiles/{z}/{x}/{y}.mvt`) 기반 opportunity_score
   히트맵. 상단에 제품(SKU)·채널·objective 선택 컨트롤. `confidence='low'` 지역은 색상만이 아니라
   패턴/해칭으로 구분.
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

- **`/frontend`를 어떻게 할지** — 폐기하는지, `/console`로 포팅할 부분(예: `sequentialScale.ts`
  같은 재사용 가능한 순수 유틸)이 있는지는 사람(jin)의 결정 사항으로 보인다. `/console` 소유권
  밖이라 스스로 판단해 옮기지 않았다.
- **`/backend` 진행 상태** — 브리프상 "C가 아직 준비 안 됐으면 mock을 먼저 만들어 D가 시작할 수
  있게 하라"고 되어 있다. 방금 확인한 MEMORY 갱신 로그에 `scope_backend_role.md`가 새로 생긴 걸
  보면 에이전트 C도 이번 재정렬로 막 착수한 것 같다 — 실제 엔드포인트가 아직이면 `04_api_contract.yaml`의
  example을 목으로 쓰고 시작하겠다. mock/실제 전환 시점을 알려주면 반영한다.
- **인증/토큰 발급 방식** — `tenant_id`가 토큰에서만 파생된다는 규칙은 명확하지만, `/console`이
  로그인/토큰 발급을 어떻게 받는지(자체 구현 vs `/backend` 제공 엔드포인트)는 `04_api_contract.yaml`에
  명시가 없어 `/backend` 담당에게 확인이 필요하다.
- **벡터타일 서버 소스** — region 경계(GeoJSON)를 벡터타일로 변환하는 주체가 `/data-platform`인지
  `/backend`인지 브리프에 명확하지 않다(`03_region_features.json`에 A가 "벡터타일 생성"이라고
  되어 있고, `04_api_contract.yaml`의 타일 엔드포인트는 `/backend`에 있음) — `/console`은 최종
  엔드포인트만 소비하면 되지만 확인 차 남겨둔다.

---

기존 코드 삭제 없음(`/console`에 삭제할 것도 없었음). 다음 지시 대기.
