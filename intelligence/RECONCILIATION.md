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
