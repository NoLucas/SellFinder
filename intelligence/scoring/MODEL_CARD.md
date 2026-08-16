# 모델 카드 — SellFinder 8-요인 승법 모델 (Step 2/3, T0 tier)

`05_scoring_spec.md` §5.3이 요구하는 문서. 이 모델을 붙이거나 그 출력을 보고 의사결정하기
전에 반드시 읽어야 한다. 아래 수치는 전부 `intelligence/backtest/harness.py`로 실제로 돌려서
얻은 값이다 — 추정치나 목표치가 아니다. 재현 명령은 각 절에 붙여뒀다.

---

## 1. 무엇으로 학습/검증했는가

**전부 합성(synthetic) 데이터다. 실거래 데이터는 단 한 건도 쓰지 않았다.**

- 생성기: `intelligence/synthetic/generate.py`, `seed=42`, 기간 `2025-01`~`2026-06` (18개월)
- 지역: 전국 sido/sigungu/adm_dong 계층을 합성으로 생성 (실제 행정구역 좌표·이름 사용,
  인구·소득·점포수 등 속성값은 `region_type`(metro/major_city/mid_city/rural)별 분포에서 샘플링)
- 상품: 10개 큐레이션 택소노미 노드(`synthetic/demand_gen.py`의 `NODE_PARAMS`) 중
  5개는 `synthetic/ground_truth.py`에 명시적으로 심어둔 관계(planted relationship)를 가짐,
  나머지 5개는 대조군(관계 없음)
- 채널: `02_taxonomy.json`의 채널 정의를 그대로 사용 (오프라인/온라인/B2B)
- 백테스트: `05_scoring_spec.md` §5.1대로 시간 분할(2025-01~12 학습 / 2026-01~06 검증,
  무작위 분할 아님) + 지역 홀드아웃(seed 42, 20%), `as_of`를 각 검증 기간 시작일로 고정

## 2. 깔려 있는 전제

1. **ADR-004 / `DECISIONS.md` D-18: `demand_signal.spend_krw`는 항상 `null`이다.**
   `card_mcc`가 라이선스 미확보 상태라 원화 매출 신호의 근거가 없다. `category_penetration`
   요인은 `spend_index`(0~100+ 지수)만 쓰고, 이 지수 자체도 `store_count`·소비력 프록시로
   유도해야 한다는 설계는 아직 미착수다(현재 합성 생성기는 planted relationship 재현을 위해
   `spend_index`를 직접 심어 놓은 값이다 — 실데이터 전환 시 이 부분이 가장 먼저 바뀐다).
2. **T0 테넌트는 금액을 절대 추정하지 않는다 (`DECISIONS.md` D-03).**
   `expected_revenue_krw`는 항상 `null`이며 `assert_t0_revenue_null()`이 코드 레벨에서 강제한다.
   아래 백테스트는 전부 `expected_demand_units`(원화가 아닌 상대적 수요 단위)를 대상으로 한다.
3. **`tenant_calibration`(f8)은 T0/T1/T2 전부 중립(1.0) 고정이다** (`scoring/factors.py`).
   실적 기반 보정(Step 5, 잔차분포 모델)이 아직 없다. 이 모델 카드의 모든 지표는 "테넌트
   실적을 전혀 반영하지 않은" 상태의 성적이다.
4. **8개 요인은 계약(`05_scoring_spec.md` §1)에 고정**돼 있고 추가·개명 불가.
5. 벤치마크(`value/benchmark` 비율의 분모)는 **요청된 지역 집합 내부**에서 계산된다
   (`model.py`의 `_compute_benchmarks`) — 고정된 전국 평균 상수가 아니다. 즉 같은 지역이라도
   함께 조회한 지역 집합이 다르면 점수가 달라질 수 있다.

## 3. 백테스트 결과 (표본외, out-of-sample)

재현:
```
cd intelligence
python -c "
from backtest import harness
from scoring.feature_store import SyntheticFeatureStore
from synthetic import generate
dataset = generate.generate_all(seed=42, start_period='2025-01', end_period='2026-06')
store = SyntheticFeatureStore.from_dataset(dataset)
result = harness.run_backtest(dataset, store, taxonomy_node_id='TX-FOOD-BEV-COFFEE-RTD',
    channel='cvs', train_cutoff='2026-01',
    product_attributes={'target_age': ['20s','30s'], 'sugar_free': True},
    seasonality_profile=[0.92,0.90,0.98,1.02,1.08,1.14,1.18,1.16,1.04,0.96,0.92,0.90])
for s in result['all_regions']:
    print(s.period, s.n_regions, s.spearman_rho, s.top_decile_lift, s.wmape, s.pi_coverage)
"
```

대상: `TX-FOOD-BEV-COFFEE-RTD`(RTD 커피, planted relationship 보유) × `cvs` 채널.
학습 2025-01~12 / 검증 2026-01~06, `as_of`를 각 검증월 1일로 고정해 재조회.

| 검증월 | n | Spearman ρ | Top-decile lift | wMAPE | PI coverage |
|---|---|---|---|---|---|
| 2026-01 | 44 | 0.941 | 2.698 | 0.482 | 0.818 |
| 2026-02 | 42 | 0.919 | 2.522 | 0.459 | 0.786 |
| 2026-03 | 43 | 0.892 | 2.669 | 0.494 | 0.837 |
| 2026-04 | 44 | 0.947 | 2.835 | 0.392 | 0.773 |
| 2026-05 | 43 | 0.893 | 2.789 | 0.385 | 0.814 |
| 2026-06 | 44 | 0.941 | 2.910 | 0.335 | 0.773 |
| **평균** | | **0.922** | **2.737** | **0.425** | **0.800** |
| 지역 홀드아웃(2026-04, n=10) | 10 | 0.976 | 1.705 | 0.564 | 0.900 |

§5.2 T2 v1 목표 대비: **ρ 0.92 ≥ 0.60 통과**, **lift 2.74 ≥ 2.0 통과**,
**coverage 0.80 — 목표 구간(0.75~0.85) 안**, **wMAPE 0.43 — 목표(≤0.25) 미달**.

wMAPE가 목표를 넘는 이유는 알려진 것이다: `expected_demand_units`는 원화로 캘리브레이션된
값이 아니라 `base_volume()`의 임의 상수(`NODE_PARAMS`의 `txn_rate`)에 8요인 배수를 곱한
**상대적** 단위다. PI 밴드(`calibrate_pi_multipliers`)도 이 배후 학습 구간의 실제/예측 비율
10·90분위수로 만든 **백테스트 전용 경험적 추정**이며, Step 5의 진짜 테넌트 보정 모델이 아니다
— coverage가 목표 구간에 들어온 것은 이 경험적 보정이 자기 자신을 상대로 잘 작동한다는
뜻이지, 실데이터에서도 그렇다는 보장은 아니다.

### 지역 유형별 분해

같은 백테스트를 `region_type`(metro/major_city/mid_city/rural)별로 나눠 검증 기간 전체를
합산한 결과:

| 지역 유형 | n | Spearman ρ | wMAPE | PI coverage |
|---|---|---|---|---|
| metro (수도권) | 96 | 0.782 | 0.343 | 0.865 |
| major_city (광역시) | 60 | 0.678 | 0.567 | 0.883 |
| mid_city (중소도시) | 84 | 0.688 | 0.695 | 0.810 |
| rural (군지역) | 20 | 0.451 | 0.844 | **0.200** |

재현 명령 (VF-014 — 위 표는 §3의 `run_backtest` 표와 달리 지역 단위로 직접 계산해야 해서
별도 스크립트다. `dataset["_profiles"]`의 `region_type`으로 그룹화하고, `q10`/`q90`은 §3와
같은 방식으로 학습 구간에서 보정한다):

```
cd intelligence
python -c "
from backtest import harness
from scoring import model
from scoring.feature_store import SyntheticFeatureStore
from synthetic import generate

dataset = generate.generate_all(seed=42, start_period='2025-01', end_period='2026-06')
store = SyntheticFeatureStore.from_dataset(dataset)
profiles = dataset['_profiles']
region_type_by_id = {rid: p['region_type'] for rid, p in profiles.items()}

node='TX-FOOD-BEV-COFFEE-RTD'; channel='cvs'
train_periods, val_periods = harness.time_split(dataset['manifest']['periods'], '2026-01')
q10,q90 = harness.calibrate_pi_multipliers(store, store.all_adm_dong_ids(), node, channel, train_periods,
    product_attributes={'target_age':['20s','30s'],'sugar_free':True},
    seasonality_profile=[0.92,0.90,0.98,1.02,1.08,1.14,1.18,1.16,1.04,0.96,0.92,0.90])

from collections import defaultdict
by_type_pred = defaultdict(list)
by_type_act = defaultdict(list)
by_type_cov = defaultdict(list)

for period in val_periods:
    as_of = period + '-01'
    results = model.predict_batch(region_ids=store.all_adm_dong_ids(), taxonomy_node_id=node, channel=channel,
        period=period, as_of=as_of, data_tier='T0', store=store,
        product_attributes={'target_age':['20s','30s'],'sugar_free':True}, price_tier='mid',
        seasonality_profile=[0.92,0.90,0.98,1.02,1.08,1.14,1.18,1.16,1.04,0.96,0.92,0.90], horizon_months=1)
    for r in results:
        act = harness._actual_transaction_count(store, r.region_id, node, channel, period)
        if act is None: continue
        rt = region_type_by_id.get(r.region_id, 'unknown')
        by_type_pred[rt].append(r.expected_demand_units)
        by_type_act[rt].append(act)
        lo, hi = r.expected_demand_units*q10, r.expected_demand_units*q90
        by_type_cov[rt].append(1 if lo<=act<=hi else 0)

for rt in by_type_pred:
    n=len(by_type_pred[rt])
    rho = harness.spearman_rho(by_type_pred[rt], by_type_act[rt]) if n>=2 else float('nan')
    wm = harness.wmape(by_type_pred[rt], by_type_act[rt])
    cov = sum(by_type_cov[rt])/n
    print(f'{rt:12s} n={n:4d} rho={rho:.3f} wmape={wm:.3f} coverage={cov:.3f}')
"
```

실행 결과 (2026-08-16 재확인, `git log -1`이 `01_domain_model.json`·`scoring/`·`synthetic/`을
바꾸지 않는 한 값이 그대로여야 한다 — `seed=42`로 고정돼 있으므로):

```
metro        n=  96 rho=0.782 wmape=0.343 coverage=0.865
major_city   n=  60 rho=0.678 wmape=0.567 coverage=0.883
mid_city     n=  84 rho=0.688 wmape=0.695 coverage=0.810
rural        n=  20 rho=0.451 wmape=0.844 coverage=0.200
```

**rural은 명백히 가장 약하다.** 표본이 작고(n=20) suppression 비율이 높아 스코어링에 쓸 수
있는 셀 자체가 적다 — PI coverage 0.20은 예측구간이 사실상 실제값을 못 담는다는 뜻이다.

### Tier 별 분해

**T0만 검증됐다.** 위 모든 수치는 `data_tier='T0'`로 돌린 것이다. T1/T2는 `tenant_calibration`이
아직 중립(1.0) 고정이라(§2-3) 별도로 검증할 대상 자체가 없다 — T1/T2 테넌트에게 보여주는 점수는
현재 T0와 수학적으로 동일한 배수를 쓰고 있다는 뜻이며, 이건 결함이 아니라 Step 5 미착수 상태다.

## 4. 알려진 한계 (`known_limitations`)

1. **전부 합성 데이터로만 검증했다.** 실제 판매/유동인구/소비 데이터로 이 성적이 재현된다는
   보장이 없다 — 특히 `spend_index`가 합성 생성기에서 planted relationship을 직접 심어 만든
   값이라, 실데이터에서 `store_count`·소비력 프록시로 유도했을 때는 신호가 이보다 약할 수 있다.
2. **`spend_krw`는 항상 `null`이다 (ADR-004).** 원화 매출 신호가 전혀 없다 — `card_mcc` 라이선스
   확보 전까지는 구조적 한계다.
3. **`expected_revenue_krw`는 항상 `null`이다 (T0, D-03).** 위 백테스트는 상대적 수요 단위
   기준이며, 원화 캘리브레이션 성적이 아니다.
4. **PI 밴드는 Step 5 모델이 아니라 백테스트 전용 경험적 추정이다** (`harness.calibrate_pi_multipliers`).
   실서비스에 노출할 신뢰구간의 근거가 아직 아니다.
5. **`rural` 지역 유형에서 성적이 크게 떨어진다** (ρ 0.45, PI coverage 0.20). 표본 부족과
   suppression 비율이 원인으로 보이나 근본 처방은 아직 없다.
6. **10개 큐레이션 노드 중 5개(대조군)는 planted relationship이 없어 이 백테스트로 검증되지
   않는다.** 위 표는 관계가 심어진 RTD 커피 노드 하나에 대한 것이다 — 다른 9개 노드에 대해
   일반화된다는 보장이 없다.
7. **T1/T2 tier는 검증 대상 자체가 없다** (§3 참고, `tenant_calibration` 미구현).
8. **`suppressed` 셀은 스코어링에서 완전히 제외된다**(0으로도 채우지 않음). 이건 규칙을
   지킨 것이지만, suppression 비율이 높은 지역(특히 rural)일수록 표본이 얇아져 지표 자체의
   신뢰도가 떨어진다 — 위 rural 행이 그 예다.
9. **evidence 문장의 "인과 금지"/"근거 없는 수사 금지" 규칙(§6)은 아직 자동 강제 테스트가
   없다** — 현재는 요인 계산에 쓰인 피처만 evidence에 넣는 구조로만 방지하고 있다(코드 구조상
   방지, 텍스트 규칙 검증 테스트는 없음).

## 5. 이걸로 하면 안 되는 것 (`do_not_use_for`)

1. **실제 원화 매출액 추정.** `expected_revenue_krw`가 항상 `null`인 T0 tier로는 절대 못 한다.
2. **`rural` 지역 유형에 대한 단독 의사결정.** PI coverage 0.20은 예측구간을 신뢰구간으로
   보여줄 근거가 없다는 뜻이다 — 이 지역 유형에서는 상대 랭킹조차 다른 유형보다 신뢰도가 낮다.
3. **RTD 커피 이외 9개 노드에 대해 위 백테스트 수치를 그대로 인용.** 노드별로 별도 검증 없이
   "이 모델은 ρ 0.92다"라고 일반화하면 안 된다.
4. **실데이터 전환 전까지 이 카드의 수치를 프로덕션 SLA/계약 근거로 사용.** 전부 합성 데이터
   기준이다(§4-1).
5. **T1/T2 테넌트의 실적 반영 여부를 이 카드로 판단.** 아직 검증 대상이 없다(§3).

---

작성 근거: `intelligence/backtest/harness.py`, `intelligence/tests/test_backtest.py`.
재현 불가능한 수치는 이 카드에 올리지 않았다 — 전부 위 명령으로 다시 뽑을 수 있다.
