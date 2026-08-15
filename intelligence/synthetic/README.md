# synthetic/ — SellFinder 합성 데이터 생성기 (1단계 산출물)

`/intelligence` STEP 2 1단계. `03_region_features.json`의 `feature_registry`를 그대로 따르는
지역 피처 + `demand_signal`을 만드는 생성기다. `/data-platform`이 실데이터를 내기 전까지
**A의 출력 목표 형식이자 C·D의 mock 데이터 소스**로 쓰라고 설계했다.

의존성 없음(표준 라이브러리만 사용) — `pip install` 없이 바로 실행된다.

## 빠르게 쓰기

이미 커밋된 `sample/` 디렉토리를 그냥 읽으면 된다:

```
sample/regions.json          # sido/sigungu/adm_dong 63개 (계층 구조)
sample/region_features.json  # 28,200행. 01_domain_model.json의 region_feature 필드 그대로
sample/demand_signal.json    # 27,000행. 01_domain_model.json의 demand_signal 필드 그대로
sample/data_sources.json     # data_source 레지스트리 (전부 commercial_use_allowed=true, 합성)
sample/ground_truth.json     # 심어둔 관계 + 누수 함정 스펙 (아래 참조)
sample/manifest.json         # 생성 파라미터, 행 수, 권장 백테스트 분할 경계
```

직접 다른 파라미터로 재생성하려면 (예: 기간을 늘리고 싶을 때):

```bash
cd intelligence
python -m synthetic.generate --start-period 2023-01 --end-period 2026-06 --seed 7 --out-dir /tmp/bigger
```

인자 없이 실행하면 `sample/`과 **바이트 단위로 동일한** 결과가 나온다(`seed=42` 고정).
Python에서 직접 쓰려면:

```python
from synthetic.generate import generate_all
dataset = generate_all(seed=42, start_period="2025-01", end_period="2026-06")
# dataset["regions"], ["region_features"], ["demand_signal"], ["ground_truth"], ["manifest"]
```

## 다른 에이전트가 mock으로 쓰는 법

- **C (backend)**: `/predictions/{run_id}/regions`, `/regions/{region_id}/profile` 같은 엔드포인트를
  아직 `/intelligence`가 실제 예측을 못 주는 동안 mock으로 채워야 한다면, `region_features.json`을
  그대로 읽어서 `04_api_contract.yaml`의 example 응답 형태로 얇게 변환해서 반환하면 된다.
  `regions.json`의 `region_id`를 path param으로 그대로 쓸 수 있다.
- **D (console)**: 지도/지역상세 화면 mock 데이터 소스로 `region_features.json` + `demand_signal.json`을
  바로 fetch해서 쓸 수 있다. `manifest.json`의 `curated_taxonomy_nodes` 10개 중 하나를 골라 화면을
  채우면 된다 (전체 택소노미가 아니라 이 10개만 `demand_signal`이 있다 — 아래 "범위" 참조).
- **A (data-platform)**: 실제 피처 스토어를 만들 때 이 출력이 **목표 스키마**다. 특히
  `valid_from`/`valid_to` 체이닝 방식(연속 구간, 마지막 행만 `valid_to=null`)과 결측을 `null`로
  두는 방식(0으로 채우지 않음)을 그대로 따라야 `/intelligence`가 나중에 실데이터로 바꿔 꽂아도
  코드 변경이 없다.

## 스키마 매핑

`region_features.json`의 각 행:
```json
{"region_id": "91001001", "feature_key": "pop_total", "value_num": 214830.0, "value_json": null,
 "valid_from": "2025-01-01", "valid_to": "2025-02-01", "source_id": "src_syn_public",
 "ingested_at": "2026-06-01T00:00:00Z"}
```
`01_domain_model.json`의 `region_feature` 엔티티 필드와 1:1. 문자열형 피처(`trade_area_grade` 등,
`03_region_features.json`에 `"type": "string"`인 것들)는 `value_json: {"value": "B"}`로 감싸서 넣었다 —
`region_feature`에 `value_str` 필드가 없어서 그렇다. `redevelopment_flag`(boolean)는 `value_num`에
0.0/1.0으로 넣었다 (같은 이유).

`demand_signal.json`의 각 행은 `01_domain_model.json`의 `demand_signal` 엔티티 필드와 1:1.

## 범위 — 왜 전체가 아니라 일부인가

- **지역 50개** (`region_gen.py`의 `SIDO_DEFS`에 하드코딩): 4가지 합성 지역유형(metro/major_city/
  mid_city/rural)에 걸쳐 인구 1,800명~52만명까지 극단적으로 분포시켰다. 개수를 늘리고 싶으면
  `SIDO_DEFS`를 직접 넓히면 된다 (`--regions` 플래그는 없음 — 계층 구조 전체를 다시 설계해야 하므로
  숫자 하나로 스케일하지 않는다).
- **`demand_signal` 대상 택소노미 노드 10개** (`demand_gen.py`의 `CURATED_NODES`): 전체 36개 leaf
  노드 전부를 채우면 (지역50×노드36×채널평균3×기간18) 대략 30만 행이 되어 커밋하기엔 과하다.
  심어둔 관계 5개(RTD커피/HMR/이유식/대형가전/반려용품)가 걸린 노드 + 대비군 5개만 골랐다.
  다른 노드가 필요하면 `demand_gen.NODE_PARAMS`/`CHANNEL_MIX`에 추가하고 재생성하면 된다.
- **기간 18개월 (2025-01~2026-06)**: `05_scoring_spec.md` §5.1 예시("~2025-12 학습 / 2026-01~06
  검증")와 정확히 같은 경계를 쓰도록 골랐다. `manifest.json`의 `suggested_backtest_split`이 이 경계를
  그대로 담고 있다.

## ground_truth.json — 심어둔 관계

랜덤 데이터가 아니라 정답을 심었다. 5개 관계 전부 `02_taxonomy.json`의 실제 노트에 근거한다
(예: HMR 노드의 "1인가구 비중·야간 유동인구와 상관 높음"). 각 관계는:

- 어떤 지역이 조건을 만족하는지 (분위수 컷오프를 **실제 생성된 지역 집합에 대해 구체적인 숫자로
  해석**해서 `resolved_cutoff_value` + `qualifying_region_ids`로 저장 — quantile이 아니라 이미 계산된
  실제 값이므로 이 JSON만 보고도 검증 가능하다.)
- 그 지역들의 `demand_signal.spend_index`에 곱해진 배수(`multiplier`)

2단계(요인 모델)를 만들 때 이 파일로 **모델이 심어둔 배수를 복원하는지** 검증해야 한다
(`tests/test_synthetic_generator.py`의 `test_planted_relationships_are_recoverable_in_spend_index`가
생성기 자체는 이미 이렇게 검증하고 있다 — 노이즈/계절성 때문에 정확히 배수와 일치하진 않지만
방향과 대략적 크기는 항상 나온다).

## 누수 함정 (leakage trap)

`leak_trap_future_rtd_signal`이라는 **가짜** `feature_key`가 하나 있다 — `03_region_features.json`의
`feature_registry`에 없는, 존재해서는 안 되는 피처다. `valid_from=2026-01-01`(검증 구간 시작) 이전에는
**행 자체가 없다**. 값은 각 지역의 2026-01~06(검증 구간, 즉 미래) RTD커피 `spend_index`에서 유도했다 —
실무에서 실수로 "이번 분기 실적" 컬럼을 과거 학습 데이터에 조인해버리는 사고를 흉내낸 것이다.

3단계(백테스트 하네스)가 `get_features(..., as_of=...)`를 제대로 구현했다면 `as_of < 2026-01-01`인
학습 구간에서는 이 피처가 **아예 존재하지 않는 것으로** 나와야 한다. 만약 "최신값 가져오기" 같은
잘못된 헬퍼를 쓰면 이 피처가 미래 정보를 그대로 흘려서, 학습 구간 백테스트 Spearman ρ가 비정상적으로
1.0에 가깝게 나온다 — 그게 감지 신호다. 자세한 메커니즘은 `ground_truth.py`의
`LEAKAGE_TRAP_*` 독스트링 참조.

## 결측

모든 결측은 `value_num`/`value_json`을 `null`로 남긴다 (`0`으로 채우지 않음 —
`03_region_features.json`의 `feature_quality_rules` 위반이 되므로). 요금이 많이 드는/라이선스가
걸린 피처(유동인구, 카드소비)일수록, 그리고 군지역(rural)일수록 결측률을 더 높였다 — 실제
데이터 수집 현실을 흉내낸 것이다. `demand_signal`은 셀당 점포 5개 미만 또는 거래 50건 미만이면
`coverage_flag='suppressed'`로 두고 원시값(`spend_krw`/`transaction_count`/`store_count`/`spend_index`)을
전부 `null` 처리한다 (`01_domain_model.json`의 `demand_signal.privacy_rule`).

## 합성 지역 식별 방법

`region_id`는 시도코드 91/92/93으로 시작한다 — 실제 행정표준코드는 91xx를 쓰지 않으므로
(실제 코드는 11, 26-31, 36, 41-52) 절대 실데이터와 충돌하지 않는다. 지역명(예: "한빛특별시",
"늘봄해솔동")도 전부 가상 지명이다. 이 데이터를 실제 지역 통계로 오인하지 않도록 주의.

## 테스트

```bash
cd intelligence
python -m unittest discover -s tests -v
```

불변식 15개 검증: 등록된 feature_key만 쓰는지, 결측이 0으로 채워지지 않았는지, `valid_from`/
`valid_to`가 겹치지 않고 체이닝되는지, 누수 함정이 컷오프 이전에 정말 없는지, 인구 분포가
요구된 극단(30,000 미만 ~ 400,000 초과)을 커버하는지, suppressed 셀에 원시값이 없는지, 심어둔
관계가 실제로 복원 가능한지, 동일 시드 재실행이 100% 동일한 결과를 내는지 등.
