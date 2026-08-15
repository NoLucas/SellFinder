# RECONCILIATION — Data Platform (Agent A)

작성 시점: 2026-08-15. `shared/contracts/README.md`, `00_product_spec.md`, `01_domain_model.json`,
`02_taxonomy.json`, `03_region_features.json`, `06_governance.md`, `AGENT_BRIEFS.md` STEP 1을 읽고 작성.

STEP 2 (역할별 지시)는 아직 착수하지 않았다. 이 문서는 리컨실 보고만 담는다.

---

## 1. 지금까지 만든 것 (구 `/data-pipeline`)

기존 작업은 "지역별 상권/인구/소비 데이터 수집·정제" 지시를 받아 진행됐고, 신규 계약이 오기 전
`dataset_schema.proposal.json`을 자체 제안으로 만들어 썼다.

- `config/regions.yaml`, `config/.env.example` — 수집 대상 지역 목록(법정동 코드 10자리 기준), API 키 환경변수 예시
- `src/collectors/base.py`, `commercial_district.py`, `population.py`, `consumption.py` — 상권/인구/소비 3개 도메인 수집기. 전부 API 미연동, 결정론적 mock 데이터로 파이프라인 흐름만 검증
- `src/processors/normalize.py`, `merge.py` — 기준일 정규화, 결측/음수 정제, 지역당 상권+인구+소비 통합 레코드 병합
- `src/schema/dataset_schema.proposal.json`, `validator.py`, `proposed_changes.md` — 자체 제안 스키마(지역 단위 flat record) + 검증기
- `src/pipeline.py` — 엔트리포인트, `output/dataset_2026-08-01.json` 샘플 산출물
- `tests/test_schema_validator.py`
- `docs/cross_team_contract_alignment.md` — 구 계약(`dataset_schema.json`이 매물 단위임을 발견) 시점에 작성한 3팀 불일치 정리 문서. 지금은 `shared/contracts/00_product_spec.md`가 그 불일치를 공식적으로 해소한 상태로 보이며, 이 문서는 배경 기록으로만 남긴다.

## 2. 새 계약과 일치하는 것 → 유지

- **지역을 시도/시군구/행정동 3단계 계층으로 다루는 기본 구조**는 `03_region_features.json`의 `region_hierarchy`와 방향이 같다. `regions.yaml`의 지역 목록 자체는 시드 데이터로 재사용 가능.
- **"지역 단위 공개 데이터를 상권/인구/소비 세 도메인으로 수집한다"는 기본 축**은 새 계약의 `region_feature` 카테고리(`commercial`, `population`, `income_spend`, `traffic_access`)와 `demand_signal`의 원천 그대로다. 도메인 분류 자체는 버릴 필요 없음.
- **`collectors/base.py`의 수집기 추상화 패턴**(소스별 `BaseCollector` 서브클래스, mock/실API 분기)은 `data_source` 레지스트리 체계 아래서도 구조적으로 재사용 가능.
- **출처 추적 개념**(`source_meta.sources`, `collected_at`) 자체의 필요성은 `06_governance.md` §3의 `data_source`·`source_id` 필수 규칙과 일치한다. 형식은 리팩터링 필요(§3 참조).

## 3. 계약과 어긋나는 것 → 리팩터링 방향

1. **region_id 체계 불일치**: 현재 법정동 코드(10자리)를 그대로 region_id로 씀. 계약은 행정표준코드 기반 `adm_dong`(8~10자리)이고, 행정구역 개편 대응을 위한 `region_code_mapping(old_id, new_id, effective_date, split_ratio)` 테이블을 요구한다. → region_id 발급 체계를 행정표준코드로 정렬하고, 법정동/행정동 코드 차이가 있는지부터 확인 후 매핑 테이블 신설.
2. **데이터 모델이 통짜 레코드 vs 시점정합 피처**: `dataset_schema.proposal.json`은 "지역 1개 = reference_date 시점의 상권+인구+소비 스냅샷 1행"이다. 계약의 `region_feature`는 `(region_id, feature_key, valid_from, valid_to)`별 개별 행 + `as_of` 조회를 요구한다(`point_in_time_rule`). → `pipeline.py`/`merge.py`의 "지역당 1개 통합 JSON" 접근을 피처별 append-only 적재로 전면 재작성해야 한다.
3. **결측 처리 정책 위반**: `processors/normalize.py`의 `clean_numeric_breakdown`이 `None`/음수를 **0으로 치환**한다. 계약(`feature_quality_rules`)은 "결측을 0으로 채우지 마라, null로 두고 결측 인디케이터를 모델이 학습하게 하라"고 명시적으로 금지한다. → 0 치환 로직 제거, null 유지로 변경. 음수 방어(데이터 오류)와 결측(모름)을 구분해서 처리해야 함.
4. **업종 분류가 자유 텍스트**: `commercial_district.py`의 `category_breakdown`이 "음식점/카페/소매/미용/..." 같은 자유 텍스트 키다. 계약은 `02_taxonomy.json`의 `ksic_codes`/`sbiz_codes`/`card_mcc` 코드로 매핑된 `taxonomy_node_id` 기준을 요구한다. → 자유 텍스트 카테고리 폐기, 택소노미 코드 매핑으로 전환.
5. **소비 데이터가 절대금액 위주**: `consumption.py`가 `total_sales_amount` 절대값을 그대로 다룬다. 계약은 절대 소득/소비가 라이선스 제한 있는 소스가 많다는 전제로 `spend_index`(전국 대비 지수)를 1차 필드로 두고, 절대금액(`card_spend_per_capita` 등)은 `license_check: true`로 별도 표시한다. → 라이선스 확인 전에는 지수 중심으로 설계하고, 절대금액 필드는 `data_source.commercial_use_allowed` 확인 전까지 프로덕션 경로에서 배제.

## 4. 계약에 없어서 버려야 하는 것

- **`src/schema/dataset_schema.proposal.json` 자체**: 지역 단위 flat record 구조 전체가 새 계약(`region_feature` + `demand_signal`)과 근본적으로 다른 모델이라 재사용 불가. 파기하고 새 계약 기준으로 다시 설계한다.
- **`src/schema/proposed_changes.md`**: 구 스키마(존재하지도 않았던 `dataset_schema.json`) 대비 변경 제안이라 지금은 무의미. 삭제하거나, 새 계약 대비 변경이 필요해지면 그때 `CONTRACT_CHANGE_REQUEST.md` 형식으로 새로 쓴다.
- **`processors/merge.py`의 "지역당 통합 레코드" 병합 방식**: §3-2와 동일한 이유로 개념 자체가 폐기 대상. 병합이 아니라 피처별 개별 적재로 바뀐다.

## 5. 계약에 있는데 아직 없는 것 → 작업 순서

`AGENT_BRIEFS.md` STEP 2-A의 의존성 순서를 그대로 따른다: **region → region_feature(인구/소득 최소셋) → taxonomy 매핑 → demand_signal → tenant 인제스트**

1. **region 모델**: sido/sigungu/adm_dong 구축(행정표준코드), `region_code_mapping` 신설. 경계(GeoJSON)는 API 응답에 안 실음 — 별도 저장/벡터타일 전제로 설계.
2. **region_feature 스토어**: `feature_registry`에 등록된 키만, `valid_from/valid_to/source_id/ingested_at` 필수, `get_features(region_ids, keys, as_of)` 인터페이스, "최신값" 헬퍼 금지, 결측 null 유지. 지금은 전혀 없음(§3-2, §3-3 리팩터링과 사실상 동시 작업).
3. **택소노미 매핑**: `02_taxonomy.json`의 ksic/sbiz/card_mcc로 공개 데이터를 `(region × taxonomy_node × channel × period)` 격자로 정규화. 지금은 자유 텍스트 카테고리뿐이라 처음부터 구축.
4. **demand_signal + k-익명성 마스킹**: 셀당 점포 5개 또는 거래 50건 미만 시 `coverage_flag='suppressed'`, 원시값 비노출. 지금 mock 수집기엔 이 로직이 전혀 없음 — 실데이터 연동 전 필수 선행 구현.
5. **tenant_sales 인제스트**: CSV/XLSX 매핑, 비동기 잡, PII 컬럼 감지 시 잡 전체 거부, `distribution_points` 없으면 경고. 완전히 새로 만들어야 함(구 `/data-pipeline`에 대응물 없음).
6. **data_source 레지스트리**: `license`/`commercial_use_allowed` 필수, source_id 없는 값은 인제스트 단계에서 거부. 구조는 있으나(`source_meta`) 계약이 요구하는 필드(`commercial_use_allowed`, `refresh_cadence`, `known_limitations`)는 없음.

## 6. 다른 에이전트/사람에게 확인이 필요한 사항

- **(B) intelligence 팀**: `03_region_features.json`의 `feature_registry`가 5개 카테고리·20여 개 키를 정의하는데, "인구/소득 최소셋" 착수 순서에서 05_scoring_spec.md의 8개 factor_key 중 어떤 것이 최우선인지 알아야 우선순위를 정할 수 있다. 어떤 피처부터 채워야 백테스트 하네스를 먼저 검증할 수 있는지 확인 필요.
- **(C) backend 팀**: tenant_sales 인제스트에서 파일 파싱/PII 감지/컬럼 매핑을 data-platform이 담당하고 backend의 `import_job` 큐잉·webhook과 어떻게 연결되는지 경계가 명확하지 않다. data-platform이 잡 처리 로직을 콜백/라이브러리로 제공하고 backend가 잡 자체를 소유하는 형태인지 확인 필요.
- **jin(계약 오너)**: 구 `/data-pipeline`이 mock으로 만들어 둔 업종 대분류(자유 텍스트)를 `02_taxonomy.json`에 매핑할 때 `ksic_codes`와 `sbiz_codes` 중 어느 걸 1차 매핑 기준으로 삼을지(둘 다 taxonomy_node에 병존) 정해줘야 한다.
- **라이선스/소스 확정**: 구 `README.md`가 이미 밝혔듯 상권/인구/소비 3개 소스 모두 실제 API 키·엔드포인트 미연동 상태이며, 특히 카드 소비 데이터는 `commercial_use_allowed` 확인이 안 된 상태다. 새 계약 하에서도 이 미확정 상태는 그대로 남아 있다 — 소스 확정이 여전히 data-platform 범위 밖의 선행 조건.
- **구 계약 파일의 처리**: `shared/contracts/dataset_schema.json`, `prediction_api.json`(매물 단위, `/model`·`/backend`가 이미 구현해서 씀)이 신규 00~06 계약과 함께 저장소에 남아 있다. `AGENT_BRIEFS.md`/`README.md`의 읽기 순서 표에는 이 두 파일이 언급되지 않는다. 이 둘이 신규 계약으로 완전히 대체(deprecated)된 것인지, 아니면 별도로 유지되는 것인지 data-platform 범위는 아니지만 전체 정합성을 위해 확인이 필요해 보여 기록해 둔다.

---

**요약**: 구 `/data-pipeline`의 도메인 지식(상권/인구/소비를 지역 단위로 본다는 것 자체)과 수집기 추상화 구조는 재사용 가능하지만, 데이터 모델(통짜 레코드 → 시점정합 피처), 결측 처리(0 치환 → null), 카테고리 체계(자유 텍스트 → 택소노미 코드)는 전면 리팩터링 대상이다. tenant_sales 인제스트, k-익명성 마스킹, region_code_mapping은 완전히 새로 만들어야 한다. 기존 코드는 삭제하지 않았다.
