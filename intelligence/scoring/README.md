# scoring/ — 8요인 승법 모델 골격 (2단계 산출물)

`05_scoring_spec.md` §1의 8-factor multiplicative model. `factors.py`가 각 요인을,
`model.py`가 이를 지역 배치 단위로 오케스트레이션한다.

## 범위 (중요 — 이 단계에서 안 만든 것)

이 모듈은 **요인 분해 자체만** 구현한다. 의도적으로 빠진 것:

- `opportunity_score` (0~100 정규화 랭킹) — objective별 랭킹식(§3)과 묶여 있어 6단계 범위
- `expected_revenue_krw` 실제 추정치 (p10/p50/p90) — 3단계 백테스트의 잔차 분포가 있어야
  하므로 5단계 범위. 지금은 T0/T1/T2 관계없이 항상 `None`이고, `assert_t0_revenue_null()` 가드가
  "T0에는 항상 null"을 강제한다 (5단계에서 T1/T2용 실제 추정치를 넣기 시작해도 이 가드는 그대로
  살아있어야 한다 — T0 케이스에서 실수로 값이 들어가면 즉시 예외).
- SKU 자동 분류기 — `taxonomy_node_id`/`price_tier`를 아직 함수 인자로 직접 받는다 (4단계에서
  실제 `product` 도메인 객체로 교체).
- `tenant_calibration`은 T0/T1/T2 관계없이 지금은 전부 1.0 중립 (T1/T2 잔차 모델은 5단계).

## 사용

```python
from scoring import model
from scoring.feature_store import SyntheticFeatureStore
from synthetic.generate import generate_all

dataset = generate_all(seed=42, start_period="2025-01", end_period="2026-06")
store = SyntheticFeatureStore.from_dataset(dataset)

results = model.predict_batch(
    region_ids=store.all_adm_dong_ids(),
    taxonomy_node_id="TX-FOOD-BEV-COFFEE-RTD",
    channel="cvs",
    period="2025-06",
    as_of="2025-06-01",
    data_tier="T0",
    store=store,
    product_attributes={"target_age": ["20s", "30s"], "sugar_free": True},
    price_tier="mid",
    seasonality_profile=[0.92, 0.90, 0.98, 1.02, 1.08, 1.14, 1.18, 1.16, 1.04, 0.96, 0.92, 0.90],
    horizon_months=1,
)
```

`store`는 `FeatureStore` 프로토콜(`feature_store.py`)만 만족하면 되므로, `/data-platform`이
실제 구현체를 내놓으면 `SyntheticFeatureStore`를 그걸로 바꿔 끼우기만 하면 된다 — `model.py`는
`get_features(region_ids, feature_keys, as_of)` / `get_demand(region_ids, node, channel, period)`
두 메서드 외에는 아무것도 요구하지 않는다.

## 벤치마크는 "요청 결과 집합 내"

모든 요인은 `value / benchmark` 형태의 비율이고, `benchmark`는 **이번 호출에 넘긴
`region_ids` 집합의 평균**이다 — 코드에 박힌 고정 전국 평균이 아니다. `01_domain_model.json`의
`opportunity_score` 정의("요청 결과 집합 내 정규화")와 같은 스코핑을 요인 단위에도 그대로
적용한 것. 즉 같은 지역도 어떤 지역 집합과 비교되느냐에 따라 요인값이 달라진다 — 이건 버그가
아니라 설계다.

## 불변식 (tests/test_factor_model.py)

`05_scoring_spec.md` §8 체크리스트 중 이 단계가 담당하는 6개 전부 테스트로 옮겼다:

1. `Σ factors[].log_contribution == ln(total_multiplier)`, 오차 < 1e-6
2. `competition` 요인은 항상 ≤ 1
3. 온라인 채널은 `foot_traffic`/`competitor_density` 미사용 (competition은 중립 고정,
   channel_availability는 이커머스 주문밀도 사용)
4. T0 → `expected_revenue_krw` null (가드 함수가 실제로 예외를 던지는지까지 검증)
5. 동일 입력 재실행 시 100% 동일 출력 (딥카피 입력으로 숨은 mutation도 검사)
6. 인구 3만 미만 행정동이 상위 랭킹을 독식하지 않음

추가로: `synthetic/`이 1단계에서 심어둔 `rtd_coffee_young_affluent` 관계(20-30대 비중 상위
25%+소득7분위이상 → RTD커피 spend_index 1.6배)가 실제로 `category_penetration` 요인을 통해
모델에서 복원되는지도 검증한다 — "심은 계수를 모델이 복원해내는가"라는 2단계 검증 기준을
자동화한 것.

as_of 누수 검사(학습 시 미래 피처 사용 여부)는 여기 없다 — 3단계 백테스트 하네스의 역할이고,
그때 1단계의 `leak_trap_future_rtd_signal`을 써서 검증한다.

## 남은 이슈

`base_volume()`이 지금은 `synthetic.demand_gen.NODE_PARAMS`를 재사용한다 — 커스텀 10개
노드 밖에서는 `_DEFAULT_TXN_RATE_PER_1000POP`라는 대략치로 대체된다. 실제 서비스에서는
이 기준선 자체도 데이터 기반으로 다시 잡아야 한다 (지금은 "요인이 기준선 대비 몇 배인가"를
검증하는 게 목적이라 기준선의 절대 정확도는 2단계 범위 밖).
