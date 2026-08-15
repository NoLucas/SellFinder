# 검증 결과

> 형식은 `verification/CHARTER.md` §8 참조.
> 확인된 것만 적는다. 추정은 별도 절에 분리한다. 모든 항목에 재현 경로 필수.
> 번호(VF-nnn)는 재사용하지 않는다. 해결돼도 번호는 남긴다.

---

## 회차: 1회차 · 2026-08-15 · HEAD `8133702`

검증 범위: A~D 전 폴더 (첫 회차라 미해결 항목이 없다).
A~D 의 마지막 커밋은 모두 08-15 18:01 이전이므로, 계약 `33fe4ac`(19:37) 과
ADR-002/003/004 는 아직 어느 폴더에도 반영돼 있지 않다. **아래 findings 는
ADR 반영 이전 상태에 대한 것이며, 일부는 이미 결정(D-nn)이 나 있고 이행만 남았다.**
그런 항목은 각 finding 에 해당 결정 번호를 적었다 — 재논의 대상이 아니라 이행 확인 대상이다.

실행 환경: 각 폴더의 자체 venv / node_modules. 픽스처는 `verification/fixtures/` 에 있고
전부 이번 회차에 직접 실행했다. 아래 "결과"는 전부 실제 출력이다.

## 요약

| S1 치명 | S2 심각 | S3 보통 | S4 낮음 | 해결됨 | 확인 불가 |
|---|---|---|---|---|---|
| 0 | 5 | 3 | 2 | 0 | 4 |

담당별: **C 6건** (VF-002·004·005·006·008·010) · **B 2건** (VF-001·007) ·
**D 1건** (VF-009) · **A·C·D 공동 1건** (VF-003, jin 결정 필요)

---

## S1 — 즉시 조치

(없음)

> 참고: `POST /v1/dev/token` (D-17 의 S1 조건) 은 아직 구현 자체가 없다. 아래 "확인 불가" 참조.

---

## S2 — 심각

### VF-001 · 요인 분해 불변식이 항등식으로만 검사돼 강제력이 없다 (B)

- 위치: `intelligence/tests/test_factor_model.py:49`
  (`test_log_contribution_sum_matches_log_of_total_multiplier`)
- 문제: `total_multiplier` 가 `log_contribution` 들로부터 계산되므로 이 단언은 **항상 참**이다.
  분해가 거짓이 돼도 테스트는 통과한다. D-04 가 막으려던 것("설명이 거짓이 되는 것")을 못 막는다.
- 재현 (런타임 변이 주입. 에이전트 파일은 수정하지 않는다):

  ```
  python verification/fixtures/vf_51_mutation.py M1   # log_contribution 을 소수 2자리로 반올림
  python verification/fixtures/vf_51_mutation.py M2   # price_acceptance 기여도만 x0.5
  python verification/fixtures/vf_51_mutation.py M3   # 마지막 요인을 출력에서 제거
  ```

- 결과:

  ```
  [M1] ran=12 failures=0 errors=0   *** MUTANT SURVIVED ***
  [M2] ran=12 failures=0 errors=0   *** MUTANT SURVIVED ***
  [M3] ran=12 failures=1 errors=1   CAUGHT BY: test_exactly_eight_factor_keys_in_contract_order
  ```

  분해를 **거짓으로 만드는** 두 변이(M1·M2)가 B 의 12개 테스트를 전부 통과한다.
  요인 개수를 바꾸는 M3 만 잡힌다.
- 모델 자체는 정상이다 (오해 방지):

  ```
  python verification/fixtures/vf_51_factor_sum.py
  → predictions checked: 2863 / worst |sum - ln(total_multiplier)| = 1.110e-16 / violations: 0
  ```

  **깨진 것은 코드가 아니라 안전망이다.**
- 닫는 방법 (이미 증명됨): 합이 아닌 **외부 증인**과 대조하면 M2 가 잡힌다.

  ```
  python verification/fixtures/vf_51_independent_catch.py M2
  → tautological check: pass  /  independent check: worst dev = 3.674e-01 -> FAIL
  ```

  `display_effect` 처럼 실제 배수에서 파생된 값, 또는 `value/benchmark` 비율과 대조하는
  단언을 추가하면 된다.
- 근거: `05_scoring_spec.md` §1·§8-1, `DECISIONS.md` D-04
- 담당: **B**

### VF-002 · `tenant_id` 주입이 400 이 아니라 조용히 무시된다 (C)

- 위치: `backend/app/security.py:14` (`get_tenant_id` 가 헤더만 읽고 다른 경로를 거부하지 않는다).
  라우터 어디에도 주입 거부가 없다 — `app/routers/predictions.py:40`, `:101`, `app/routers/basemap.py:11`
- 재현:

  ```
  backend/.venv/Scripts/python.exe verification/fixtures/vf_52_tenant.py
  ```

- 결과 (계약은 전부 `400 TENANT_ID_NOT_ALLOWED` 를 요구):

  ```
  A + ?tenant_id=tnt_other    /regions -> 200
  A + ?tenant_id=tnt_demo     /regions -> 200
  A + ?tenant_id=tnt_other    /scores  -> 200
  A + ?tenantId=tnt_other     /scores  -> 200
  A + X-Tenant-Id: tnt_other  /regions -> 200
  A + Tenant-Id:   tnt_other  /scores  -> 200
  ```

- **지금 데이터가 새지는 않는다**: 교차 테넌트 조회는 `404 PREDICTION_RUN_NOT_FOUND` 로 막힌다
  (`prediction_store.py:99`). 그래서 S1 이 아니라 S2 다.
  위험은 "무시"가 코드에 남아 있다는 것 자체다 — 언젠가 누가 그 값을 읽는다.
  `security.py` 독스트링은 *"tenant_id 는 어디서도 쿼리/바디로 읽지 않는다"* 라고 적고 있는데,
  계약이 요구하는 것은 **읽지 않는 것이 아니라 거부하는 것**이다.
- 근거: `06_governance.md` §1.1, `ADR-003-auth.md`, `DECISIONS.md` D-17 ("조용히 무시 금지")
- 담당: **C**

### VF-003 · 경계 타일 ↔ 점수 조인 키가 실제로 안 맞는다 — 지도가 통째로 회색 (A·C·D, jin 결정 필요)

- 위치:
  - A: `data-platform/src/boundary_tiles/tiler.py:56-63` — `region_id` 를 properties 에서 **제거**하고
    숫자 feature id 로만 싣는다 (`feature_id.py` 의 변환, 역매핑은 `*.id_map.json`)
  - A 매니페스트: `data-platform/output/tiles/manifest.json` — 그런데 `feature_id_property: "region_id"`
    라고 적혀 있다 (**자기 산출물과 모순**)
  - C: `backend/app/services/basemap_registry.py:29` — `FEATURE_ID_PROPERTY = "region_id"`
  - D: `console/src/components/PredictionMap.tsx:105` — `promoteId: { [source_layer]: feature_id_property }`
- 재현 (A 의 실제 `.pmtiles` + C 의 실제 샘플 + D 의 실제 조인 로직. MapLibre 의 `getId()` 와
  `String(featureId)` 강제 변환을 원본에서 그대로 옮겨 썼다):

  ```
  backend/.venv/Scripts/python.exe verification/fixtures/vf_56_dump_features.py
  node verification/fixtures/vf_56_join.mjs
  ```

- 결과:

  ```
  manifest.feature_id_property = "region_id"
  tile feature ids (A, real)   = 11, 26, 28, 41, 50
  tile feature properties keys = ["name","level","is_synthetic_placeholder"]   ← region_id 가 없다
  features whose promoted id is undefined : 5/5
  features that received a score          : 0/5
  RESULT: every region paints NO_DATA grey. No error thrown, no console warning - silent blank map.
  ```

  `promoteId` 를 빼고 네이티브 MVT id 로 붙여보는 반사실 검사도 **0/5** 다 —
  C 의 점수는 `region_level="adm_dong"` 인데 5자리 시군구 코드(41135…)를 담고 있고,
  A 는 시도(11, 26…)만 발행하기 때문이다 (이쪽은 VF-004·D-15).
- **에러도 경고도 없다.** 세 폴더의 테스트와 `validate_contracts.py` 가 전부 통과하는 상태에서
  화면만 조용히 비어 있다. 헌장 §1 의 "통합 불일치" 유형 그대로다.
- **jin 결정이 필요한 지점**: A 는 브리프 지시("region_id 를 속성이 아니라 feature id 로 실어라",
  `feature_id.py` 독스트링)를 따랐고, D 는 계약(`feature_id_property`)을 따랐다. **둘 다 자기 문서를
  지켰는데 안 맞는다.** 계약이 두 방식을 동시에 말하고 있는 것이 원인이다. 선택지는 둘 중 하나다:
  1. A 가 `region_id` 를 properties 에도 싣는다 (계약 문구 유지, 타일 크기 소폭 증가)
  2. 계약이 "네이티브 feature id 사용"을 명시하고 `feature_id_property` 를 null 로 두는 규약을 만든다
     (D 는 `promoteId` 를 쓰지 않고 숫자 id 를 문자열로 비교. `id_map.json` 의 위치도 계약에 올려야 한다)

  A 의 매니페스트가 이미 `id_map_path` 를 내보내고 있다는 사실은 2번 쪽 설계가 실재한다는 뜻이다.
- 근거: `04_api_contract.yaml` v0.2.1 (`feature_id_property`), `ADR-001-map-tiles.md`, `DECISIONS.md` D-05
- 담당: **jin(결정) → A·C·D(이행)**

### VF-004 · C 가 광고하는 빈티지·줌이 A 의 실제 산출물과 다르다 (C)

- 위치: `backend/app/services/basemap_registry.py:32` (`_ZOOM_BY_LEVEL`), `:64-68` (`_VINTAGES` 하드코딩)
- 재현:

  ```
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe verification/fixtures/vf_56_vintage.py
  ```

- 결과:

  ```
  A 가 실제 발행:  sido  vintages=['2026-01-01','2026-07-01']  latest=2026-07-01
  C 가 광고:       sido  vintages=['2026-01-01','2025-01-01']  latest=2026-01-01
                   sigungu / adm_dong 도 광고하지만 A 는 아직 만들지 않았다

  C.get(level=sido, vintage=2026-07-01) -> 404 BOUNDARY_VINTAGE_NOT_FOUND   ← 실재하는데 없다고 답한다
  C 가 광고한 sido/2025-01-01 -> A 에 있는가? False                          ← 없는데 있다고 답한다

  zoom, sido:  A manifest minzoom=0 maxzoom=8  /  C response minzoom=5 maxzoom=8
  ```

- 양방향으로 틀렸다. 존재하는 빈티지를 404 로 막고, 없는 빈티지를 목록에 넣는다.
  줌은 D-14(sido minzoom=0)와도 다르다.
- **이미 결정돼 있다**: D-13(C 는 A 의 매니페스트를 읽는다, 없으면 빈 배열이 아니라 503),
  D-14(레벨별 줌은 A 매니페스트가 정하고 C 는 그대로 전달). 재논의 대상이 아니라 **미이행**이다.
  이 finding 은 이행 여부를 다음 회차에 확인하기 위한 것이다.
- 근거: `ADR-002-artifact-publishing.md`, `DECISIONS.md` D-08·D-13·D-14
- 담당: **C**

### VF-005 · T0 인데 `confidence.level = "high"` 가 반환된다 (C)

- 위치: `backend/app/routers/predictions.py:89` (`/regions`), `:129` (`/scores`) —
  저장된 `confidence_level` 을 그대로 내보내며 T0 상한을 적용하지 않는다.
  금액(`expected_revenue_krw`)은 같은 함수 `:82-88` 에서 T0 분기로 제대로 막고 있다. **한 겹만 있다.**
- 재현 (백엔드에 T0 run 을 만드는 테스트가 하나도 없어 검증자가 직접 만들었다 — VF-008):

  ```
  backend/.venv/Scripts/python.exe verification/fixtures/vf_t0_api.py
  ```

- 결과:

  ```
  GET /regions (T0) -> 200, 5 rows
    rows with non-null expected_revenue_krw : 0        ← 금액은 정상
    /regions (T0) confidence levels : ['high','high','medium','medium','low']
    above ceiling (=='high')        : 2               ← 계약: 0 이어야 한다
    /scores  (T0) confidence levels : ['high','high','medium','medium','low']
    above ceiling (=='high')        : 2
  ```

- 자사 판매 데이터가 없는 테넌트에게 "높은 신뢰도"라고 말하는 것은 D-03 이 막으려던 것과 같은 종류의
  거짓이다. 금액만 막고 신뢰도를 안 막으면 절반만 지킨 것이다.
- 근거: `05_scoring_spec.md` §2 ("T0 는 `confidence.level` 상한이 medium"), `DECISIONS.md` D-03
- 담당: **C**

---

## S3 — 보통

### VF-006 · 인증이 필요한 응답에 `Cache-Control: public` + 서명 URL 이 함께 나간다 (C)

- 위치: `backend/app/routers/basemap.py:31`
- 재현:

  ```
  backend/.venv/Scripts/python.exe verification/fixtures/vf_52b_basemap.py
  ```

- 결과:

  ```
  level=adm_dong  auth=yes -> 200  Cache-Control=public, max-age=3600  signed=True
      tile_url = https://cdn.sellfinder.kr/tiles/regions-adm_dong-2026-01-01.pmtiles?expires=…&sig=…
  level=adm_dong  auth=NO  -> 401
  ```

  `Authorization` 헤더가 있어야만 얻을 수 있는 **서명 URL** 이 공용 캐시 가능으로 표시된다.
  중간 프록시/CDN 이 이 응답을 캐시하면 토큰 없는 요청자에게 서명 URL 이 도달할 수 있다.
- 지금은 응답 본문이 테넌트별로 다르지 않아 유출 영향이 제한적이다. 그래서 S3 다.
  **매니페스트가 테넌트별로 갈라지는 순간 S1 로 승격된다** (D-17: 캐시 키에 `tenant_id` 포함).
  라우터 독스트링(`basemap.py:20-22`)은 *"tenant-independent 라서 캐시 가능"* 이라고 적고 있으나,
  서명 URL 은 테넌트 독립이어도 공개 대상이 아니다.
- 근거: `06_governance.md` §1.5, `ADR-003-auth.md`, `DECISIONS.md` D-17
- 담당: **C**

### VF-008 · 백엔드에 T0 run 을 만드는 테스트가 없어 T0 분기 전체가 한 번도 실행되지 않는다 (C)

- 위치: `backend/app/services/prediction_store.py:106` — 시드는 `run_demo01`(T1) **하나뿐**이다.
  `backend/tests/*` 어디에도 `data_tier="T0"` 인 run 이 없다.
- 결과: `routers/predictions.py:82-88` 의 T0 금액 차단 분기를 19개 테스트 중 **어느 것도 실행하지 않는다**.
  검증자가 직접 T0 run 을 만들어 실행한 결과 금액 차단은 정상 동작했으나(위 VF-005 출력),
  **회귀를 막는 것이 아무것도 없다.** 실제로 같은 공백 때문에 VF-005(신뢰도 상한)가 잡히지 않았다.
- 재현: `verification/fixtures/vf_t0_api.py` 가 하는 일이 곧 빠져 있는 테스트다.
- 근거: `05_scoring_spec.md` §2·§8-2, `DECISIONS.md` D-03
- 담당: **C**

### VF-009 · console 에 실행 가능한 테스트가 0개다 (D)

- 위치: `console/package.json` — 테스트 러너·테스트 파일 없음. `tsc --noEmit`(exit 0) 만 있다.
- 결과: 추적 매트릭스의 D 관련 조항이 **전부 구멍**이다 —
  조인 키 일치, `score_range` 로 색상 스케일 고정, `confidence='low'` 의 패턴 구분,
  T0 금액 자리 표기, T0 UI 문구. 코드를 읽으면 맞게 구현돼 있으나(예: `scoreScale.ts` 가
  `score_range` 를 받고 `PredictionMap.tsx:118` 이 전달), 누가 되돌려도 아무도 모른다.
  VF-003 이 세 폴더 모두 초록불인 채로 살아남은 것도 이 구멍 안에서다.
- 최소 제안 (검증자는 코드를 쓰지 않는다 — 어디가 비었는지만 적는다):
  `backend/samples/*.json` 을 입력으로 (1) 파서 → (2) `setFeatureState` 키 생성 →
  (3) fill expression 까지 가는 노드 단위 테스트 하나. `vf_56_join.mjs` 가 그 형태의 참고 구현이다.
- 근거: `verification/CHARTER.md` §5.6·§5.7, `05_scoring_spec.md` §2
- 담당: **D**

---

## S4 — 낮음

### VF-007 · `tenant_scoped` 키 목록이 테스트에 하드코딩돼 있다 (B)

- 위치: `intelligence/tests/test_synthetic_generator.py:38`
  (`{"own_store_count_2km", "own_distribution_points", "own_share_of_category"}`)
- 문제: 계약(`03_region_features.json` 의 `feature_registry.tenant_scoped`)에서 읽지 않고 복사했다.
  현재는 세 키가 일치하지만(검증자 대조 확인), 계약에 네 번째 키가 추가되면 테스트는 통과한 채
  그 키가 공용 피처스토어로 새 나간다. 헌장이 "가장 흔한 실수"로 지목한 지점이다.
- 재현: `03_region_features.json` 의 `tenant_scoped` 에 키를 하나 추가해도
  `python -m unittest discover -s tests` 는 28 passed 그대로다.
- 근거: `06_governance.md` §1.3, `03_region_features.json`
- 담당: **B**

### VF-010 · `suppressed` 원시값 차단이 생성기 단계에만 있다 (C, B)

- 위치: 차단은 `intelligence/tests/test_synthetic_generator.py:144` 가 생성기 출력에 대해서만 검사한다.
  `backend/app` 전체에 `suppressed` 문자열이 **한 번도 등장하지 않는다** (grep 0건).
- 문제: API 응답·로그·에러 메시지·내보내기 경로에 대한 방어가 없다. 지금은 내보내기 기능 자체가
  없어 실제 유출 경로가 없으므로 S4 다. **내보내기(xlsx/csv)나 상세 조회가 붙는 순간 S1 후보로 승격된다.**
- 근거: `06_governance.md` §2.3, `05_scoring_spec.md` §8-6
- 담당: **C** (B 는 `coverage_flag` 를 응답까지 전달하는 경로를 정의)

---

## 추정 (미확정)

> 확정 findings 와 절대 섞지 말 것. 확인 방법을 반드시 적는다.

(없음 — 이번 회차 항목은 전부 실행으로 확정했다.)

---

## 해결 확인됨

(첫 회차 — 없음)

참고로 아래 두 가지는 **결함이 아님을 실행으로 확인**했다. 다음 회차에 다시 올리지 말 것.

- **요인 로그 합 불변식 자체**: 2,863건 예측에서 최대 편차 `1.11e-16` (한계 1e-6). 모델은 정상이다.
  문제는 테스트의 강제력이고 그것이 VF-001 이다.
- **API 재현성**: `/scores`·`/regions`·`/basemap` 을 5회씩 호출해 본문 sha256 이 전부 동일했다
  (`vf_repro_api.py`). 서명 URL 이 있는 basemap 도 TTL 창 안에서는 동일하다.

---

## 확인 불가

> "아마 괜찮을 것"은 쓰지 않는다. 무엇을 왜 확인할 수 없었는지만 적는다.

- **RLS 가 DB 레벨에 걸렸는가** (`06_governance.md` §1.2) — DB 가 없다.
  `prediction_store.py` 는 인메모리 dict 다. DB 도입 전까지 확인 불가.
- **개발 전용 토큰 엔드포인트가 운영에 노출되는가** (D-17 의 S1 조건) —
  `POST /v1/dev/token` 도 `SELLFINDER_ENV` 분기도 아직 없다 (grep 0건). ADR-003 구현 후 첫 확인 대상.
- **내보내기(xlsx/csv)에 T0 금액·suppressed 원시값이 새는가** (CHARTER §5.1·§5.4) —
  내보내기 경로가 구현되지 않았다 (`backend/app` 에 export/csv/xlsx 라우트 0건).
- **학습 데이터 누수 / 백테스트 시간 분할** (`05_scoring_spec.md` §5.1) —
  B 가 Step 3 범위로 명시 선언했고 backtest 모듈이 없다. 누수 **함정 피처**가 생성기에 심겨 있고
  그 존재는 `test_synthetic_generator.py:74,84,87` 로 검증되지만, **그것을 잡아내는 하네스**가 없다.
