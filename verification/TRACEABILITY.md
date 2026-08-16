# 추적 매트릭스 — 계약 조항 ↔ 강제하는 테스트

> 형식: `verification/CHARTER.md` §6.
> **"테스트가 있다"로 끝내지 않는다.** 아래 "실행 확인" 열은 전부 이번 회차에 직접 실행한 결과다.
> 빈 칸(**구멍**)이 곧 findings 다.

1회차 · 2026-08-15 · HEAD `8133702`
(작성 시점 HEAD 는 `d17d7cf` 였다. 그 뒤 계약 `33fe4ac` 와 브리프 `8133702` 가 들어왔으나
A~D 폴더는 한 파일도 바뀌지 않았으므로, 아래 실행 결과는 `8133702` 에서 전부 재실행해 동일함을 확인했다.)

> **2회차 갱신 (2026-08-16 · HEAD `d942dd4`)**: 아래 표의 판정 열 중 **VF-001·002·003·005·006·007·008·009**
> 는 `orchestrator/DISPATCH.md` 1차 지시 이행으로 이번 회차에 **O 로 전환**됐다 — 각 행에
> `(2회차: 통과)` 로 표시했다. 상세 재현 경로는 `verification/FINDINGS.md` "회차: 2회차"를 봐라.
> **VF-004 는 3회차(HEAD `641cfa2`)에서 O 로 전환됐다.** 2회차의 "미커밋" 판정은 관측 시점
> 오류였다 — C-7(`a760b31`)이 실제로는 2회차 커밋보다 먼저 마스터에 있었다. 상세는
> `verification/FINDINGS.md` "회차: 3회차"를 봐라. 이번 표의 나머지 셀(1행 5·6, 3.4·1.5,
> 5절 전체)은 1차 지시 범위 밖이라 변경 없음 — 1회차 판정 그대로다.

## 이번 회차에 실행한 스위트

| 스위트 | 명령 | 결과 |
|---|---|---|
| B intelligence | `cd intelligence && python -m unittest discover -s tests -v` | **28 passed** |
| C backend | `cd backend && .venv/Scripts/python -m pytest tests -q` | **19 passed** |
| A data-platform | `cd data-platform && .venv/Scripts/python -m pytest tests -q` | **6 passed** |
| D console | `cd console && ./node_modules/.bin/tsc --noEmit` | **exit 0** (테스트 스위트 없음) |

> D 에는 실행 가능한 테스트가 하나도 없다. 타입 체크만 있다. 아래 D 관련 조항이 전부 구멍인 이유다. → **VF-009**
> **(2회차: 통과)** `console/tests/join.test.mjs` 신설, `node --test` 로 3/3 통과 — 파서·조인·fill expression 전 구간.

추가로 C 의 실제 샘플을 D 의 파서 타입에 직접 넣어봤다
(`console/node_modules/.bin/tsc -p verification/fixtures/tsconfig.vf.json`).
`region_level` / `level` 이 JSON 임포트에서 `string` 으로 넓어져 `RegionLevel` 유니온에 안 들어가는
TS2322 두 건 외에 **구조적 불일치는 없다**. 이건 TS 의 JSON 임포트 특성이지 결함이 아니다 — findings 로 올리지 않는다.
페이로드가 실제로 안 맞는 곳은 타입이 아니라 조인 키(VF-003)와 레벨/빈티지(VF-004)다.

---

## 1. `05_scoring_spec.md` §8 — 실패 모드 체크리스트 8개

| # | 계약 조항 | 출처 | 강제하는 테스트 | 실행 확인 | 판정 |
|---|---|---|---|---|---|
| 1 | 요인 로그 기여도 합 = 최종 배수의 로그 (오차 < 1e-6) | §8·§1, `D-04` | `intelligence/tests/test_factor_model.py:49` | 통과 | **구멍 — VF-001** (항등식이라 강제력 없음. 변이 M1/M2 생존) → **(2회차: 통과)** 외부 증인 단언 추가, M1/M2 모두 잡힘 |
| 2 | T0 응답에 `expected_revenue_krw` 가 null | §8·§2, `D-03` | 모델측 `test_factor_model.py:97,101` | 통과 | O (모델측) |
| 2b | 〃 **API 응답측** | 〃 | **없음** — C 는 `data_tier="T1"` run 하나만 시드(`prediction_store.py:106`), T0 분기(`routers/predictions.py:83`)는 어떤 테스트도 실행하지 않음 | 검증자가 직접 T0 run 을 만들어 실행 → **동작은 정상** (5행 전부 null) | **구멍(미추적) — VF-008** — 코드는 맞으나 회귀를 막는 테스트가 없다 → **(2회차: 통과)** `backend/tests/test_predictions_t0.py` 신설, T0 분기가 스위트에서 실행됨 |
| 3 | `competition` 이 1 을 초과하지 않음 | §8 | `test_factor_model.py:66` | 통과 | O |
| 4 | 온라인 채널에 `foot_traffic`/`competitor_density` 미투입 | §8 | `test_factor_model.py:75,88`, `test_synthetic_generator.py:159` | 통과 | O |
| 5 | 학습 시 `as_of` 가 타깃 기간 이후인 케이스 없음 (누수) | §8·§5.1 | **없음** — B 가 Step 3 범위로 명시 선언(`test_factor_model.py` 파일 독스트링) | — | **구멍** (선언된 미구현. 함정 피처 자체는 `test_synthetic_generator.py:74,84,87` 로 검증됨) |
| 6 | `suppressed` 셀 원시값이 응답 어디에도 노출 안 됨 | §8, `06` §2.3 | 생성기측 `test_synthetic_generator.py:144`, API측 `backend/tests/test_privacy.py`(7건) | 통과 | **부분 구멍 — VF-010** → **(4회차: 통과)** 응답·로그·에러 메시지 3경로 전부 API 레벨에서 테스트로 고정, 검증자가 C 미작성 시나리오로 독립 재확인. **단 4번째 경로(정렬 순서)가 열려 있다 — VF-013(S2, 신규), 아직 미해소** |
| 7 | 동일 `run_id` 재실행 결과 100% 동일 | §8, `06` §4 | `test_factor_model.py:114,119`, `test_synthetic_generator.py:200` | 통과 | O |
| 7b | 〃 **API 응답측** | 〃 | **없음** | 검증자가 직접 5회 반복 → `/scores`·`/regions`·`/basemap` 모두 바이트 동일 | O (동작 확인, 테스트 미추적) |
| 8 | 인구 3만 미만 행정동이 상위 랭킹 독식 안 함 | §8 | `test_factor_model.py:131` | 통과 | O |

## 2. `05_scoring_spec.md` §2 — Tier 별 동작

| 계약 조항 | 출처 | 강제하는 테스트 | 실행 확인 | 판정 |
|---|---|---|---|---|
| T0 는 `f₈ tenant_calibration = 1.0` 고정 | §2 | `test_factor_model.py:106` | 통과 | O |
| **T0 는 `confidence.level` 상한이 `medium`** | §2 | **없음** | 검증자가 T0 run 실행 → `/regions`·`/scores` 모두 `high` 2건 반환 | **위반 — VF-005** → **(2회차: 통과)** `above ceiling` 0건, 상한 medium 적용 확인 |
| T0 UI 문구가 "상대적 유망도 랭킹" | §2 | **없음** (D 테스트 없음) | — | **구멍 — VF-009** (조인 테스트는 생겼으나 이 문구 자체는 여전히 테스트 안 됨 — 부분 잔존) |

## 3. `06_governance.md` §1 — 테넌트 격리

| # | 계약 조항 | 출처 | 강제하는 테스트 | 실행 확인 | 판정 |
|---|---|---|---|---|---|
| 1.1a | 다른 테넌트의 run 이 새지 않음 | §1.1 | `backend/tests/test_predictions_regions.py:31` | 통과 | O |
| 1.1b | **`tenant_id` 를 쿼리/바디/헤더로 받으면 `400 TENANT_ID_NOT_ALLOWED`** | §1.1 | **없음** | 검증자가 직접 주입 → 전부 **200, 조용히 무시** | **위반 — VF-002** → **(2회차: 통과)** 쿼리·헤더 7경로 전부 400 TENANT_ID_NOT_ALLOWED |
| 1.2 | RLS 를 DB 레벨에 건다 | §1.2 | **없음** | DB 자체가 없음(`prediction_store.py` 인메모리) | **확인 불가** |
| 1.3 | `tenant_scoped` 피처가 공용 피처스토어에 안 들어감 | §1.3 | `intelligence/tests/test_synthetic_generator.py:36` | 통과 | O (단 3개 키를 계약에서 읽지 않고 테스트에 하드코딩 — 계약에 키가 추가되면 못 잡는다. VF-007) → **(2회차: 통과)** `contracts.load_tenant_scoped_feature_keys()` 로 계약에서 직접 읽도록 변경됨 |
| 1.4 | 공용 기저 모델에 `tenant_sales` 미혼입 | §1.4 | **없음** (학습 코드 미구현) | — | **구멍** |
| 1.5 | 캐시 키에 `tenant_id` 포함 | §1.5 | **없음** | 서버측 캐시 계층 없음. 단 C 가 인증 응답에 `Cache-Control: public` 을 붙임 | **구멍 — VF-006** → **(2회차: 통과)** 서명 응답은 `Cache-Control: private`로 분기됨 |

## 4. `ADR-001` / `DECISIONS.md` D-05~D-09 — 지도

| 계약 조항 | 출처 | 강제하는 테스트 | 실행 확인 | 판정 |
|---|---|---|---|---|
| 경계 타일(A)·점수(C) 분리, 서버가 합치지 않음 | `D-05` | `backend/tests/test_basemap.py:20` | 통과 | O |
| `/scores` 는 튜플배열 + `schema` 형식 | `D-07` | `test_predictions_scores.py:15` | 통과 | O |
| `/scores` 페이지네이션 없음 | `D-07` | `test_predictions_scores.py:44` | 통과 | O |
| `/scores` 에 금액 미포함 | `D-07` | `test_predictions_scores.py:36` | 통과 | O |
| `score_range` 필수 | `D-07` | `test_predictions_scores.py:52` | 통과 | O |
| 클라이언트가 색상 스케일 재계산 안 함 | `D-07` | `console/tests/join.test.mjs` (fill expression 테스트) | 통과 | **(2회차: 통과)** `join.test.mjs` 가 `scoreScale.ts` 의 `score_range` 반영을 직접 검증 |
| `/regions` 는 유지 (`/scores` 가 대체 아님) | `D-07` | `test_predictions_regions.py:15` | 통과 | O |
| `prediction_run` 에 `boundary_vintage` 기록·보존 | `D-08` | `test_predictions_scores.py:15`, `data-platform/tests/test_boundary_tiles.py:86,99` | 통과 | O (각 에이전트 내부 한정) |
| **`feature_id_property` ↔ D 의 `setFeatureState` 키 일치** | `04_api_contract.yaml` v0.2.1, `D-05` | **없음 — 양쪽을 붙여보는 테스트가 어디에도 없다** | 검증자가 A 의 실제 `.pmtiles` + C 의 실제 매니페스트 + D 의 실제 조인 코드로 실행 → **0/5 매칭** | **위반 — VF-003** → **(2회차: 통과)** region_id 가 properties 에 존재(0/250 미정의), scores.json 5건 전부 매칭. D 자체 테스트(`join.test.mjs`)로도 교차 확인 |
| C 가 광고하는 level/vintage 가 A 의 실제 산출물과 일치 | `D-08` | `backend/tests/test_basemap.py` (C-7/C-8, `a760b31`) | 통과 | **위반 — VF-004** → **(3회차: 통과)** sido/sigungu/adm_dong 전부 A 실물과 일치, 404 오탐 재현 안 됨, `pytest backend/tests -q` 32 passed |
| 표준 행정경계는 GeoJSON 금지, 타일만 | `D-09` | `test_basemap.py:20` | 통과 | O |
| 폐기된 `.mvt` 엔드포인트 부재 | `D-06` | **없음** | 검증자가 전 저장소 grep → 참조 0건 | O (동작 확인, 테스트 미추적) |

## 5. `05_scoring_spec.md` §6 — evidence 작성 규칙

| 계약 조항 | 출처 | 강제하는 테스트 | 실행 확인 | 판정 |
|---|---|---|---|---|
| evidence 가 실제 피처값을 인용 | §6.1 | `test_factor_model.py:75,88` (부분) | 통과 | 부분 → **(5회차, HEAD `525594a`: 위반 없음)** 검증자가 evidence 1,600건을 직접 실측 — 인용값이 전부 FactorResult 의 value/benchmark 와 같은 변수에서 나옴 |
| evidence 에 비교 기준 동반 | §6.2 | **없음**(5회차 시점 미커밋 — B 작업 중) | — | **구멍** → **(5회차: 위반 없음, 자동 테스트는 아직 없음)** 1,600건 실측, benchmark 있는 케이스 전부 비교 표현 동반 |
| 모델이 안 쓴 근거를 지어내지 않음 (null 피처 인용 금지) | §6.2 | **없음**(5회차 시점 미커밋) | — | **구멍** → **(5회차: 위반 없음)** value=None 케이스 전부 조기 반환 구조라 지어낼 코드 경로 자체가 없음, 1,600건 실측 0 위반 |
| 인과 주장 금지 | §6.3 | **없음**(5회차 시점 미커밋) | — | **구멍** → **(5회차: 위반 없음)** 1,600건 전수 검색, 인과 표현 0건 |
