# intelligence — 진입점 (C가 읽어야 하는 전부)

`backend`(C)가 실제 예측을 만들려면 이 문서 하나만 보고 호출 코드를 쓸 수 있어야 한다.
아래는 전부 `intelligence/scoring/model.py`·`intelligence/scoring/feature_store.py`를 직접
실행해서 확인한 사실이다 — 추측이나 설계 의도가 아니다. 재현 명령은 각 절에 붙어 있다.

---

## 1. 호출 시그니처

```python
from scoring import model
from scoring.feature_store import SyntheticFeatureStore  # 지금 쓸 수 있는 유일한 FeatureStore 구현체

results: list[model.PredictionResult] = model.predict_batch(
    region_ids: list[str],                    # 필수. 빈 리스트 허용 (§4-1 참고)
    taxonomy_node_id: str,                     # 필수. 02_taxonomy.json의 leaf node_id
    channel: str,                              # 필수. 02_taxonomy.json channels의 channel_id
    period: str,                               # 필수. "YYYY-MM" (예: "2025-06")
    as_of: str,                                # 필수. "YYYY-MM-DD" (예: "2025-06-01")
    data_tier: str,                            # 필수. "T0"/"T1"/"T2" (검증 안 함, §4-3 참고)
    store: FeatureStore,                       # 필수. 아래 §2
    product_attributes: dict | None = None,    # 선택. 예: {"target_age": ["20s","30s"], "premium_ingredient": True}
    price_tier: str = "mid",                   # 선택. "value"/"mid"/"premium"/"luxury" (검증 안 함, §4-3 참고)
    seasonality_profile: list[float] | None = None,  # 선택. 정확히 12개 원소 (1월~12월), §4-2 참고
    horizon_months: int = 1,                   # 선택. 1 이상이어야 함, §4-2 참고
    calibration_profile: tenant_layer.TenantCalibrationProfile | None = None,  # 선택. T1/T2 전용, §5-1
) -> list[model.PredictionResult]
```

호출 1건 = 예측 키 (제품 × 지역 × 채널 × 기간) 중 **채널·기간·제품(taxonomy_node_id)을 고정하고
지역 여러 개를 한 번에 스코어링**한 것. `region_ids`에 넣은 지역마다 `PredictionResult` 1개가
그 순서대로(§3) 반환된다.

## 2. `store` — FeatureStore

`intelligence/scoring/feature_store.py`의 `Protocol`:

```python
class FeatureStore(Protocol):
    def get_features(self, region_ids: list[str], feature_keys: list[str], as_of: str) -> dict[str, dict[str, object]]: ...
    def get_demand(self, region_ids: list[str], taxonomy_node_id: str, channel: str, period: str) -> dict[str, dict[str, object]]: ...
```

**구현체는 지금 두 개다.** 둘 다 같은 `Protocol`을 구현하므로 C 쪽 호출 코드는 `store` 생성
한 줄만 바뀌면 된다.

### 2-1. `SyntheticFeatureStore` — 지금 당장 통합·데모에 쓸 수 있는 유일한 완전한 스토어

```python
from synthetic import generate
from scoring.feature_store import SyntheticFeatureStore

dataset = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
store = SyntheticFeatureStore.from_dataset(dataset)
```

`get_features`와 `get_demand`를 모두 구현한다 — `predict_batch`를 지금 당장 끝까지 돌릴 수 있는
유일한 스토어다.

### 2-2. `RegionFeatureFileStore` — A(data-platform)의 실제 산출물을 읽는 리더 (B-2, 2026-08-16 추가)

```python
from scoring.feature_store import RegionFeatureFileStore

store = RegionFeatureFileStore.from_directory("data-platform/output/region_features")
```

**주의: `get_demand()`는 아직 `NotImplementedError`를 던진다.** A가 `region_feature`
(인구/소득 등)는 물론 `demand_signal`도 아직 발행하지 않았다(2026-08-16 기준,
`find data-platform/output -type f`로 직접 확인 가능 — 경계 타일 매니페스트만 있다).
`region_feature` 파일 형식은 `01_domain_model.json`의 `region_feature` 엔티티(`region_id`,
`feature_key`, `value_num`, `value_json`, `valid_from`, `valid_to`, `source_id`,
`ingested_at`)를 그대로 따르는 JSON 배열이며, 디렉터리 안의 `*.json` 전부를 읽는다.
**A가 실제로 이 형식의 파일을 내는 순간 `from_directory()`의 경로만 바꾸면 된다** —
`as_of` 필터링은 `SyntheticFeatureStore`와 완전히 동일한 코드(`_select_value_at`)를 쓴다.
파일이 하나도 없으면 `FileNotFoundError`, 필수 필드가 빠진 행이 있으면 `ValueError` —
조용히 넘어가지 않는다. 검증: `intelligence/tests/test_region_feature_file_store.py`
(픽스처는 `tests/fixtures/region_features_fixture/`, `as_of` 강제를 9개 케이스로 검증).

## 3. 반환값 — `PredictionResult`

```python
@dataclass
class PredictionResult:
    region_id: str
    taxonomy_node_id: str
    channel: str
    period: str
    data_tier: str
    factors: list[dict]              # 정확히 8개, FACTOR_KEYS 순서 고정 (아래)
    total_log_multiplier: float
    total_multiplier: float
    expected_demand_units: float     # 원화 아님. §5 참고
    expected_revenue_krw: dict | None  # 지금은 항상 None (Step 5 전까지, §5 참고)

    def to_dict(self) -> dict: ...   # JSON 직렬화용. C는 /scores·/regions 응답을 만들 때 이걸 쓴다.
```

`factors`의 각 원소(`to_dict()` 기준)는 `{"key", "label", "log_contribution", "display_effect",
"value", "benchmark", "evidence"}`. `key`는 항상 이 순서·이 8개:

```
addressable_demand, category_penetration, product_affinity, price_acceptance,
competition, channel_availability, seasonality, tenant_calibration
```

**`Σ factors[].log_contribution == log(total_multiplier)`가 항상 성립**(오차 < 1e-6,
`05_scoring_spec.md` D-04). `results`의 순서는 **입력한 `region_ids`의 순서와 동일**하다
(내부에서 재정렬하지 않음).

## 4. 결정성 보장과 예외 — 지어내지 말고 이걸 봐라

모든 항목은 아래 재현 명령으로 실제로 실행해 확인했다 (`cd intelligence` 후 실행):

### 4-1. 결정성 (`run_id` 재실행 관점)

`predict_batch`는 순수 함수다 — **동일한 인자 + 동일한 `store` 데이터 상태**로 두 번 호출하면
`[r.to_dict() for r in a] == [r.to_dict() for r in b]`가 바이트(값) 단위로 참이다. 숨겨진 난수나
시간 의존성이 없다. **C가 같은 `run_id`를 재실행해서 같은 결과를 보장하려면, 그 run을 만들 때
쓴 인자 전부(위 §1 시그니처)를 저장해뒀다가 그대로 다시 넘겨야 한다** — `run_id`만으로는 재현이
안 된다, 인자가 재현의 전부다. `store`가 가리키는 데이터가 그 사이 바뀌면(예: A가 새 빈티지를
발행) 결과도 달라진다 — 이건 버그가 아니라 `as_of` 시점 정합성이 정상 동작한 것이다.

```python
a = model.predict_batch(region_ids=ids, taxonomy_node_id=node, channel=ch, period=p,
                         as_of=af, data_tier="T0", store=store, seasonality_profile=prof)
b = model.predict_batch(region_ids=ids, taxonomy_node_id=node, channel=ch, period=p,
                         as_of=af, data_tier="T0", store=store, seasonality_profile=prof)
assert [r.to_dict() for r in a] == [r.to_dict() for r in b]  # True
```

### 4-2. 예외가 나는 입력 — try/except로 감싸야 하는 것들

| 입력 | 결과 |
|---|---|
| `channel`이 `02_taxonomy.json`의 channels에 없는 값 | `KeyError` |
| `period`가 `"YYYY-MM"` 형식이 아님 (예: `"2025"`) | `IndexError` |
| `seasonality_profile`을 줬는데 12개 미만이고, `horizon_months`가 그 범위를 넘는 달을 요구 | `IndexError` |
| `horizon_months <= 0` (0 또는 음수) **그리고** `seasonality_profile`을 실제로 줌 | `ZeroDivisionError` |

**C는 이 4가지를 잡아 사용자에게 400을 돌려줘야 한다** — 지금 `predict_batch`는 이걸
검증하지 않고 그대로 예외를 던진다. 방어는 호출자(C) 책임이다.

### 4-3. 예외가 나지 않고 조용히 "동작"하는 것들 (예상과 다를 수 있는 것)

| 입력 | 실제 동작 |
|---|---|
| `region_ids = []` | 예외 없이 **빈 리스트 반환** |
| `region_ids`에 저장소에 없는 지역 id | 예외 없이, 그 지역은 **모든 피처가 None → 중립(1.0) 요인들로 예측 생성** (틀린 게 아니라 "정보 없음"으로 처리됨) |
| `region_ids`에 중복 id | 예외 없이 **중복 그대로 결과에 두 번 나옴** (C가 dedup 안 하면 `/scores`에 같은 지역이 두 줄 나간다) |
| `data_tier`가 `"T0"`/`"T1"`/`"T2"`가 아닌 임의 문자열 | 검증 안 함 — `"T0"`가 아니면 전부 T1/T2와 동일하게 취급(중립 보정) |
| `price_tier`가 `_PRICE_TIER_SENSITIVITY`(value/mid/premium/luxury)에 없는 값 | 검증 안 함 — `"mid"`와 동일한 민감도(0.55)로 조용히 처리 |
| `taxonomy_node_id`가 `NODE_PARAMS`에 없는 노드 | 검증 안 함 — 기본 거래율(`_DEFAULT_TXN_RATE_PER_1000POP`=40)로 대체, 예외 없음 |
| `as_of`가 `period`보다 미래(정상적으로는 `period` 시작일이어야 함) | **검증 안 함, 예외 없음.** `store.get_features`가 그 `as_of` 시점 기준으로 정상 조회한다 — 누수 방지는 `as_of`를 올바르게 넘기는 호출자 책임이다. C는 반드시 `as_of = f"{period}-01"`로 고정해서 호출해야 한다 (`05_scoring_spec.md` §5.1). |

**T0에서 `expected_revenue_krw`는 절대 `None`이 아닌 값이 나올 수 없다** — `assert_t0_revenue_null()`이
코드 레벨에서 강제한다(현재는 모든 tier에서 항상 `None`, §5 참고). 이건 예외가 아니라 불변식이다.

## 5. 지금 이 모델이 안 하는 것 (Step 5 전까지 구조적으로 없음)

- **`expected_revenue_krw`는 항상 `None`.** T0라서가 아니라 아직 Step 5(잔차분포 캘리브레이션)가
  없어서다 — T1/T2도 마찬가지다. C는 이 필드가 채워질 거라 가정하고 코드를 짜면 안 된다.
- **`expected_demand_units`는 원화가 아니라 상대적 수요 단위**다 (`base_volume()`의 임의 상수
  기반). `/scores` 응답의 점수·랭킹 소스로는 쓸 수 있지만 금액으로 표시하면 안 된다.
- **`opportunity_score`(퍼센타일 랭킹)는 여기서 계산되지 않는다.** `region_ids` 전체 집합
  내에서의 상대 순위가 필요하면 C가 `total_multiplier` 기준으로 직접 정렬해야 한다.
- **`tenant_calibration`(f8)은 `calibration_profile`을 안 주면 모든 tier에서 중립(1.0)
  고정**이다. T1/T2에서 실제 보정을 반영하려면 §5-1을 봐라 — 자동으로 되지 않는다.

### 5-1. T1/T2 보정 (`calibration_profile`, 2026-08-17 추가)

`predict_batch`/`predict_one`에 `calibration_profile` 키워드 인자를 추가로 받는다
(`scoring.tenant_layer.TenantCalibrationProfile | None`, 기본값 `None`=중립).
**`store`(공용 FeatureStore)와는 완전히 별개 경로다** — `region_ids`/`taxonomy_node_id`/
`channel`/`period`/`as_of` 등 나머지 인자는 이전과 똑같이 동작하고, `calibration_profile`은
오직 f8(`tenant_calibration`)에만 영향을 준다. f1~f7은 이 인자가 있든 없든 바이트 단위로
동일하다(`tests/test_tenant_isolation.py`가 실제로 검증).

```python
from scoring import tenant_layer

# 1단계: 테넌트의 과거 실적(sales_rows)과, 그 시점에 공용 모델(calibration 없이)이
#        예측했을 baseline을 짝지어 프로파일을 학습한다. C는 sales_rows를 이미
#        access token에서 나온 tenant_id로만 필터링해서 넘겨야 한다 — 이 함수는
#        tenant_id를 받지 않고 더 가져올 방법도 없다(06_governance.md §1.4).
baseline_by_region_period = {
    (row.region_id, period): row.expected_demand_units
    for period in past_periods
    for row in model.predict_batch(region_ids=..., period=period, as_of=f"{period}-01",
                                    data_tier="T2", store=store)  # calibration_profile 없이
}
profile = tenant_layer.fit_tenant_calibration(
    sales_rows=tenant_sales_rows,  # [{"region_id","period","units_sold","distribution_points","is_outlier"}, ...]
    baseline_by_region_period=baseline_by_region_period,
    data_tier="T2",
)  # 표본이 부족하면 None을 반환한다 — 억지로 배수를 만들지 않는다

# 2단계: 실제 예측 요청에 프로파일을 그대로 넘긴다.
results = model.predict_batch(region_ids=..., period="2026-07", as_of="2026-07-01",
                               data_tier="T2", store=store, calibration_profile=profile)
```

`fit_tenant_calibration`은 표본이 3건 미만이면 `None`을 반환한다 — `predict_batch`에
`calibration_profile=None`을 넘기면(또는 그냥 생략하면) `tenant_calibration`이 중립(1.0)으로
처리된다(크래시 없음). **한 번 학습한 `profile`을 매 예측 요청마다 재사용해라** —
`fit_tenant_calibration`을 요청마다 다시 부르지 마라, 무겁고 매번 같은 결과가 나온다.

## 6. 최소 통합 예시

```python
from scoring import model
from scoring.feature_store import SyntheticFeatureStore
from synthetic import generate

_dataset = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
_store = SyntheticFeatureStore.from_dataset(_dataset)  # 프로세스당 한 번만

def run_prediction(region_ids, taxonomy_node_id, channel, period, data_tier):
    as_of = f"{period}-01"  # 반드시 기간 시작일 (§4-3)
    try:
        return model.predict_batch(
            region_ids=region_ids, taxonomy_node_id=taxonomy_node_id, channel=channel,
            period=period, as_of=as_of, data_tier=data_tier, store=_store,
        )
    except (KeyError, IndexError, ZeroDivisionError) as e:
        raise ValueError(f"invalid prediction request: {e}") from e  # C가 400으로 변환
```

## 7. 백테스트·모델 카드

Step 3 백테스트 하네스: `intelligence/backtest/harness.py`, 테스트: `intelligence/tests/test_backtest.py`.
모델 카드(무엇으로 학습했는지, 어떤 전제가 깔려 있는지, 어디서 틀리기 쉬운지):
`intelligence/scoring/MODEL_CARD.md` — **C/D 모두 프로덕션에 붙이기 전에 필독**, 특히 §4 known_limitations.
