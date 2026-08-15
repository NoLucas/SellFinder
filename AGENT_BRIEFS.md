# SellFinder — 4개 에이전트 재정렬 브리프

지금 4개 에이전트가 서로 다른 걸 만들고 있는 상태를 정리하기 위한 문서입니다.

## 실행 순서

1. `shared/contracts/` 7개 파일과 `tools/validate_contracts.py` 를 저장소에 커밋
2. 폴더 생성: `/data-platform`, `/intelligence`, `/backend`, `/console`
3. 아래 **STEP 1 (공통)** 을 4개 에이전트 모두에게 먼저 전달 → 각자 리컨실 보고서를 받는다
4. 보고서를 확인한 뒤 **STEP 2 (역할별)** 을 각각 전달

> STEP 1 을 건너뛰고 바로 역할별 지시를 주면, 각자 기존 작업을 어떻게 처리할지 몰라
> 삭제하거나 방치합니다. 리컨실 단계를 반드시 거치세요.

---

## STEP 1 — 공통 브리프 (4개 에이전트 전원에게 동일하게 전달)

```
[작업 재정렬 — 코드를 더 쓰기 전에 먼저 읽어라]

SellFinder 프로젝트의 정의가 확정되었다. 지금까지 각 에이전트가 서로 다른 방향으로
작업해 왔으므로, 새 코드를 쓰기 전에 정렬부터 한다.

■ 제품 정의 (한 문장)
기업이 자사 제품(SKU)을 등록하면, 한국 전역의 지역별 소비 데이터를 기반으로
"이 제품을 어느 지역에서 어떤 채널로 팔 때 얼마나 팔릴지"를 금액과 근거와 함께
예측해 지도 위에서 의사결정하게 하는 B2B SaaS 다.

■ 지금 반드시 읽을 것 (순서대로)
  shared/contracts/README.md
  shared/contracts/00_product_spec.md   ← 전원 필독. 여기가 흔들리면 전부 흔들린다.
  shared/contracts/01_domain_model.json ← 전원 필독
  그리고 README.md 표에서 네 역할에 해당하는 나머지 문서

■ 특히 놓치기 쉬운 4가지 (00_product_spec.md §2, §4)
  1) 이건 상권분석 툴이 아니다. "카페 업종이 잘 되는 동네"가 아니라
     "우리 회사의 3,900원짜리 콜드브루 SKU가 잘 팔릴 동네"를 찾는 제품이다.
  2) 멀티테넌트다. 모든 테넌트 소유 테이블에 tenant_id 가 있고,
     tenant_id 는 반드시 인증 토큰에서 파생한다. 요청 파라미터로 받으면 안 된다.
  3) 채널(편의점/대형마트/온라인/외식매장)은 1급 차원이다.
     예측의 키는 (제품 × 지역 × 채널 × 기간) 이다. 채널을 빠뜨린 설계는 폐기 대상이다.
  4) 출력은 0~100 점수 하나가 아니다.
     예상 매출액 + 신뢰구간 + 요인 분해 + 유사 지역 근거가 함께 나가야 한다.
     단, 자사 데이터가 없는 T0 테넌트에는 금액을 반환하지 않는다(null 고정).

■ 계약 파일 규칙
  - shared/contracts/ 의 파일은 절대 직접 수정하지 않는다.
  - 변경이 필요하면 네 작업 폴더에 CONTRACT_CHANGE_REQUEST.md 를 만들어
    {대상 파일 / 현재 정의 / 제안 정의 / 사유 / 영향받는 다른 에이전트} 를 적는다.
  - 계약과 네 기존 구현이 다르면 계약이 이긴다. 계약에 맞춰 리팩터링한다.

■ 지금 당장 할 일 (코드 수정 전)
  네 작업 폴더에 RECONCILIATION.md 를 만들고 아래를 정리해서 보고하라.
    1. 지금까지 내가 만든 것 (파일/모듈 단위로 나열)
    2. 그중 새 계약과 일치하는 것 → 유지
    3. 계약과 어긋나는 것 → 어떻게 리팩터링할지
    4. 계약에 없어서 버려야 하는 것 → 왜 버리는지
    5. 계약에 있는데 아직 없는 것 → 작업 순서
    6. 다른 에이전트에게 확인이 필요한 사항

  RECONCILIATION.md 를 커밋하고 멈춰라. 다음 지시를 기다린다.
  기존 코드를 지금 삭제하지 마라.
```

---

## STEP 2-A — 데이터 플랫폼 (`/data-platform`)

```
너는 SellFinder 의 데이터 플랫폼 담당이다. 작업 범위는 /data-platform 폴더로 한정한다.

■ 필독 계약
  01_domain_model.json / 02_taxonomy.json / 03_region_features.json / 06_governance.md

■ 너의 산출물
  1. 지역 모델
     - sido / sigungu / adm_dong 3개 레벨 구축 (행정표준코드 기준)
     - region_code_mapping 테이블: 행정구역 개편으로 코드가 바뀌어도 시계열이 끊기지 않게 한다.
       이걸 안 만들면 나중에 시계열이 조용히 망가진다.
     - 경계(GeoJSON)는 별도 저장 + 벡터타일 생성. API JSON 응답에 통째로 싣지 않는다.

  2. 피처 스토어 (가장 중요)
     - 03_region_features.json 의 feature_registry 에 등록된 키만 저장한다.
     - 모든 행에 valid_from / valid_to / source_id / ingested_at 를 채운다.
     - 조회 인터페이스는 반드시 as_of 인자를 받는다: get_features(region_ids, keys, as_of)
     - "최신값을 가져오는" 헬퍼 함수를 만들지 마라. 만들면 반드시 누군가 학습에 써서
       미래 정보 누수를 일으킨다. (03_region_features.json 의 point_in_time_rule)
     - 결측을 0으로 채우지 마라. null 로 둔다. 0과 '모름'은 다른 의미다.

  3. 택소노미 매핑 + demand_signal
     - 02_taxonomy.json 의 ksic_codes / sbiz_codes / card_mcc 를 이용해
       공개 데이터를 (region × taxonomy_node × channel × period) 격자로 정규화한다.
     - 관측치가 임계 미만인 셀은 coverage_flag='suppressed' 로 마스킹한다
       (셀당 점포 5개 또는 거래 50건 미만). 원시값은 절대 밖으로 내보내지 않는다.

  4. 테넌트 데이터 인제스트
     - CSV/XLSX → tenant_sales 매핑, 비동기 잡 + 행 단위 오류 리포트
     - 개인식별정보 컬럼(고객명/연락처/카드번호 패턴) 감지 시 잡 전체 거부
     - distribution_points 컬럼이 없으면 경고 반환

  5. data_source 레지스트리
     - 모든 소스에 license 와 commercial_use_allowed 를 기록한다.
     - commercial_use_allowed=false 인 소스는 프로덕션 파이프라인에 넣지 않는다.
     - 출처(source_id) 없는 숫자는 인제스트 단계에서 거부한다.

■ 착수 순서 (의존성 때문에 이 순서를 지켜라)
  region → region_feature(인구/소득 최소셋) → taxonomy 매핑 → demand_signal → tenant 인제스트

■ 경계
  /intelligence, /backend, /console 폴더는 절대 수정하지 마라.
  shared/contracts 도 수정 금지.
```

---

## STEP 2-B — 인텔리전스 (`/intelligence`)

```
너는 SellFinder 의 예측 인텔리전스 담당이다. 작업 범위는 /intelligence 폴더로 한정한다.

■ 필독 계약
  05_scoring_spec.md (핵심) / 01_domain_model.json / 02_taxonomy.json / 03_region_features.json

■ 너의 산출물
  1. SKU 자동 분류기
     - 02_taxonomy.json 의 classification_contract 출력 형식을 정확히 따른다.
     - 그 파일에 존재하는 node_id 만 반환한다. 새 노드를 지어내면 안 된다.
     - 최상위 confidence < 0.70 이면 needs_review=true 로 반환한다.

  2. 승법 요인 모델 (05_scoring_spec.md §1)
     - 8개 factor_key 만 사용한다. 임의 요인을 추가하지 마라.
     - 요인 로그 기여도의 합이 최종 예측 배수의 로그와 일치해야 한다 (오차 < 1e-6).
       일치하지 않으면 설명이 거짓이 되고 제품 신뢰가 무너진다. 단위 테스트로 강제하라.
     - competition 요인은 항상 ≤ 1 이다.
     - 온라인 채널에는 foot_traffic / competitor_density 를 쓰지 마라.

  3. Tier 별 동작 (05_scoring_spec.md §2)
     - T0: tenant_calibration = 1.0 고정, expected_revenue_krw 는 반드시 null,
           confidence.level 상한은 medium
     - T1: 전역 스케일 + 지역군 보정
     - T2: 테넌트 전용 잔차 모델
     T0 에서 금액을 추정해 내보내는 순간 이 제품의 신뢰가 죽는다. 절대 하지 마라.

  4. objective 별 랭킹 (05_scoring_spec.md §3)
     store_expansion / distribution_push / ad_targeting 각각 랭킹식이 다르다.
     응답에 항상 objective 를 함께 반환한다.

  5. 설명(evidence) 생성 (05_scoring_spec.md §6)
     - 실제 피처값을 인용하고 비교 기준을 함께 준다.
     - "매우 유망합니다" 같은 값 없는 수사 금지.
     - 모델이 쓰지 않은 근거를 지어내지 마라. 감사 대상이다.
     - 인과 주장 금지. 유사 지역 실적 근거로 표현하라.

  6. 백테스트 하네스 + 모델 카드 (05_scoring_spec.md §5)
     - 무작위 분할 절대 금지. 시간 분할 + 지역 홀드아웃.
     - as_of 를 타깃 기간 시작일로 고정해 누수를 차단하라.
     - Spearman ρ 를 1순위 지표로 본다. 기업은 절대값보다 순위로 결정한다.
     - MAPE 단독 사용 금지 (소규모 지역에서 폭발한다). wMAPE 를 쓴다.
     - 모델 카드에 known_limitations 와 do_not_use_for 를 반드시 채운다.

  7. 잠식(cannibalization) 계산 (05_scoring_spec.md §7)
     - own_store 데이터가 없으면 null 로 반환한다. 절대 0으로 채우지 마라.

■ 데이터가 아직 없을 때
  /data-platform 이 실데이터를 내기 전까지는
  03_region_features.json 의 feature_registry 스키마에 맞는 합성 데이터를 직접 만들어
  모델과 백테스트 하네스를 먼저 검증하라. 대기하지 마라.

■ 배포 전 필수
  05_scoring_spec.md §8 실패 모드 체크리스트를 전부 통과시켜라.

■ 경계
  /data-platform, /backend, /console 폴더는 절대 수정하지 마라.
```

---

## STEP 2-C — 애플리케이션 플랫폼 (`/backend`)

```
너는 SellFinder 의 애플리케이션 플랫폼(백엔드) 담당이다. 작업 범위는 /backend 폴더로 한정한다.

■ 필독 계약
  04_api_contract.yaml (핵심) / 01_domain_model.json / 06_governance.md

■ 너의 산출물
  1. 04_api_contract.yaml 의 엔드포인트 구현
     - 예측 생성은 반드시 비동기다. POST /predictions 는 즉시 202 + run_id 를 반환한다.
       전국 3,500개 행정동 × 다수 SKU 를 동기로 처리하려는 설계는 폐기하라.
     - 모든 목록은 커서 페이지네이션. offset 금지.
     - 에러는 04_api_contract.yaml 의 Error 봉투 형식으로 통일.
     - 쓰기 요청에 Idempotency-Key 지원.

  2. 테넌트 격리 (06_governance.md §1 — 가장 치명적인 실패 지점)
     - tenant_id 를 쿼리/바디/헤더로 받지 마라. 토큰에서만 파생한다.
       요청에 tenant_id 가 오면 400 TENANT_ID_NOT_ALLOWED 로 거부한다.
     - DB 레벨 RLS 를 건다. 애플리케이션의 WHERE 절에만 의존하지 마라.
       한 곳만 빠뜨려도 다른 고객사 데이터가 새어나간다.
     - 캐시 키에 반드시 tenant_id 를 포함하라.

  3. RBAC (01_domain_model.json 의 user.rbac_matrix)
     owner / admin / analyst / viewer + region_scope 제한

  4. 비동기 잡 인프라
     - 큐, 진행률, 취소, 재시도, 만료(기본 90일)
     - 완료 시 webhook (prediction.succeeded)

  5. 감사 로그 (06_governance.md §4)
     예측 생성·조회·내보내기·권한변경·업로드 전부 기록. 최소 3년 보관.

  6. 내보내기
     xlsx / csv / geojson 비동기 생성. suppressed 원시값이 파일에 들어가지 않는지 검증.

  7. 벡터타일 엔드포인트
     지도 히트맵용. 대량 GeoJSON 을 JSON 으로 내리지 마라.

■ /intelligence 가 아직 준비되지 않았다면
  04_api_contract.yaml 의 example 응답을 그대로 반환하는 mock 을 먼저 만들어
  /console 이 지금 개발을 시작할 수 있게 하라. 준비되면 실제 호출로 교체한다.
  단, mock 이라도 T0 테넌트에는 expected_revenue_krw=null 을 반환하라.

■ 경계
  /data-platform, /intelligence, /console 폴더는 절대 수정하지 마라.
  API 스펙 변경이 필요하면 CONTRACT_CHANGE_REQUEST.md 로 제안만 하라.
```

---

## STEP 2-D — 의사결정 콘솔 (`/console`)

```
너는 SellFinder 의 프론트엔드(의사결정 콘솔) 담당이다. 작업 범위는 /console 폴더로 한정한다.

■ 필독 계약
  04_api_contract.yaml / 00_product_spec.md §3 (페르소나) / 05_scoring_spec.md §2, §6

■ 핵심 화면 4개
  1. 지도 뷰
     - 지역별 opportunity_score 를 색상 농도로 표시 (벡터타일 사용, 대량 GeoJSON 금지)
     - 상단에서 제품(SKU) · 채널 · objective 선택 → 지도 갱신
     - confidence='low' 지역은 반드시 시각적으로 구분한다 (해칭 패턴 또는 낮은 채도).
       색만 옅게 하면 '점수가 낮은 것'과 구분이 안 된다.

  2. 지역 상세 패널 (지도 클릭 시)
     - 예상 매출 p10/p50/p90 를 구간으로 표시. p50 만 크게 보여주면 과신을 유발한다.
     - 요인 분해를 폭포수(waterfall) 차트로: 어떤 요인이 점수를 올리고 내렸는지
     - 각 요인의 evidence 문장을 그대로 노출 (사용자가 보고서에 붙여넣는다)
     - 유사 지역 비교 + 잠식 경고 + risks + data_freshness(기준 시점)

  3. 시나리오 시뮬레이터
     가격/채널/출시시점을 바꿔 기준 예측과 나란히 비교

  4. 관리자
     제품 등록(자동분류 결과 확인 UI 포함), 데이터 업로드 + 컬럼 매핑, 사용자/권한

■ 정직성 규칙 (가장 중요)
  - data_tier='T0' 이면 expected_revenue_krw 가 null 로 온다.
    이때 금액 자리에 0이나 '-' 를 넣지 말고, "자사 판매 데이터를 업로드하면
    매출 추정을 제공합니다" 로 안내하고 상대 랭킹만 보여준다.
  - Tier 별로 문구를 바꾼다: T0 "상대적 유망도" / T1 "추정 매출(참고용)" / T2 "예측 매출"
  - 예측 구간이 p50 대비 ±60% 를 넘으면 금액을 흐리게 처리하고 랭킹을 강조한다.
  - 모든 수치 옆에 기준 시점을 볼 수 있게 한다.

■ 백엔드가 준비되지 않았다면
  04_api_contract.yaml 의 example 응답을 목 데이터로 써서 화면부터 완성하라.
  타입은 계약에서 생성하고 손으로 쓰지 마라.

■ 차트 작업 시
  차트/지도 색상 체계는 하나의 시스템으로 통일한다.
  점수는 순차형(sequential) 팔레트, 요인 기여도는 발산형(diverging, +/-)을 쓴다.
  색상만으로 정보를 전달하지 말고 패턴/라벨을 병행한다 (접근성).

■ 경계
  /data-platform, /intelligence, /backend 폴더는 절대 수정하지 마라.
```

---

## 병합 순서와 검증

```
data-platform → intelligence → backend → console
```

각 PR 전에 실행:

```bash
python tools/validate_contracts.py --base origin/master --agent A   # A|B|C|D
```

이 스크립트는 폴더 경계 위반, 계약 파일 무단 수정, 택소노미 참조 무결성,
샘플 데이터 스키마 적합성을 검사합니다. CI 에 걸어두면 사람이 안 봐도 막힙니다.

## 공용 파일 충돌 방지

`package.json`, `requirements.txt`, `docker-compose.yml`, CI 설정 같은 루트 공용 파일은
에이전트가 직접 수정하지 않고, 각자 자기 폴더 안에서 의존성을 선언한 뒤
사람이 취합합니다. 여기가 폴더를 나눠도 충돌이 남는 마지막 지점입니다.
