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

> 이 문서 상단은 STEP 1(리컨실) 시점 기록으로 낡았다 — STEP 2 경계 타일 파이프라인(boundary_tiles)은 그 뒤 커밋에서 실제로 만들어졌다. 아래는 `orchestrator/DISPATCH.md` 1차 지시(A-1~A-5) 실행 결과다.

---

## 7. DISPATCH 1차 (A-1~A-5) 실행 결과 · 2026-08-16

지시 근거: `orchestrator/DISPATCH.md` §1, `shared/contracts/ADR-005-tile-join-key.md`, `DECISIONS.md` D-11/D-12/D-13/D-20.
지시된 순서(A-1→A-2→A-3→A-4→A-5, A-3 이 A-4 보다 먼저) 그대로 실행했다.

- **끝낸 항목**: A-1, A-2, A-3, A-4, A-5
- **통과 확인**:
  - A-1 — `git ls-files data-platform/output/manifest` → `regions-sido-2026-01-01.json`, `regions-sido-2026-07-01.json` (비어 있지 않음). `git ls-files 'data-platform/**/*.pmtiles'` → `data-platform/fixtures/regions-sigungu-fixture.pmtiles` 단 1건(A-4 픽스처 예외뿐, `output/tiles/` 아래 실 아티팩트는 0건).
  - A-2 — `data-platform/.venv/Scripts/python.exe verification/fixtures/vf_56_tile_probe.py` 대신 (해당 스크립트가 참조하는 `output/tiles/*.pmtiles` 자체를 새 파이프라인으로 재빌드 후) 직접 디코드 확인: 재빌드된 `regions-sido-2026-01-01.pmtiles`, `regions-sigungu-fixture.pmtiles` 모두 피처 `properties`에 `region_id` 원문 문자열 존재. `pytest tests -q` 의 `test_build_vintage_end_to_end` 가 `"region_id" in feat["properties"]` 를 단언하며 통과. 매니페스트 엔트리에 `id_map_path` 없음.
  - A-3 — 신규 테스트 `test_build_fails_when_feature_id_property_missing_from_tile` 통과: `region_id` 속성을 제거한 피처로 빌드 시 `TileJoinKeyVerificationError` 발생 확인. 수동 재현으로도 동일 결과 확인(별도 스크립트, region_id 제거 → 빌드 실패). `pytest tests -q` → **7 passed**.
  - A-4 — `data-platform/fixtures/regions-sigungu-fixture.pmtiles`(250 피처, 386KB, 5MB 이하) + `manifest-fixture.json`(`boundary_vintage: "fixture"`) 생성. `backend/samples/scores.json` 이 쓰는 5개 region_id(`41135`,`11650`,`11680`,`28245`,`41461`) 전부 실제 타일 디코드로 확인됨(`region_id` 속성 매칭). `python tools/validate_contracts.py --check-manifest data-platform/fixtures/manifest-fixture.json` → **오류 0건**.
  - A-5 — 레벨 산출 순서를 `LEVEL_BUILD_ORDER = ("sigungu", "adm_dong", "sido")` 로 `build.py` 에 명시. 이번 사이클에서 처음 새로 낸 레벨이 `sigungu`(A-4 픽스처)로, 순서 그대로 이행. `sido` 는 기존에 이미 나가 있던 두 빈티지를 새 파이프라인(A-2/A-3 반영)으로 재빌드만 함 — 새로 만들지 않음. `adm_dong` 은 아직 소스 경계 데이터가 없어 이번 사이클 대상 아님(§5 순서상 다음 작업).
- **못 한 것과 이유**:
  - `adm_dong` 레벨의 실제/픽스처 빌드 — 소스 GeoJSON 경계 데이터가 아직 없다(§5 "region 모델" 선행 작업 미착수). A-5 는 순서만 지시했지 이 사이클에 adm_dong 산출을 요구하지 않았다.
  - `python tools/validate_contracts.py --base origin/master --agent A` — 실행하면 오류 21건이 뜨지만, 전부 `backend/`, `intelligence/`, `shared/contracts/`, `tools/` 파일이고 `data-platform/` 은 0건이다(`git diff --cached --name-only` 로 직접 확인 — 이번 스테이징엔 data-platform 파일만 있음). `origin/master` 가 여러 에이전트의 기존 로컬 커밋들보다 한참 뒤처져 있어 이 비교 자체가 지금 시점엔 모두를 걸리게 만드는 것으로 보인다. 이 검사 도구(`tools/`)는 소유 범위 밖이라 고치지 않았다.
  - `--check-manifest` 를 `output/manifest/regions-sido-*.json` 개별 파일에도 돌려보고 싶었으나(픽스처만 검사 대상으로 브리프에 명시돼 있었음), 실행 결과도 함께 남긴다: 두 파일 모두 오류 0건.

---

## 8. DISPATCH 2차 (A-3 재검증 + sigungu·adm_dong 실물) 실행 결과 · 2026-08-16

지시 근거: 총괄자 2차 지시. A-1 게이트 문구("`*.pmtiles` 전체가 비어야 한다")는 D-12와
모순되는 총괄자 표기 오류였고, `output/tiles` 미추적 여부로 정정됨 — 이미 그 조건대로였다
(§7의 `git ls-files` 결과가 `output/tiles/` 아래 실 아티팩트 0건이었음). 별도 조치 불필요.

### 8.1 A-3 재검증 — 두 가지 실패 시나리오 + 대조군

일부러 실패를 유도하는 두 시나리오를 다시 돌렸다(첫 회차의 "속성 제거" 외에
"매니페스트가 광고하는 이름 자체를 존재하지 않는 이름으로 바꾸는" 케이스를 추가):

```
=== 시나리오 1: properties 에서 region_id 를 아예 뺀다 ===
PASS (실패로 막힘): TileJoinKeyVerificationError: feature_id_property='region_id' 가 산출 타일
z0/0/0 의 피처 properties 에 없습니다: ['name', 'level', 'is_synthetic_placeholder']

=== 시나리오 2: FEATURE_ID_PROPERTY 자체를 존재하지 않는 이름으로 바꾼다 ===
PASS (실패로 막힘): TileJoinKeyVerificationError: feature_id_property='region_code_that_does_not_exist'
가 산출 타일 z0/0/0 의 피처 properties 에 없습니다: ['region_id', 'name', 'level', 'is_synthetic_placeholder']

=== 대조군: 정상 properties + 정상 FEATURE_ID_PROPERTY 는 통과해야 한다 ===
PASS (정상 통과): feature_count=5, feature_id_property='region_id'
```

두 실패 시나리오 모두 예외로 막혔고, 정상 케이스는 그대로 통과한다 — 검사가 "항상 실패"나
"항상 통과"가 아니라 실제로 광고값과 산출물을 비교해 판별한다는 뜻이다. 가짜 검사가 아니다.
회귀 테스트(`tests/test_boundary_tiles.py::test_build_fails_when_feature_id_property_missing_from_tile`)로
시나리오 1은 이미 고정돼 있다.

### 8.2 sigungu·adm_dong 실물 레벨 산출 (D-13)

**선행 조치 — 타일러 성능 문제 발견 및 수정**: adm_dong(zoom 5~14, 전국 bbox)을 그대로
빌드해보려 하자 `tiler.py::build_tiles()`가 타일 후보 전부 x 피처 전부에 대해 정확 기하
`.intersection()`을 매번 실행하는 구조라는 게 드러났다. zoom 14 에서 전국 bbox 타일
후보가 약 14만 개이고, 500 피처 기준 최대 7천만 회의 정확 교차 연산이 필요해 견적상
수십 분이 걸린다. 실제로 겹칠 여지가 없는 조합을 O(1) 바운딩박스 비교로 먼저 걸러내는
사전 필터를 추가했다(`tiler.py` `build_tiles`, 결과는 동일하고 속도만 다름 — 회귀 테스트
7개 전부 그대로 통과 확인). 이 수정이 없었다면 이번 사이클 안에 adm_dong 을 낼 수 없었다.

- **sigungu (실물, `boundary_vintage: "2026-01-01"`)**: A-4 픽스처와 같은 250개 합성 소스
  (`tests/fixtures/sigungu_sample_fixture.geojson`)를 `build_vintage()`(fixture 아닌 정식
  경로)로 빌드. `output/manifest/regions-sigungu-2026-01-01.json` 생성,
  `--check-manifest` 오류 0건. 타일 디코드로 250개 피처 전부 `region_id` 속성 확인.
- **adm_dong (실물, `boundary_vintage: "2026-01-01"`)**: 신규 소스
  `tests/fixtures/adm_dong_sample_2026-01-01.geojson` — sigungu 250개 각각의 하위에
  2개씩(잔단 지터 포함, `parent_id` 로 상위 sigungu 코드 참조) 총 500개 합성 생성.
  빌드 소요 **41초**(사전 필터 적용 후). `output/manifest/regions-adm_dong-2026-01-01.json`
  생성, `--check-manifest` 오류 0건. 타일 디코드로 500개 피처 전부 `region_id` 속성 확인.
  minzoom/maxzoom = 5/14 (D-14).

**현재 4개 레벨×빈티지 조합이 `output/manifest/`에 모두 있다**: sido(2026-01-01,
2026-07-01), sigungu(2026-01-01), adm_dong(2026-01-01). `git ls-files data-platform/output/tiles`
는 여전히 비어 있다(pmtiles 실 아티팩트는 계속 미추적).

- **끝낸 항목**: A-3 재검증(2건 실패 시나리오 + 대조군), sigungu 실물, adm_dong 실물
- **통과 확인**: 위 8.1의 3개 스크립트 출력 그대로. `pytest tests -q` → 7 passed(사전 필터
  추가 후 재확인). `validate_contracts.py --check-manifest` sigungu/adm_dong 매니페스트
  각각 오류 0건. 타일 재디코드로 sigungu 250/250, adm_dong 500/500 전부 `region_id` 존재.
- **못 한 것과 이유**: 없음. 다만 sigungu·adm_dong 소스는 실측 SGIS 경계가 아니라 합성
  좌표(모든 A 산출물이 지금 `is_synthetic_placeholder: true`인 것과 동일 전제)다 — 이는
  region 모델 선행 작업(§5-1) 완료 전까지 이 프로젝트 전체의 기존 상태이지, 이번 지시로
  새로 생긴 제약이 아니다.

---

## 9. DISPATCH-2 (A-1 sbiz 매핑 · A-2 suppressed 산출 · A-3 SGIS 착수) 실행 결과 · 2026-08-16

지시 근거: 총괄자 3차 지시(`orchestrator/DISPATCH-2.md` §5), `shared/contracts/ADR-004-taxonomy-mapping.md`,
`DECISIONS.md` D-18/D-19, `shared/contracts/06_governance.md` §2.3.

### 9.1 A-1 — sbiz 1차 택소노미 매핑 파이프라인

신규 모듈 `src/taxonomy_mapping/{sbiz_mapping.py, demand_signal.py, build.py}`.

- `sbiz_mapping.py` 가 `shared/contracts/02_taxonomy.json` 전체 리프 노드(36개)를 순회하며
  자기 노드 → 조상 순으로 `sbiz_codes` 를 상속 해석한다.
- **가장 중요한 실측 결과**: 현재 계약 스냅샷 기준 **36개 리프 노드 중 2개(`TX-FOOD-BEV-COFFEE-RTD`,
  `TX-FNB-CAFE`)만 직접 매핑이 있고, 나머지 34개는 상속으로도 해소되지 않는다** — 상위 L1/L2 노드
  어디에도 `sbiz_codes` 가 없기 때문이다(`output/manifest/taxonomy_sbiz_coverage.json` 에 전체
  목록 커밋). 이건 ADR-004 "A가 할 일 #2"가 요구한 보고이자, jin 이 판단해야 할 사안이다 — 매핑을
  더 채울지, 아니면 v1 스코프를 이 2개 노드로 좁힐지는 A 가 결정할 수 없다. **실제 sbiz 코드값을
  제가 지어내 채우지 않았다.**
- 매핑 없는 34개 노드는 `demand_signal` 행 자체를 만들지 않는다(0으로 채우지 않음) —
  `02_taxonomy.json` 의 `public_data_mapping_note` 문구("상속도 없으면 demand_signal 을
  만들 수 없다")를 그대로 구현. 테스트(`test_unmapped_leaf_never_produces_a_demand_signal_row`)로
  강제: 매핑 없는 노드를 방어적 필터를 우회해 입력에 섞어도 출력에 안 나오는 것까지 확인.
- `spend_krw`/`transaction_count` 는 항상 null(카드 MCC 라이선스 미확보, ADR-004) —
  테스트로 강제(`test_spend_krw_is_always_null_no_card_mcc_license`).
- `data_source` 레지스트리에 `src_sbiz_market` 등록(`output/manifest/data_source-src_sbiz_market.json`),
  `known_limitations` 3개는 ADR-004 "A가 할 일 #3" 문구 그대로. `url` 은 계약(`03_region_features.json`
  `recommended_public_sources`)이 명시한 `https://sg.sbiz.or.kr` 를 그대로 썼다(직접 검증 안 하고
  지어내지 않음).
- **아직 실 sbiz API 연동이 아니다** — 결정론적 합성 점포관측치(`_mock_raw_store_count`)로 구조만
  검증했다. `data_source` 항목에 `is_synthetic_placeholder: true` 를 남겨 숨기지 않는다
  (계약 스키마엔 없는 필드지만, 파이프라인 전체가 이 정직성 원칙을 따르고 있어 통일했다).

### 9.2 A-2 — coverage_flag='suppressed' 셀을 실제로 산출물에 싣기

- `demand_signal.py` 의 합성 관측치 생성기가 셀당 18% 확률로 0~4개(임계 5개 미만, `06_governance.md`
  §2.3) 를 굴리도록 설계 — 억제 대상이 실제로 나오게 하기 위함.
- 억제된 셀은 **원시값을 그 어떤 필드에도 대입하지 않는다.** 대신 같은 sido 안의 억제되지 않은
  시군구 관측치 평균으로 대체(`06` §2.3 "상위 지역 값으로 대체")하고, 대체 불가 시(같은 sido에
  비억제 관측치가 하나도 없는 경우) null.
- 실행 결과(250개 시군구 × 매핑된 2개 노드 = 500행): **actual 402행, suppressed 98행(19.6%)**.
  C 의 VF-010 차단이 실제로 뭔가를 차단해볼 대상이 이제 존재한다.
- 테스트(`test_suppression_threshold_hides_raw_value_and_flags_suppressed`)가 매 행에 대해
  "raw < 5 → 최종 store_count 는 raw 와 다르거나 null" 을 직접 재계산해 검증.

### 9.3 A-3 — SGIS 실데이터 연동 착수 (계획 + 첫 단계, 규모상 여기까지)

`src/boundary_tiles/sgis_source.py` 신설. **실제 HTTP 호출은 아직 하지 않는다** — 이유를 아래에 명시한다.

- **막힌 지점**: SGIS Open API 는 계정 신청·승인이 필요하고(`https://sgis.kostat.go.kr`,
  계약이 명시한 URL), 이건 **사람이 해야 하는 외부 절차**라 에이전트 세션이 대신 할 수 없다.
  정확한 인증 흐름·요청/응답 스키마(좌표계 등)도 이 세션에서 실제 API 문서를 열람해 검증하지
  못했다 — 검증 안 된 가정을 코드로 굳히지 않기 위해 일부러 구현하지 않았다.
- **한 것**: `SgisCredentials.from_env()` 가 `SGIS_CONSUMER_KEY`/`SGIS_CONSUMER_SECRET` 환경변수를
  확인하고, 없으면 `SgisCredentialsMissingError` 로 **명확히 실패**한다(합성 데이터로 조용히
  대체하지 않음, DISPATCH-2 §9 "모르면 503/null/질문이지 추측이 아니다"). `fetch_boundary_geojson()`
  은 자격증명 확인 이후 `NotImplementedError` 로 멈춘다 — 이것도 "조용한 no-op" 이 아니라
  명시적 실패다. 3개 테스트로 이 fail-closed 동작을 고정(`test_sgis_source.py`).
- **계획**(모듈 독스트링에도 기록): ①SGIS 계정 신청/승인(외부, 사람) → ②`consumer_key`/`secret`
  을 환경변수로 주입(하드코딩 금지, `06_governance.md` 비밀 관리 규칙) → ③인증 토큰 발급 →
  경계 API 호출 → 좌표계/응답 형식을 **실제 응답을 보고** GeoJSON(EPSG:4326)으로 변환하는
  계층 구현 → ④기존 `tiler.build_tiles`/`build.build_vintage` 파이프라인에 그대로 투입(타일링·
  조인키·매니페스트 로직은 이미 있어 재사용) → ⑤`data_source` 에 `src_sgis_boundary` 등록,
  해당 빈티지 매니페스트에서 `is_synthetic_placeholder` 문구 제거 → ⑥동일 인증 계층으로
  인구·가구 통계(§5 region_feature 스토어)까지 확장.
- **`is_synthetic_placeholder` 가 붙지 않은 빈티지는 이번 사이클에 만들지 않았다** — 실제로
  SGIS 를 호출하지 않았으므로 만들면 그게 곧 "지어낸 값"이다(DISPATCH-2 §9 가 명시적으로
  경계한 것과 정확히 같은 실수). **다음 필요 행동은 jin/사람이 SGIS Open API 키를 발급받아
  `SGIS_CONSUMER_KEY`/`SGIS_CONSUMER_SECRET` 로 넘겨주는 것**이고, 그 전까지 A 가 이 항목을
  더 진행할 방법이 없다.

### 9.4 종합

- **끝낸 항목**: A-1, A-2, A-3(계획 + 자격증명 게이트 첫 단계)
- **통과 확인**: `pytest tests -q` → **16 passed** (기존 7 + A-1/A-2 전용 6 + A-3 전용 3).
  `python -m src.taxonomy_mapping.build --period 2026-01` 실행 출력:
  `{"leaf_nodes_total": 36, "leaf_nodes_mappable": 2, "leaf_nodes_unmappable": 34, "regions": 250,
  "demand_signal_rows": 500, "rows_actual": 402, "rows_suppressed": 98}`.
- **못 한 것과 이유**: A-3 의 "실제 non-synthetic 빈티지 1개"는 못 만들었다 — SGIS API 자격증명이
  없고, 자격증명 신청은 에이전트가 대신 할 수 없는 외부(사람) 절차이기 때문이다. 대체로 계획과
  자격증명 게이트가 실패로 확인되는 첫 단계를 만들었다(DISPATCH-2 A-3 이 "규모가 크면 계획과
  첫 단계까지만 해도 된다"고 명시적으로 허용).

---

## 10. DISPATCH-4 (SGIS 실물 빈티지 완성 · suppressed 실데이터 경로 확인 · VF-013류 자체 점검) · 2026-08-16

지시 근거: 총괄자 4차 지시. 두 과제 모두 끝냈고, 두 번째 과제에서 **A 잘못이 아닌 실제 막힘**을
하나 찾아 재현했다.

### 10.1 SGIS 실물 빈티지 — 세 레벨(adm_dong·sigungu·sido) 전부 완성. 단, 경로에 대한 정직한 정정이 있다

**SGIS Open API 직접 연동은 여전히 막혀 있다**(자격증명, §9.3 그대로). 대신
`https://github.com/vuski/admdongkor` 를 찾아 썼다 — 원 출처가 통계청 SGIS이고
**CC BY 4.0(공공누리 제1유형 기반, 상업적 이용 포함 자유 이용 허용)** 로 재배포되는
저장소다(`06_governance.md` §3 "commercial_use_allowed=false 소스는 프로덕션 투입
금지"에 저촉되지 않음 — 이건 `true`). 라이선스·최신 커밋(`ver20260701`, 2026-07-01
기준 개편분 반영, 광주·전남 통합 등)을 직접 저장소에서 확인했고 추측하지 않았다.

**정직성 노트 — jin 이 판단해야 할 지점**: 이건 SGIS Open API 를 직접 호출한 게 아니라
**제3자가 SGIS 데이터를 라이선스대로 재배포한 미러**다. `src/boundary_tiles/sgis_source.py`
(직접 연동 스캐폴딩)는 자격증명이 없어 여전히 멈춰 있고 손대지 않았다. 새 모듈
`src/boundary_tiles/admdongkor_source.py` 가 이 미러 경로를 구현한다. 공식 SGIS Open API
경로만 인정한다면 이번 결과는 기각 대상이고, 그러면 자격증명 발급이 여전히 유일한 다음 단계다.
**"SGIS 를 직접 연동했다"고 부풀리지 않았다** — `data_source` 등록에도 "제3자 CC BY 4.0
재배포본"이라고 그대로 적었다(`known_limitations` 1번째 항목).

**실행 결과** (`raw.githubusercontent.com` 에서 34.6MB geojson 다운로드 → 우리 스키마로 변환
→ 기존 `tiler.build_tiles`/`build.build_vintage` 파이프라인에 그대로 투입, 코드 변경 없음):

| 레벨 | region_id 소스 | vintage | feature_count | 빌드 소요 | `--check-manifest` | 타일 디코드 확인 |
|---|---|---|---|---|---|---|
| adm_dong | `adm_cd2`(10자리) | `2026-07-01` | 3,558 | 5분 45초 | 오류 0 | 3558/3558 `region_id` 존재 |
| sigungu | `sgg`(5자리, dissolve) | `2026-07-01` | 256 | <1분 | 오류 0 | 256/256 |
| sido | `sido`(2자리, dissolve) | `2026-08-16`* | 16 | <1분 | 오류 0 | 16/16 |

\* **sido 빈티지 날짜에 대한 정정 필요 사항**: 원본 소스의 실제 기준일은 `2026-07-01`
(다른 두 레벨과 동일)이지만, 그 날짜는 **1차 사이클 때 만든 5피처짜리 합성 sido**가 이미
점유하고 있다(`VintageExistsError` 로 직접 확인 — 재현: `boundary_vintage=2026-07-01`
로 sido 빌드 시도 → 거부). D-11 이 과거 빈티지 덮어쓰기를 금지하므로, sido 만 부득이하게
**인입일(`2026-08-16`)을 vintage 로 기록**했다 — 원본 기준일과 다르다는 사실을
`attribution` 필드에 그대로 남겼다. **더 나은 정리 방법이 있다면(예: 옛 합성 sido 빈티지를
명시적으로 폐기 표시) 그건 jin 의 결정이지 A 가 임의로 지울 사안이 아니다.**

- 세 레벨 모두 `is_synthetic_placeholder: false`, `source_id: "src_admdongkor_sgis"`.
- `data_source` 등록: `output/manifest/data_source-src_admdongkor_sgis.json`
  (`commercial_use_allowed: true`, `license: "CC BY 4.0 (원출처: 통계청 SGIS, 공공누리 제1유형)"`).
- 신규 코드(`admdongkor_source.py`) 테스트 3개 추가(`test_admdongkor_source.py`) —
  변환 정확성, 비합성 플래그, **중복 region_id 는 조용히 버리지 않고 예외**.
- **`output/tiles/regions-adm_dong-2026-07-01.pmtiles` 는 21MB다.** git 에 커밋하지
  않는다(gitignore 그대로 적용됨, `git status` 로 미추적 확인). 원본 다운로드/변환본
  (34.6MB, 31.7MB)도 저장소 밖 스크래치 디렉터리에만 있고 커밋 대상이 아니다 —
  재현이 필요하면 `admdongkor_source.py` 의 `download()`/`convert_to_pipeline_geojson()`
  를 그대로 다시 돌리면 된다(같은 URL, 같은 결과).

### 10.2 coverage_flag='suppressed' 가 실데이터 경로에도 표시되는가 — **아직 아니다. A 의 결함이 아니라 소비 측이 안 뚫려 있다**

재현(읽기 전용, `intelligence/` 수정 없음):

```
store = RegionFeatureFileStore(rows=[])
store.get_demand(['41135'], 'TX-FOOD-BEV-COFFEE-RTD', 'all', '2026-01')
-> NotImplementedError: RegionFeatureFileStore has no demand_signal source -
   data-platform hasn't published one yet. See this class's docstring and intelligence/README.md.
```

`intelligence/scoring/feature_store.py` 의 `RegionFeatureFileStore.get_demand()` 는
**어떤 파일이 있든 없든 무조건 `NotImplementedError` 를 던지도록 하드코딩돼 있다.** 이
코드와 `intelligence/README.md` §2-2 의 주석("A가 region_feature는 물론 demand_signal도
아직 발행하지 않았다")은 **내 §9(DISPATCH-2) 커밋 이전 시점 기준**이라 지금은 낡았다 —
나는 이미 `output/manifest/demand_signal-sigungu-2026-01.json` 을 발행했다(§9.2). 하지만
B 쪽 리더가 그 사실을 모른 채 무조건 예외를 던지므로, **내 산출물이 맞아도 지금 이
경로로는 어디에도 도달하지 못한다.**

추가로: B 가 이미 문서화한 `region_feature` 기대 경로(`intelligence/README.md` 60행)는
`data-platform/output/region_features` 인데, **이건 `demand_signal` 이 아니라 별개
엔티티(`region_feature`)의 경로다.** `demand_signal` 에 대해서는 B 쪽에 기대 경로 자체가
아직 없다 — 내가 고른 `output/manifest/demand_signal-{level}-{period}.json` 이 유일한
후보고, B 가 채택할지는 B/총괄자의 결정이다. 이 자리에서 내가 `intelligence/` 코드를
고치는 건 범위 밖이다(경계 위반).

**결론**: coverage_flag 값 자체(§9.2, §10.3)는 정확하지만, **B↔C 로 가는 실데이터
경로에 아직 demand_signal 소비 코드가 없어 검증 자체가 불가능하다.** 이건 VF-003 과
같은 "이음매가 안 뚫린" 유형이고, C 의 VF-010/VF-013 차단이 이 경로에서 실제로 시험
받으려면 먼저 B(또는 C)가 `output/manifest/demand_signal-*.json` 을 읽는 리더를
만들어야 한다. **jin/총괄자에게 보고 — A 가 더 진행할 수 없는 지점이다.**

### 10.3 VF-013류(값은 막았는데 순서가 원시값을 반영) 자체 점검 — 세 가지 테스트로 확인, 지금 구조에서는 발견되지 않음

`test_taxonomy_mapping.py` 에 3개 테스트 추가:

1. **`test_two_suppressed_cells_in_same_sido_are_indistinguishable_in_output`** — 같은
   sido 안에서 원시값이 서로 다른(0개 대 4개 등) 억제 셀 두 개를 찾아, 출력 `store_count`
   가 **완전히 동일한 값 하나로 수렴**하는지 확인. 통과 — 대체 로직이 sido 평균 하나로만
   귀결되고 개별 원시값은 반영되지 않는다.
2. **`test_national_mean_and_sido_substitute_never_derived_from_suppressed_raw_values`** —
   `actual` 행들의 `spend_index` 를 역산해 파이프라인이 실제로 쓴 `national_mean` 을
   복원하고, "억제 제외 실측치만의 평균"과 독립적으로 재계산해 대조(VF-001 교훈 — 합이
   아니라 외부 증인). 통과(상대오차 0.5% 이내, `spend_index` 소수 1자리 반올림으로 인한
   잡음 감안).
3. **`test_sorting_output_by_store_count_does_not_recover_raw_suppressed_ranking`** —
   억제 셀들을 `store_count` 로 정렬한 결과가, `region_id` 만으로 정렬한(=아무 정보도
   없는) 결과와 **완전히 동일**한지 확인 — `store_count` 자체가 억제 셀 사이의 순서를
   구분할 정보를 전혀 담고 있지 않다는 뜻. 통과.

**결론 — 지금 구조에는 VF-013 류 부채널이 없다.** 이유는 C 의 사고와 달리 애초에
**A 의 산출물에 정렬/순위 단계 자체가 없기 때문이다**(평평한 배열, 입력 지역 순서
그대로). 억제 셀의 `store_count` 는 "같은 sido 의 실측 평균"으로만 정해지므로, 그 지역
자신의 원시값이 얼마였든 결과에 반영되지 않는다.

**단, 발견한 별개의 주의사항 하나(누수는 아니지만 투명하게 남긴다)**: 지금 `store_count`
는 `_mock_raw_store_count(region_id, node_id)` 라는 **공개된 결정론적 함수**의 산출물이다.
따라서 이 저장소 코드에 접근할 수 있는 누구든 억제된 "원시값"을 스스로 재계산할 수 있다 —
이건 산출물 스키마의 결함이 아니라 **모의(mock) 데이터를 쓰는 것 자체의 성질**이다. 실
sbiz API 데이터로 바뀌면(A-1/A-3 다음 단계) 원시값이 외부 시스템에만 있게 되어 이 문제는
자연히 사라진다. 지금 단계에서 조치는 필요 없다고 판단했다 — 픽스처/합성 데이터라는 표시
(`is_synthetic_placeholder`)가 이미 있고, 실 데이터 전환이 근본 해법이지 이 모의 생성기를
난독화하는 건 헛수고다.

### 10.4 종합

- **끝낸 항목**: SGIS 실물 빈티지 3개 레벨(adm_dong/sigungu/sido) 완성, coverage_flag
  실데이터 경로 확인(결과: 아직 도달 못 함, 원인 특정), VF-013류 자체 점검(3개 테스트,
  누수 없음 확인 + 모의생성기 재계산가능성 caveat 기록)
- **통과 확인**: `pytest tests -q` → **22 passed**(기존 16 + admdongkor_source 3 +
  leak-audit 3). 세 매니페스트 전부 `--check-manifest` 오류 0. 세 pmtiles 전부 타일
  디코드로 region_id 100% 확인(3558/256/16). `RegionFeatureFileStore.get_demand()` 가
  발행 여부와 무관하게 무조건 `NotImplementedError` 를 던짐을 직접 재현.
- **못 한 것과 이유**: ① SGIS Open API **직접** 연동은 여전히 안 됨 — 자격증명 필요,
  사람이 해야 하는 외부 절차(§9.3과 동일). ② coverage_flag 가 실제로 예측 결과에
  반영되는 것까지는 확인 못 함 — B 의 `get_demand()` 가 무조건 실패하는 스텁이라
  A 의 산출물 유무와 무관하게 막혀 있고, 이건 `intelligence/` 범위라 A 가 고칠 수
  없다. **다음 필요 행동은 B(또는 총괄자 조정)가 `output/manifest/demand_signal-{level}-
  {period}.json` 을 읽는 리더를 만드는 것.**
