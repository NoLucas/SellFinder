# RECONCILIATION — 에이전트 B (Intelligence)

작성일: 2026-08-15
읽은 계약: `00_product_spec.md`, `01_domain_model.json`, `02_taxonomy.json`,
`03_region_features.json`, `05_scoring_spec.md`, `04_api_contract.yaml`

---

## 1. 지금까지 내가 만든 것

`/intelligence` 폴더에는 `.gitkeep` 외에 아무 코드도 없다. 이 역할로는 처음 시작이다.

**참고 (내 폴더 밖, 수정 대상 아님):** `/model` 폴더에 이전 제품 정의(매물 단위 중고거래
판매확률/가격 예측 — `sold`/`days_to_sell`/`final_sale_price` 라벨 기반) 시절 코드가 있다
(`schema_io.py`, `dummy_data.py`, `features.py`, `model.py`, `train.py`, `predict.py`).
이는 폐기된 제품 가정 위에서 만들어졌고 소유권도 `/intelligence`가 아니므로 이관하지 않는다.
다만 구조적으로 참고할 만한 패턴은 있다: 계약 스키마에 대한 로드/검증을 별도 모듈로 분리
(`schema_io.py`), 합성 데이터 생성기를 프로덕션 코드와 분리, train/predict를 얇은 CLI로 감싸고
로직은 `model.py`에 둔 것. `/intelligence`를 새로 지을 때 이 구조는 재사용하되, 내용은
전부 새 계약(승법 요인 모델, tier, objective, evidence) 기준으로 새로 작성해야 한다.

## 2. 새 계약과 일치하는 것 → 유지

해당 없음 (기존 산출물 없음).

## 3. 계약과 어긋나는 것 → 리팩터링

해당 없음.

## 4. 계약에 없어서 버려야 하는 것

해당 없음. (`/model`의 구코드는 내 폴더 소관이 아니므로 이 보고서의 대상이 아니다 —
필요하다면 `/model` 자체의 존치/폐기는 사람(jin)이 결정할 사항으로 보인다.)

## 5. 계약에 있는데 아직 없는 것 → 작업 순서

`05_scoring_spec.md` §8 실패 모드 체크리스트를 최종 통과 기준으로 두고, 의존성 순서대로 진행한다.

1. **합성 데이터 생성기** (`/data-platform`이 아직 실데이터를 내지 않았으므로 대기하지 않고 직접 생성)
   - `03_region_features.json`의 `feature_registry`에 등록된 키만 사용해 지역×피처 합성 데이터 생성
   - `02_taxonomy.json`의 노드 + `channels` 조합으로 합성 제품/데모 SKU 생성
   - 결측을 절대 0으로 채우지 않고 실제로 null을 섞어 넣어, 이후 로직이 결측을 무시하지 않는지 검증 가능하게 함

2. **SKU 자동 분류기** (`02_taxonomy.json` `classification_contract`)
   - 입력: name/description/unit_price_krw/pack_size → 출력: candidates(≤5, confidence 내림차순)/suggested_channels/extracted_attributes
   - `02_taxonomy.json`에 실재하는 `node_id`만 반환하도록 강제 검증 (존재하지 않는 노드 생성 시 예외)
   - confidence < 0.70 → `needs_review=true`

3. **피처 조회 인터페이스 (계약 소비 측)**
   - `get_features(region_ids, feature_keys, as_of)` 형태로만 피처를 읽는 얇은 클라이언트를 만든다.
   - "최신값" 헬퍼는 만들지 않는다 — `03_region_features.json`의 `point_in_time_rule`이 명시적으로 금지.
   - `/data-platform`이 아직 이 인터페이스의 실제 구현체를 안 줬으므로, 1번 합성 데이터를 같은
     시그니처로 서빙하는 스텁을 만들어 이후 로직이 실제 구현으로 교체될 때 코드 변경이 없게 한다.

4. **승법 요인 모델 (핵심, `05_scoring_spec.md` §1)**
   - 8개 `factor_key` 고정: `addressable_demand`, `category_penetration`, `product_affinity`,
     `price_acceptance`, `competition`(≤1 강제), `channel_availability`, `seasonality`, `tenant_calibration`
   - `Σ log_contribution == ln(total_multiplier)` 오차 < 1e-6을 단위 테스트로 강제
   - 온라인 채널(`type='online'`)에는 `foot_traffic`/`competitor_density` 계열 피처 입력 금지 — 채널 타입 체크를 모델 진입점에서 강제

5. **Tier(T0/T1/T2) 로직 (`05_scoring_spec.md` §2)**
   - T0: `tenant_calibration=1.0` 고정, `expected_revenue_krw` 항상 null, `confidence.level` 상한 medium
   - T1/T2: 잔차 모델/전역 스케일 보정 — `tenant_sales`가 있어야 하므로 4번 이후, `/data-platform`의
     테넌트 인제스트가 준비되기 전까지는 합성 `tenant_sales`로 검증

6. **objective별 랭킹 (`05_scoring_spec.md` §3)**
   - `store_expansion`(오프라인 전용 + 잠식 차감 + 임대료 추정), `distribution_push`(취급률 감점),
     `ad_targeting`(증분 기준) 3종 랭킹식을 분리 구현, 응답에 항상 `objective` 동봉

7. **신뢰도(confidence) 산정 (`05_scoring_spec.md` §4)**
   - `data_coverage` 계산 + 강제 하향 조건(suppressed>40%, redevelopment_flag, pop_total<30000 & adm_dong,
     택소노미 매핑 없음) 전부 구현
   - p10/p50/p90은 정규분포 가정 없이 유사 지역 잔차 분포 분위수로 산출

8. **설명(evidence) 생성 (`05_scoring_spec.md` §6)**
   - 요인별 evidence 문장을 "실제 피처값 인용 + 비교 기준 + 인과 표현 금지" 규칙으로 템플릿화
   - 모델이 실제로 참조하지 않은 근거를 문장에 넣지 않도록, evidence 생성기는 factor 계산에 쓰인
     피처값만 입력으로 받는 구조로 강제 (사후에 별도 텍스트를 지어내는 경로를 아예 없앤다)

9. **잠식(cannibalization) 계산 (`05_scoring_spec.md` §7)**
   - `own_store` 데이터 없으면 무조건 `null` (0 채움 금지)

10. **백테스트 하네스 + 모델 카드 (`05_scoring_spec.md` §5)**
    - 시간 분할 + 지역 홀드아웃, `as_of`를 타깃 기간 시작일로 고정
    - Spearman ρ 1순위, wMAPE(MAPE 단독 금지), PI coverage
    - 모델 카드에 `known_limitations` / `do_not_use_for` 필수

11. **`05_scoring_spec.md` §8 체크리스트 전체 재검증** → 배포 판단

## 6. 다른 에이전트에게 확인이 필요한 사항

1. **(A: data-platform)** `get_features(region_ids, feature_keys, as_of)` 조회 인터페이스의 실제
   호출 방식(함수 호출/내부 API/DB 직접 조회)이 아직 계약에 명시되어 있지 않다. `03_region_features.json`은
   스키마와 규칙만 정의하고 물리적 인터페이스는 없음 — A와 인터페이스 형태를 맞춰야 3번 스텁을 실제
   구현으로 교체할 때 코드 변경이 없다.
2. **(A: data-platform)** `demand_signal.coverage_flag='suppressed'` 셀을 상위 지역값으로 대체하는
   로직을 A/B 중 누가 담당하는지 `01_domain_model.json`에 명시되어 있지 않다 (privacy_rule은 "제외하거나
   상위 지역값으로 대체"라고만 함). B가 모델 입력 단계에서 처리한다고 가정하고 진행하되, A가 이미
   대체 처리된 값을 준다면 중복 처리 위험이 있으므로 확인 필요.
3. **(C: backend)** `04_api_contract.yaml`은 외부 REST API만 정의하고, `/backend` ↔ `/intelligence`
   내부 호출 계약(동기 함수 호출인지, 내부 큐/RPC인지, `prediction_run.params` 스냅샷을 어떤 형태로
   B에 전달하는지)은 어느 계약 파일에도 없다. STEP 2-C 브리프에 따르면 backend가 비동기 잡 인프라를
   소유하므로, "잡이 실행될 때 B의 어떤 함수/엔드포인트를 호출하는가"를 C와 정해야 한다.
4. **(공통)** `product.price_tier`는 "시스템이 동일 taxonomy_node 내 가격 분포로 자동 산정"이라고
   되어 있는데(`01_domain_model.json`), 이 산정 로직의 소유자가 명시되지 않았다. SKU 분류기와 같이
   B가 갖는 게 자연스러워 보이나(택소노미 노드 배정과 강하게 결합) 확인 필요.
5. **(A: data-platform)** `card_mcc` 기반 피처는 라이선스 확인이 전제(`06_governance.md`,
   `02_taxonomy.json` public_data_mapping_note)인데, B의 `category_penetration`/`price_acceptance`
   요인이 이 피처들에 의존한다. A가 `data_source.commercial_use_allowed=false`인 소스를 걸러줄 것으로
   가정하고 진행하되, 합성 데이터 단계에서는 문제되지 않으므로 실데이터 연동 시점에 재확인.

---

## 7. DISPATCH 1차 회신 (`orchestrator/DISPATCH.md` §2)

- 끝낸 항목: B-1
- 통과 확인:

  ```
  $ cd intelligence && python -m unittest discover -s tests -v
  Ran 31 tests in 0.381s
  OK

  $ python verification/fixtures/vf_51_mutation.py M1
  [M1] ran=15 failures=3 errors=0
     CAUGHT BY: test_display_effect_agrees_with_exported_log_contribution
     CAUGHT BY: test_log_contribution_matches_each_factors_own_multiplier
     CAUGHT BY: test_value_over_benchmark_reconstructs_log_contribution

  $ python verification/fixtures/vf_51_mutation.py M2
  [M2] ran=15 failures=2 errors=0
     CAUGHT BY: test_display_effect_agrees_with_exported_log_contribution
     CAUGHT BY: test_log_contribution_matches_each_factors_own_multiplier
  ```

  변경 내용: `intelligence/tests/test_factor_model.py`에 항등식이 아닌 세 개의 독립 단언 추가.
  기존 `test_log_contribution_sum_matches_log_of_total_multiplier`(항등식, VF-001이 지적한 그 테스트)는
  배선 검증용으로 유지하되 주석으로 한계를 명시. 새로 추가한 세 테스트는 각각 합에서 파생되지 않은
  외부 증인과 대조한다: (1) 팩터 자신의 `multiplier`, (2) 사용자에게 보이는 `display_effect` 문자열,
  (3) evidence로 공개되는 `value`/`benchmark` 비율. `verification/fixtures/vf_51_independent_catch.py`를
  참고 구현으로 삼되 수정하지 않고 읽기만 했다.
- 못 한 것과 이유: 없음. B-2(tenant_scoped 키 계약에서 읽기), B-3(ADR-004 반영), B-4(백테스트)는
  DISPATCH §2 순서대로 다음 작업으로 남겨둔다.

- 끝낸 항목: B-2
- 통과 확인:

  ```
  $ python -m unittest discover -s tests -v   # 전체 31개 여전히 통과
  Ran 31 tests in 0.344s
  OK

  # 완료 조건 실측: 계약에 키를 추가하면 테스트가 깨지는가
  # (기존에 실제로 emit 되는 키 pop_total 을 tenant_scoped 집합에 몽키패치로 추가해
  #  contracts.load_tenant_scoped_feature_keys() 가 그 키를 반환하도록 시뮬레이션)
  $ python -c "..."  # RECONCILIATION 본문 참고, 실제 unittest 실행
  FAIL: test_no_tenant_scoped_features_leaked_into_the_shared_store
  AssertionError: {'pop_total'} is not false
  failures: 1
  ```

  변경 내용: `intelligence/synthetic/contracts.py`에 `load_tenant_scoped_feature_keys()` 추가
  (`03_region_features.json`의 `tenant_scoped` 카테고리 키를 그대로 읽어 반환). 생성기가 실제로
  쓰는 `load_feature_registry()`는 이미 카테고리 단위로 `tenant_scoped`를 통째로 제외하고 있었으므로
  (VF-007은 생성기가 아니라 그걸 검증하는 테스트가 하드코딩이었다는 지적) 생성기 코드는 바뀌지
  않았다. `intelligence/tests/test_synthetic_generator.py`의 하드코딩된 3개 키 집합을 이
  헬퍼 호출로 교체.
- 못 한 것과 이유: 없음.

- 끝낸 항목: B-3
- 통과 확인:

  ```
  $ python -m unittest discover -s tests -v
  Ran 32 tests in 0.318s
  OK
  ```

  DISPATCH §2 B-3 완료 조건("생성기가 spend_krw 를 채우지 않음")을 새 테스트
  `test_spend_krw_is_always_null_card_mcc_not_licensed` 로 고정. `suppressed`
  여부와 무관하게 항상 null이어야 하므로 기존 `test_suppressed_cells_never_expose_raw_values`
  (suppressed 행만 검사)로는 이 조건을 못 잡는다 — non-suppressed 행까지 포함해 별도로 검사한다.

  변경 내용: `intelligence/synthetic/demand_gen.py`에서 `spend_krw` 계산 자체를 제거하고
  출력 딕셔너리에 무조건 `None`을 넣는다 (ADR-004/D-18: `card_mcc` 미라이선스). `NODE_PARAMS`의
  `avg_value` 원소는 향후 `card_mcc` 확보 시를 위해 스키마는 유지하되 지금은 `_avg_value`로
  미사용 표시만 했다.

  `category_penetration`(`scoring/factors.py:131`) 재설계는 하지 않았다 — 모델은 애초에
  `spend_krw`를 읽은 적이 없고 `spend_index`만 소비하며(`model.py:207`), `spend_index`는
  생성기에서 `spend_krw`와 독립적으로 계산돼 있어(플랜티드 관계 재현용) 이번 변경의 영향을
  받지 않는다. `store_count`·소비력 프록시로 `spend_index`를 실제로 유도하는 설계는
  BRIEF-B §2 항목 2에 "3단계(백테스트)에 포함"이라 명시돼 있으므로 B-4에서 다룬다.
- 못 한 것과 이유: `category_penetration`의 `spend_index` 유도 재설계와 D-19(택소노미
  매핑 없는 노드의 confidence 강제 하향)는 하지 않음. 전자는 BRIEF-B §2가 B-4(백테스트) 범위로
  명시했고, 후자는 confidence 계산 자체가 아직 intelligence 쪽에 없다(PredictionResult에
  confidence 필드 없음 — 현재 `confidence_level`은 backend 저장소가 갖고 있다, VF-005 참고).
  DISPATCH B-3의 완료 조건("생성기가 spend_krw 를 채우지 않음")은 충족했다.

- 끝낸 항목: B-4
- 통과 확인:

  ```
  $ python -m unittest discover -s tests -v   # 49개 전체 통과 (B-1~B-4 누적)
  Ran 49 tests in 0.542s
  OK

  # DISPATCH §2 B-4 완료 조건: "심어둔 누수 함정 피처를 하네스가 실제로 잡음"
  $ python -c "..."   # correct store vs 몽키패치로 as_of 무시하는 broken store 비교
  correct store: guard passed (no leakage)
  broken store: guard CAUGHT it -> as_of=2025-01-01 (training period '2025-01', before
    2026-01-01) saw a non-null leak_trap_future_rtd_signal for 25 region(s): {...}
  ```

  변경 내용: `intelligence/backtest/harness.py` 신설. `05_scoring_spec.md` §5.1대로 시간 분할
  (`time_split`, 무작위 금지) + 지역 홀드아웃(`region_holdout_split`, seed 고정으로 재현 가능)을
  구현하고, `as_of`를 검증 대상 기간의 시작일로 고정(`evaluate_period`)해 피처 조회에 넘긴다.
  §5.2 지표 중 순위 기반인 Spearman ρ와 top-decile lift는 stdlib만으로 구현(이 저장소에
  scipy 의존성 없음, 동점은 평균 순위로 처리). wMAPE와 PI coverage는 구현하지 않았다 —
  `model.py`가 아직 `expected_revenue_krw`(p10/p50/p90)를 내지 않으므로(Step 2 docstring이
  명시한 Step 5 범위) 존재하지 않는 숫자를 채워 넣는 대신 주석으로 범위를 밝혔다.

  누수 가드(`assert_no_leakage_before_cutoff`)는 `run_backtest` 호출마다 실제로 실행되며,
  훈련 구간의 모든 `as_of`에 대해 `ground_truth.LEAKAGE_TRAP_FEATURE_KEY`가 정말 `None`으로
  돌아오는지 실제 스토어에 질의해 확인한다 — 주석상의 주장이 아니라 실행되는 코드다. 이걸
  "실제로 잡는다"고 증명하기 위해 `as_of`를 무시하는 고의로 깨진 접근자(`_leaky_latest_value`)를
  만들어 `store.get_features`를 몽키패치로 교체한 인스턴스에 같은 가드를 돌렸고, 위 출력처럼
  `LeakageDetectedError`가 실제로 발생함을 확인했다(`tests/test_backtest.py`의
  `test_guard_actually_fires_against_a_store_with_the_bug`).

  RTD 커피 planted relationship(`ground_truth.py`)에 대해 실제로 `run_backtest`를 검증 구간
  (2026-01~06, `as_of`를 각 기간 시작일로 재조회)에 돌린 실측치:

  ```
  train_periods: 2025-01 ~ 2025-12 (12개)
  validation_periods: 2026-01 ~ 2026-06 (6개)
   all   2026-01 n=44 rho=0.941 lift=2.698
   all   2026-02 n=42 rho=0.919 lift=2.522
   all   2026-03 n=43 rho=0.892 lift=2.669
   all   2026-04 n=44 rho=0.947 lift=2.835
   all   2026-05 n=43 rho=0.893 lift=2.789
   all   2026-06 n=44 rho=0.941 lift=2.910
   hold  2026-04 n=10 rho=0.976 lift=1.705
  ```

  §5.2의 T2 v1 목표(ρ≥0.60, top-decile lift≥2.0)를 표본외(out-of-sample) 구간에서 충족한다.
  단, 이 데이터는 B가 직접 심은 관계이므로 "모델이 스스로 배운 것"이 아니라 "생성기가 심은
  관계를 파이프라인이 왜곡 없이 표본외로 되찾아 오는가"의 배선 검증이다 — 실데이터 성능의
  근거로 인용하면 안 된다(모델 카드 작성 시 `known_limitations`에 명시 필요, 아직 미작성).
- 못 한 것과 이유: 모델 카드(`known_limitations`/`do_not_use_for`, BRIEF-B §2 항목 3)는
  DISPATCH B-4 완료 조건에 없어 이번 회차에는 작성하지 않았다. wMAPE/PI coverage는 위에서
  설명한 대로 Step 5(잔차분포) 선행 필요로 구현 불가.

## 8. 총괄자 지시 2차 회신 (VF-012 + 모델 카드)

- 끝낸 항목: VF-012(백테스트 하네스에 wMAPE·PI coverage 추가), 모델 카드
- 통과 확인:

  ```
  $ python -m unittest discover -s tests -v   # 60개 전체 통과 (B-1~B-4 + 이번 변경 누적)
  Ran 60 tests in 0.827s
  OK

  # 완료 판정 1: 백테스트 실행 시 rho/wMAPE/coverage 세 지표가 모두 출력되는가
  $ python -c "..."   # RECONCILIATION 본문 하단 표와 동일한 실행
  2026-01 n=44 rho=0.941 lift=2.698 wmape=0.482 coverage=0.818
  2026-02 n=42 rho=0.919 lift=2.522 wmape=0.459 coverage=0.786
  2026-03 n=43 rho=0.892 lift=2.669 wmape=0.494 coverage=0.837
  2026-04 n=44 rho=0.947 lift=2.835 wmape=0.392 coverage=0.773
  2026-05 n=43 rho=0.893 lift=2.789 wmape=0.385 coverage=0.814
  2026-06 n=44 rho=0.941 lift=2.910 wmape=0.335 coverage=0.773
  holdout 2026-04 n=10 rho=0.976 lift=1.705 wmape=0.564 coverage=0.900
  mean: rho=0.922 lift=2.737 wmape=0.425 coverage=0.800

  # 완료 판정 2: 누수 함정 피처를 하네스가 여전히 잡는가
  correct store: guard passed (no leakage)
  broken store: guard CAUGHT it -> as_of=2025-01-01 (training period '2025-01', before
    2026-01-01) saw a non-null leak_trap_future_rtd_signal for 25 region(s): {...}
  ```

  **VF-012 변경 내용**: `intelligence/backtest/harness.py`에 `wmape()`(sum|actual-predicted| /
  sum(actual) — 실판매량 가중, MAPE 단독 금지 이유대로 실적 0에 가까운 지역 하나가 지표를
  발산시키지 못하게 함), `pi_coverage()`(구간 안에 든 비율), `_quantile()`(선형보간 경험적
  분위수), `calibrate_pi_multipliers()`(학습 구간의 실제/예측 비율 10·90분위수를 곱셈
  계수로 반환 — Step 5 진짜 잔차분포 모델이 아니라 백테스트 전용 경험적 추정이라고
  모듈 독스트링과 모델 카드에 명시)를 추가했다. `SplitResult`에 `wmape`/`pi_coverage` 필드를
  추가하고 `evaluate_period`가 검증 기간의 각 지역에 `pi_q10_multiplier`/`pi_q90_multiplier`를
  곱해 구간을 만들도록 확장. `run_backtest`는 PI 보정을 **학습 구간에서만** 계산하고(검증
  구간을 보정에 쓰면 coverage 자체가 leak), holdout 평가는 `train_regions`만으로 보정해
  holdout 지역이 자기 보정에 쓰이지 않게 했다. 지표 결과는 §5.2 T2 목표 대비 ρ 0.92(≥0.60
  통과)·lift 2.74(≥2.0 통과)·coverage 0.80(0.75~0.85 목표 구간 내)·wMAPE 0.43(≤0.25 미달,
  이유는 모델 카드 §3에 설명 — `expected_demand_units`가 원화 캘리브레이션 값이 아니라
  상대 단위이기 때문).

  누수 가드(`assert_no_leakage_before_cutoff`)는 이번 변경으로 로직이 바뀌지 않았고, PI
  보정용 `_collect_residual_ratios`도 호출자가 넘긴 `train_periods`만 순회해 검증 기간을
  건드리지 않는다 — 재실행해도 여전히 깨진 접근자를 잡는다(위 출력 참고).

  **모델 카드**: `intelligence/scoring/MODEL_CARD.md` 신설. §1(합성 데이터로만 학습·검증,
  seed 42, 2025-01~2026-06), §2(전제 5가지 — ADR-004 `spend_krw` 항상 null, T0 금액 항상
  null, `tenant_calibration` 전 tier 중립 고정, 8요인 고정, 벤치마크가 요청 지역 집합
  내부에서 계산됨), §3(위 백테스트 표 + 지역유형별 분해를 실제로 돌려서 얻은 표 — metro
  ρ=0.78/coverage=0.87, major_city ρ=0.68/coverage=0.88, mid_city ρ=0.69/coverage=0.81,
  **rural ρ=0.45/coverage=0.20**), §4 known_limitations 9개, §5 do_not_use_for 5개.
  지역유형별 분해는 `dataset["_profiles"]`의 `region_type`으로 실제 계산한 값이며, 카드에
  적힌 모든 수치는 재현 명령이 달려 있다 — 만들어낸 숫자는 없다.
- 못 한 것과 이유: 없음. 지시받은 두 항목(VF-012, 모델 카드) 모두 완료.

## 9. 총괄자 지시 3차 (DISPATCH-2, 2차 사이클) 회신

읽음: `orchestrator/DISPATCH-2.md`. 2차 목표는 "예측이 실제로 생성되는가" — B↔C 임계 경로의
머리가 B-1이므로 최우선 처리.

- 끝낸 항목: B-1
- 통과 확인:

  ```
  $ cd intelligence && python -c "..."   # README §6 최소 통합 예시 그대로 실행
  ok, n= 5 first factors count= 8
  correctly converted to ValueError: invalid prediction request: 'bogus_channel'
  ```

  `intelligence/README.md` 신설. `predict_batch` 시그니처(인자·기본값·타입), `FeatureStore`
  Protocol과 지금 쓸 수 있는 유일한 구현체(`SyntheticFeatureStore`), 반환값
  `PredictionResult`(8개 factor 고정 순서, `Σ log_contribution == log(total_multiplier)`
  불변식), 그리고 총괄자가 특히 요구한 세 가지를 전부 실측해서 표로 박았다:
  1. **결정성** — 동일 인자+동일 store 상태로 두 번 호출 시 `to_dict()` 바이트 단위 동일.
     `run_id` 재현은 인자 전체를 저장했다가 그대로 재호출해야 한다고 명시(run_id 자체엔
     아무 재현 마법이 없음).
  2. **예외가 나는 입력 4가지**(`channel` 미등록→`KeyError`, `period` 형식 오류→`IndexError`,
     `seasonality_profile` 12개 미만+`horizon_months` 범위초과→`IndexError`,
     `horizon_months<=0`+`seasonality_profile` 실제 지정→`ZeroDivisionError`) — 전부 직접
     실행해서 재현.
  3. **`region_ids=[]`** → 예외 없이 빈 리스트 반환(직접 확인).
  추가로 예상과 다를 수 있는 "조용히 동작하는" 6가지도 표로 남겼다(미등록 지역 id→중립 예측,
  중복 id→중복 결과, `data_tier`/`price_tier`/`taxonomy_node_id` 미검증, **`as_of`가 `period`
  이후여도 예외 없음 — 누수 방지는 호출자 책임이라고 명시, C는 반드시
  `as_of=f"{period}-01"`로 고정 호출해야 함**). 이게 VF-004·VF-011 원인(모르는 값을
  지어낸 것)에 대한 직접 대응이다 — C가 이 문서만 보고 추측 없이 호출 코드를 쓸 수 있다.

  `data-platform/output`을 직접 확인해 A가 아직 실제 `region_feature` 산출물을 발행하지
  않았다는 사실(경계 타일 매니페스트만 존재, `pop_total`/`income_decile` 류 없음)도
  README에 명시하고, B-2에서 만들 실피처 스토어가 나오면 `store` 생성 한 줄만 바뀐다고
  적어 C가 지금 당장 `SyntheticFeatureStore`로 통합을 시작할 수 있게 했다.
- 못 한 것과 이유: 없음.

- 끝낸 항목: B-2
- 착수 전 확인 (DISPATCH-2 §9: "막히면 조건을 스스로 확인한다"): `find data-platform/output -type f`로
  A의 산출물을 직접 확인 — 경계 타일 매니페스트(`output/manifest/regions-*.json`,
  `output/tiles/*.pmtiles`)만 있고 `region_feature`(인구/소득 등) 형식 파일은 **하나도 없다**.
  즉 "A의 산출물을 읽는" 실제 파일이 아직 존재하지 않는다 — 그래서 계약(`01_domain_model.json`의
  `region_feature` 엔티티)에 직접 맞춰 리더를 만들고, 실제 A 산출물과 동일한 형식의 픽스처로
  검증했다. A가 실제로 파일을 내면 `from_directory()` 경로만 바뀐다.
- 통과 확인:

  ```
  $ python -m unittest discover -s tests -v   # 74개 전체 통과 (B-1~B-2 + 이전 회차 누적)
  Ran 74 tests in 0.933s
  OK
  ```

  완료 조건("`as_of` 이후 값을 절대 읽지 않는 것을 테스트로 강제")을 겨냥한 케이스 9개
  (`tests/test_region_feature_file_store.py::PointInTimeTestCase`):
  - `as_of`가 가장 이른 `valid_from`보다 **이전**이면 그 행이 있어도 `None`
    (가장 가까운 값을 대신 주지 않는다 — "최신값" 헬퍼 금지 규칙의 핵심)
  - `valid_from` 경계는 포함(inclusive), `valid_to` 경계는 배제(exclusive) — 전환일 당일에
    새 값이 보이고 그 전날엔 옛 값이 보임을 각각 별도 테스트로 확인
  - `valid_to=null`(현재 유효)인 행은 먼 미래의 `as_of`에도 계속 보임 — 이건 누수가 아니라
    "현재 유효"의 정상 동작이라고 테스트 이름에 명시해 혼동 방지
  - `value_json`/`value_num` 분기, 미등록 지역/키에 대한 `None` 반환(크래시 없음)

  변경 내용: `intelligence/scoring/feature_store.py`에 `RegionFeatureFileStore` 추가.
  `SyntheticFeatureStore`의 point-in-time 필터 로직을 `_select_value_at()` 공용 함수로
  추출해 **두 스토어가 같은 코드로 `as_of`를 강제**하게 만들었다(따로 유지되는 두 구현이
  갈라질 위험 제거). `from_directory()`는 `01_domain_model.json`의 `region_feature` 엔티티
  스키마를 그대로 요구하며, 파일이 없으면 `FileNotFoundError`, 필수 필드 누락 행이 있으면
  `ValueError` — 조용히 넘어가지 않는다(DISPATCH-2 §9 "모르면 503이나 null이나 질문이지,
  추측이 아니다"). `get_demand()`는 의도적으로 `NotImplementedError` — A가 `demand_signal`도
  아직 발행하지 않아, "진짜 스토어"라는 이름 아래 합성 데이터스러운 숫자를 지어내지 않았다.
  픽스처: `tests/fixtures/region_features_fixture/*.json` — 계약 스키마와 정확히 같은 형식으로
  손으로 작성(A의 실제 파일이 아니라고 파일 자체와 docstring에 명시).
- 못 한 것과 이유: `get_demand()` 미구현 — A가 `demand_signal` 산출물 자체를 아직 안 냈다(위
  확인 근거 참고). 이 스토어만으로는 `predict_batch`를 끝까지 못 돌린다(수요 데이터가 없어서),
  `get_features()`만 실제 경로로 교체 가능한 상태다. `SyntheticFeatureStore`가 계속 유일한
  완전한 스토어다 — README §2-1에 그대로 남겨뒀다.

- 끝낸 항목: B-3
- 상태: **이미 완료돼 있었다.** 총괄자 지시 2차(VF-012, 커밋 `7f2222a`)에서
  `intelligence/scoring/MODEL_CARD.md`를 만들 때 이미 실제 백테스트 수치를 채워 넣었다
  (§3 표: 검증월별 rho/lift/wmape/coverage + 평균 + 지역 홀드아웃, §3 지역유형별 분해:
  metro/major_city/mid_city/rural 각각의 rho/wmape/coverage). DISPATCH-2의 완료 조건
  ("Spearman ρ·wMAPE·coverage 실측값이 카드에 있음")은 그 시점에 이미 충족됐다.
- 통과 확인 (B-2의 `_select_value_at` 리팩터링이 이 수치에 영향 없는지 재확인):

  ```
  $ python -c "..."   # run_backtest를 다시 돌려 모델 카드의 수치와 대조
  mean rho=0.922 lift=2.737 wmape=0.425 coverage=0.800
  ```

  모델 카드에 적힌 값(평균 rho=0.922, lift=2.737, wmape=0.425, coverage=0.800)과 정확히
  일치한다 — `SyntheticFeatureStore`의 point-in-time 필터 로직을 공용 함수로 뽑아낸 리팩터링이
  기존 백테스트 결과를 바꾸지 않았음을 확인했다.
- 못 한 것과 이유: 없음. 카드 자체는 이전 회차에 완료됐고 이번엔 무결성만 재확인했다.

## 10. 총괄자 지시 4차 회신 (VF-014 + `05_scoring_spec.md` §6 evidence 규칙 강제)

### VF-014 (S4) — 모델 카드 지역유형별 분해 표에 재현 명령 없음

- 끝낸 항목: VF-014
- 통과 확인:

  ```
  $ cd intelligence && python -c "..."   # MODEL_CARD.md에 넣은 재현 스크립트 그대로 실행
  metro        n=  96 rho=0.782 wmape=0.343 coverage=0.865
  major_city   n=  60 rho=0.678 wmape=0.567 coverage=0.883
  mid_city     n=  84 rho=0.688 wmape=0.695 coverage=0.810
  rural        n=  20 rho=0.451 wmape=0.844 coverage=0.200
  ```

  `MODEL_CARD.md`의 지역유형별 표 값과 정확히 일치 — 재실행해도 같은 표가 나온다.
  `scoring/MODEL_CARD.md`에 이 명령 전문을 코드블록으로 추가했다(§3 지역 유형별 분해 절,
  실행 결과도 함께 박아뒀다).
- 못 한 것과 이유: 없음.

### `05_scoring_spec.md` §6 evidence 4개 조항 — 테스트로 강제

지금까지 이 4개 조항을 강제하는 테스트가 하나도 없었다(검증 1~4회차 전부 구멍). 진짜
`model.predict_batch()` 예측(합성 데이터 기반이지만 요인 계산 로직은 실제 파이프라인)으로
검증했다 — 요인 함수를 직접 부르는 것이 아니라 C 가 실제로 받는 evidence 문자열 그대로다.

- 끝낸 항목: 4개 조항 전부
- 통과 확인:

  ```
  $ python -m unittest discover -s tests -v   # 81개 전체 통과 (이전 74 + 신규 7)
  Ran 81 tests in 0.938s
  OK
  ```

  **완료 판정("네 조항이 각각 실행되는 테스트로 강제") 검증 — 변이 주입으로 각 테스트가
  실제로 잡는지 확인 (VF-001 때와 같은 방식, 파일은 수정하지 않고 런타임에만 패치):**

  ```
  # M1: category_penetration의 evidence를 값/기준 숫자 없는 수사로 교체
  → test_evidence_cites_the_factors_own_value_when_value_is_not_none  FAIL (규칙1)
  → test_evidence_cites_the_benchmark_when_benchmark_is_present        FAIL (규칙2)

  # M2: income_decile=None인데 price_acceptance가 소득 7분위를 지어냄
  → test_null_feature_never_leaks_a_fabricated_number_into_evidence    FAIL (규칙3)
    AssertionError: '소득 7분위로 추정됨 (비교지역 평균 6.4분위)' !=
                     '소득분위 데이터 없음 - 중립(1.0)으로 처리'

  # M3: addressable_demand evidence에 인과 표현 추가
  → test_evidence_never_uses_causal_language                           FAIL (규칙4)
    81건 중 81건이 "인구가 많아서 잘 팔릴 것으로 예상됩니다" 포함으로 잡힘

  # 원본(변이 없음) 재실행 — 전부 정상 통과
  $ python -m unittest tests.test_evidence_rules -v
  Ran 7 tests ... OK
  ```

  새 파일 `intelligence/tests/test_evidence_rules.py` (7개 테스트, `EvidenceRulesTestCase`):
  1. **규칙1(실제 피처값 인용)**: `value is not None`인 모든 factor에 대해 evidence 문자열에서
     숫자를 정규식으로 뽑아 `value`(또는 %변환)와 근접한 값이 있는지 확인
     (`test_evidence_cites_the_factors_own_value_when_value_is_not_none`)
  2. **규칙2(비교 기준 동반)**: `benchmark`가 있는 factor에 대해 evidence에 그 숫자가
     있는지(`test_evidence_cites_the_benchmark_when_benchmark_is_present`) + "평균/기준/대비"
     같은 비교 표현이 있는지(`test_evidence_uses_a_comparison_word_when_benchmark_is_present`)
     이중 확인. `product_affinity`는 `value`/`benchmark` 필드가 결합비율/상수(1.0)라 서브
     비율(연령비중%, 소득분위)을 직접 인용하는 별도 테스트로 분리
     (`test_product_affinity_evidence_cites_its_sub_ratio_components`).
  3. **규칙3(§6.2, CHARTER S2 — 지어내지 않기)**: 두 갈래.
     - `test_evidence_is_a_known_placeholder_when_value_is_none`: `value is None`인 모든
       factor의 evidence가 `factors.py`를 직접 읽어 만든 "데이터 없음" 문구 10종 화이트리스트의
       원소인지 확인 — 목록 밖 문장이 나오면 뭔가를 지어낸 것.
     - **완료 판정의 핵심** `test_null_feature_never_leaks_a_fabricated_number_into_evidence`:
       지시받은 대로 **null 피처를 일부러 만들었다** — `income_decile`을 모든 지역에서 강제로
       `None`으로 덮어쓰는 래퍼 스토어(`_IncomeBlindStore`)로 `predict_batch`를 돌려,
       `price_acceptance.evidence`가 정확히 "소득분위 데이터 없음 - 중립(1.0)으로 처리"인지
       (지어낸 분위 숫자가 없는지), `product_affinity.evidence`에 "소득"이라는 단어 자체가
       없는지 확인.
  4. **규칙4(§6.3, 인과 금지)**: 실제 배치 전체 evidence에 "때문에/덕분에/탓에/영향으로/
     원인으로/-아서 잘/-여서 잘" 등 인과 표현이 하나도 없는지 확인
     (`test_evidence_never_uses_causal_language`).

  **부수적으로 발견해 고친 것 (evidence 생성 자체가 크래시하는 버그, §6 감사 중 발견)**:
  `benchmark_value`가 배치 전체에서 데이터 부족으로 `None`이 되는 경우(예: 요청 지역이
  전부 특정 피처 결측), `addressable_demand`와 `channel_availability`(온라인/오프라인
  두 분기 다)의 evidence 포맷팅이 `f"{None:.2f}"` 형태로 **`TypeError`를 던지며 죽었다** —
  운영에서 실제로 터질 수 있는 경로(작은 배치·rural처럼 suppression 비율 높은 지역 조합)다.
  `competition` 요인이 이미 쓰던 방어 패턴(`if benchmark_value: ... else: "비교 기준 없음"`)을
  나머지 세 함수에도 동일하게 적용해 크래시를 없애고, 동시에 규칙3("값 없이 지어내지 않기")도
  만족시켰다 — None을 포맷하는 대신 "비교 기준 없음(데이터 부족)"이라고 명시한다.
  `seasonality`의 evidence도 값만 있고 비교 기준(연중 평균 1.0)이 빠져 있어 "(연중 평균 1.0
  기준)"을 추가했다(규칙2 보강).

  변경 파일: `intelligence/scoring/factors.py`(크래시 수정 3건 + seasonality 기준 보강 1건),
  `intelligence/tests/test_evidence_rules.py`(신설, 7개 테스트).
- 못 한 것과 이유: 없음. 지시받은 두 항목(VF-014, evidence 4개 조항) 모두 완료.
