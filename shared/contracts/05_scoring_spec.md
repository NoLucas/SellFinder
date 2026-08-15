# 05. 스코어링 · 설명가능성 규격 (v0.2.0)

> 소유자: jin (사람) · 주 구현자: 에이전트 B · 주 소비자: 에이전트 D
> 선행 문서: `00_product_spec.md`, `03_region_features.json`

---

## 1. 왜 승법(multiplicative) 요인 모델인가

블랙박스 회귀는 성능이 좋아도 기업 고객이 임원 보고에 쓸 수 없습니다.
"87점입니다"로는 아무도 예산을 승인하지 않습니다.

그래서 v1 은 **승법 요인 모델**을 씁니다. 각 요인이 독립적인 배수로 작동하므로
로그를 취하면 덧셈이 되고, 각 요인의 기여도를 정확히 분해해 보여줄 수 있습니다.

```
expected_demand(product, region, channel, period)
    = base_volume(taxonomy_node, channel)
    × f₁ addressable_demand      (지역의 구매 가능 인구 규모)
    × f₂ category_penetration    (그 지역이 이 카테고리를 얼마나 소비하는가)
    × f₃ product_affinity        (제품 속성 ↔ 지역 인구 프로파일 적합도)
    × f₄ price_acceptance        (가격대 ↔ 지역 소득 수용도)
    × f₅ competition             (경쟁 밀도에 의한 감쇄, 항상 ≤ 1)
    × f₆ channel_availability    (그 채널이 지역에 실제로 얼마나 깔려 있는가)
    × f₇ seasonality             (예측 구간의 계절 지수)
    × f₈ tenant_calibration      (자사 실적으로 학습된 보정 배수, T1/T2 만)
```

로그 공간에서:

```
ln(expected_demand) = ln(base) + Σᵢ ln(fᵢ)
```

`ln(fᵢ)` 가 API 응답의 `factors[].log_contribution` 입니다. **합이 반드시 맞아야 합니다.**
맞지 않으면 설명이 거짓이 되고, 그 순간 제품 신뢰가 무너집니다.

### factor_keys (이 8개 외에 만들지 말 것)

| key | label | 범위 | 주 입력 피처 |
|---|---|---|---|
| `addressable_demand` | 수요 규모 | > 0 | pop_total, pop_age_dist, daytime_pop, household_count |
| `category_penetration` | 카테고리 침투율 | > 0 | spend_index_by_node, demand_signal |
| `product_affinity` | 제품 적합도 | > 0 | product.attributes × 지역 인구/소득 프로파일 |
| `price_acceptance` | 가격 수용도 | > 0 | price_tier, income_decile, apartment_price_index |
| `competition` | 경쟁 강도 | **≤ 1** | store_count_by_node, own_share_of_category |
| `channel_availability` | 채널 접근성 | > 0 | 채널별 점포 수, ecommerce_order_density |
| `seasonality` | 계절성 | > 0 | taxonomy_node.seasonality_profile × horizon |
| `tenant_calibration` | 자사 실적 보정 | > 0 | tenant_sales 잔차 모델 (T0 에서는 1.0 고정) |

---

## 2. 데이터 성숙도(Tier)별 동작

| | T0 (자사 데이터 없음) | T1 (일부 지역) | T2 (12개월 × 30지역 이상) |
|---|---|---|---|
| f₁~f₇ | 공개 데이터 기반 | 동일 | 동일 |
| f₈ tenant_calibration | **1.0 고정** | 전역 스케일 + 지역군별 보정 | 테넌트 전용 잔차 모델 |
| `expected_revenue_krw` | **null (금액 추정 금지)** | 제공, 넓은 구간 | 제공, 좁은 구간 |
| `confidence.level` 상한 | `medium` | `high` 가능 | `high` |
| UI 문구 | "상대적 유망도 랭킹" | "추정 매출 (참고용)" | "예측 매출" |

**T0 에서 금액을 추정해 보여주는 것은 이 제품을 죽이는 가장 빠른 방법입니다.**
근거 없는 절대값 한 번이 틀리면 고객은 랭킹까지 통째로 불신합니다.
랭킹은 공개 데이터만으로도 쓸만하지만, 절대값은 그렇지 않다는 걸 UI가 정직하게 말해야 합니다.

---

## 3. objective 별 랭킹 기준

같은 예측값이라도 목적이 다르면 순위가 달라져야 합니다.

### 3.1 `store_expansion` (신규 출점)
```
rank_score = expected_revenue_krw.p50
           × (1 - cannibalization_ratio)      ← 기존 자사 매장 잠식 차감
           - estimated_monthly_cost           ← avg_rent × 면적 + 인건비 추정
```
- 오프라인 채널에서만 유효
- `custom_catchment` 레벨 권장 (행정동 경계는 실제 상권과 다름)
- `store_close_rate_12m` 이 높은 지역은 리스크 플래그

### 3.2 `distribution_push` (유통 확대)
```
rank_score = expected_units.p50 × (1 - current_distribution_coverage)
```
- 이미 취급률이 높은 지역은 추가 여지가 적으므로 감점
- `own_distribution_points` 가 없으면 이 objective 의 정확도가 크게 떨어짐 → 경고 노출

### 3.3 `ad_targeting` (지역 광고)
```
rank_score = expected_incremental_units × unit_margin_krw / estimated_cpm_cost
```
- **증분(incremental)** 이 핵심. 이미 잘 팔리는 지역에 광고하면 낭비
- 온라인 채널에서는 `ecommerce_order_density` 가 지배적

> **함의:** `prediction.opportunity_score` 는 objective 에 따라 계산식이 다르다.
> 따라서 서로 다른 objective 의 점수를 비교하면 안 되며, API 응답에 항상 objective 를 함께 반환한다.

---

## 4. 신뢰도(confidence) 산정

```
data_coverage = Σ(사용된 피처의 비결측 가중 비율) / Σ(요구 피처 가중치)
```

| 조건 | level |
|---|---|
| data_coverage ≥ 0.80 **AND** comparable_region_count ≥ 15 **AND** tier ≥ T1 | `high` |
| data_coverage ≥ 0.55 **AND** comparable_region_count ≥ 5 | `medium` |
| 그 외 | `low` |

**강제 하향 조건** (하나라도 걸리면 `low`):
- 해당 지역 `demand_signal.coverage_flag = 'suppressed'` 비율 > 40%
- `redevelopment_flag = true`
- `pop_total < 30,000` 이면서 `region_level = adm_dong`
- taxonomy_node 에 공개데이터 코드 매핑이 없음

### 예측 구간 (p10/p50/p90)
- T1/T2: 유사 지역 홀드아웃 잔차 분포의 분위수로 산출. 정규분포 가정 금지 (매출은 우편향).
- 구간이 p50 대비 ±60% 를 넘으면 UI 에서 금액 대신 랭킹만 강조하도록 플래그를 내린다.

---

## 5. 백테스트 & 모델 카드 (기업 도입 실사 대응)

### 5.1 분할 규칙
- **무작위 분할 절대 금지.** 시간 기준 분할 필수 (예: ~2025-12 학습 / 2026-01~06 검증)
- 지역 홀드아웃 병행: 학습에 전혀 없던 지역에서의 성적을 별도 보고
- `as_of` 를 타깃 기간 시작일로 고정해 피처 누수 차단 (`03_region_features.json` 참조)

### 5.2 필수 지표

| 지표 | 왜 필요한가 | v1 목표 (T2) |
|---|---|---|
| **Spearman ρ** | 기업은 절대값보다 **순위**로 의사결정한다. 가장 중요한 지표. | ≥ 0.60 |
| Top-decile lift | 상위 10% 추천 지역이 평균 대비 몇 배인가 | ≥ 2.0 |
| wMAPE | 금액 추정 오차 (매출 가중) | ≤ 0.25 |
| Coverage of PI | p10~p90 구간이 실제값을 포함한 비율 (목표 80%) | 0.75 ~ 0.85 |

MAPE 단독 사용 금지 — 소규모 지역에서 폭발해 지표가 무의미해집니다.

### 5.3 모델 카드에 반드시 포함할 것
- 지역 유형별 성적 분해 (수도권 / 광역시 / 중소도시 / 군지역)
- Tier 별 성적 분해
- `known_limitations` 와 **`do_not_use_for`** — 이걸 안 쓰면 고객이 오용하고 그 책임이 우리에게 옵니다

---

## 6. 설명(evidence) 작성 규칙 — 에이전트 B 필독

`factors[].evidence` 는 사용자가 그대로 보고서에 붙여넣는 문장입니다.

**반드시 지킬 것**
1. 실제 피처값을 인용한다. `"20~30대 인구 15.2만명, 주간활동인구비 1.34"` ✅
2. 비교 기준을 함께 준다. `"RTD커피 소비지수 138 (전국 평균 100)"` ✅
3. 데이터 시점을 알 수 있게 한다 (`data_freshness` 필드와 함께).

**금지**
1. 값 없는 수사. `"이 지역은 매우 유망합니다"` ❌
2. 모델이 실제로 쓰지 않은 근거를 지어내는 것 ❌ — 감사 대상입니다.
3. 인과 주장. `"인구가 많아서 잘 팔릴 것입니다"` 는 상관을 인과로 말하는 것. → `"인구 규모가 상위 3%로, 유사 프로파일 지역 23곳에서 평균 대비 1.5배 실적을 보였습니다"` ✅

---

## 7. 잠식(cannibalization) — 출점 의사결정의 핵심

신규 출점 예측에서 가장 자주 틀리는 부분입니다. 예상 매출이 높아도 그 매출의 상당 부분이
기존 자사 매장에서 옮겨온 것이면 회사 전체로는 이익이 없습니다.

```
cannibalization_ratio = Σ over 자사매장 s within radius:
                          overlap(catchment_new, catchment_s) × decay(distance)
estimated_uplift_ratio = 1 - cannibalization_ratio
```

- `own_store` 데이터가 없으면 이 값을 계산할 수 없다 → `cannibalization: null` 로 명시하고
  UI 에서 "기존 매장 정보를 등록하면 잠식 위험을 계산할 수 있습니다" 를 안내한다.
- 절대 0 으로 채우지 말 것. "잠식 없음"과 "모름"은 다릅니다.

---

## 8. 실패 모드 체크리스트 (배포 전 반드시 확인)

- [ ] 요인 로그 기여도의 합이 최종 예측 배수의 로그와 일치하는가 (오차 < 1e-6)
- [ ] T0 테넌트 응답에 `expected_revenue_krw` 가 null 인가
- [ ] `competition` 요인이 1을 초과하는 케이스가 없는가
- [ ] 온라인 채널 예측에 `foot_traffic` / `competitor_density` 가 들어가지 않았는가
- [ ] 학습 시 `as_of` 가 타깃 기간 이후로 설정된 케이스가 없는가 (누수 검사)
- [ ] `suppressed` 셀의 원시값이 응답 어디에도 노출되지 않는가
- [ ] 동일 `run_id` 재실행 결과가 100% 동일한가
- [ ] 인구 3만 미만 행정동이 상위 랭킹을 독식하지 않는가 (소표본 과대추정 검사)
