# RECONCILIATION — 에이전트 C (Application Platform / `/backend`)

작성일: 2026-08-15
읽은 계약: `shared/contracts/README.md`, `00_product_spec.md`, `01_domain_model.json`,
`04_api_contract.yaml`(핵심), `06_governance.md`

---

## 1. 지금까지 만든 것

`/backend`에는 구 제품 정의(중고거래 매물 단위 판매확률/가격 예측 — `prediction_api.json`,
매물 단위) 시절 코드가 이미 동작 상태로 있다.

- `app/main.py` — FastAPI 앱, 공통 예외 핸들러(HTTPException/RequestValidationError → `{"error": {...}}` 봉투)
- `app/routers/health.py` — `GET /api/v1/health`
- `app/routers/predictions.py` — `POST /api/v1/predictions` (동기, 배치 최대 100건)
- `app/schemas.py` — `PredictionItem`/`ItemPrediction`/`PredictionRequest`/`PredictionResponse` (매물 단위: item_id/category/price/condition/days_listed)
- `app/services/model_client.py` — `ModelClient` 추상 클래스 + `MockModelClient`(휴리스틱) / `LiveModelClient`(`/model`을 in-process import) + `get_model_client()` 팩토리
- `app/config.py` — `pydantic_settings` 기반 환경변수 (`SELLFINDER_USE_LIVE_MODEL` 등)
- `tests/test_predictions.py`, `requirements.txt`, `requirements-live.txt`, `README.md`

## 2. 새 계약과 일치하는 것 → 유지

- **레이어 분리 구조**(`routers/` = HTTP, `services/` = 외부 연동, `schemas.py` = 계약 타입)는 그대로 재사용 가능.
- **Mock/Live 이원화 + 팩토리 패턴**(`ModelClient` ABC, `get_model_client()`)은 구조적으로 정확히 STEP 2-C가 요구하는 것과 같다:
  "`/intelligence`가 아직 준비 안 됐으면 `04_api_contract.yaml`의 example을 반환하는 mock을 먼저 만들어라." →
  `MockIntelligenceClient` / `LiveIntelligenceClient`로 이름만 바꿔 같은 패턴을 재사용한다.
- **에러 봉투 공통 처리**(`main.py`의 예외 핸들러가 모든 에러를 `{"error": {...}}`로 통일)는 방향 자체는 맞다. 다만 필드가
  계약과 다름 → §3에서 리팩터링.
- **`pydantic_settings` 기반 설정 패턴**은 재사용 가능 (live 전환 플래그, DB/큐 접속정보 등을 여기로 확장).

## 3. 계약과 어긋나는 것 → 리팩터링 방향

1. **동기 API 자체가 폐기 대상**: `00_product_spec.md` Anti-goals가 명시적으로 금지하는
   "예측 API를 동기 호출로 설계"를 그대로 하고 있다(`POST /api/v1/predictions`가 즉시 결과 반환).
   → `POST /predictions`는 즉시 `202 {run_id, status:"queued", estimated_seconds, model_version, feature_as_of, data_tier}`만
   반환하고, 실제 계산은 잡 워커로 분리해야 한다.
2. **테넌트 개념 전무**: 현재 코드 어디에도 인증/토큰/`tenant_id`가 없다. `06_governance.md` §1이 가장 치명적인
   실패 지점으로 지목한 부분이 아예 시작이 안 된 상태다. → 인증 미들웨어에서 토큰을 파싱해 `tenant_id`를 파생하고,
   요청 파라미터로 `tenant_id`가 오면 `400 TENANT_ID_NOT_ALLOWED`로 거부하는 검증을 모든 엔드포인트 공통으로 넣어야 한다.
3. **에러 봉투 필드 불일치**: 현재 `{"error": {"code": "http_error", "message": ...}}`. 계약은
   `{"error": {"code", "message", "details"?, "request_id"}}`이고 `request_id` 필수. `code`도
   `TENANT_ID_NOT_ALLOWED` 같은 계약상 의미 있는 값이어야지 `"http_error"` 같은 범용 값이면 안 된다.
4. **라우트 프리픽스**: 현재 `/api/v1/...`. 계약의 `servers.url`이 이미 `/v1`을 포함하고 각 path는
   `/predictions`, `/products` 등이므로 실제로는 `/v1/predictions` 형태가 되어야 한다. `/api` 세그먼트는 계약에 없다.
5. **페이지네이션/Idempotency-Key 미구현**: 목록형 엔드포인트(`/products`, `/predictions/{run_id}/regions`)는
   커서 방식(`cursor`/`next_cursor`)이어야 하고 `offset`은 금지. 쓰기 엔드포인트는 `Idempotency-Key` 헤더를
   지원해야 한다 — 지금은 둘 다 없음.
6. **`LiveModelClient`의 in-process import 패턴**: `/model`(구 폴더, 소유권表 밖)을 `sys.path` 조작으로 직접
   import하는 지금 방식은, 새 구조에서 `/backend` ↔ `/intelligence` 경계에도 똑같이 적용할 수 있는 패턴이긴 하다.
   다만 이게 맞는 방식인지(동기 함수 호출 vs 내부 API/RPC)는 계약에 명시가 없다 → §6에서 확인 필요 사항으로 남김.

## 4. 계약에 없어서 버려야 하는 것

- **`PredictionItem`/`ItemPrediction`/`PredictionRequest`/`PredictionResponse` 스키마 전체**
  (`item_id`, `category`, `condition`, `days_listed`, `sell_probability`, `estimated_days_to_sell`,
  `recommended_price`) — 매물 단위 중고거래 예측 개념이며, 신계약의 `product`/`prediction_run`/`prediction`
  (SKU × 지역 × 채널 × 기간, `opportunity_score`, `expected_revenue_krw`, `factors`, `confidence`)와
  근본적으로 다른 도메인. 재사용 불가, 새로 작성.
- **`POST /api/v1/predictions`의 동기 배치 처리 로직**: §3-1과 동일한 이유로 폐기. 비동기 잡 발행/폴링 구조로 대체.
- **`MockModelClient`의 컨디션 기반 휴리스틱**(`_CONDITION_SCORE`, staleness penalty 등): 새 계약의 8-factor
  승법 요인 모델과 무관한 로직. 폐기하되, "결정론적 mock으로 프론트를 먼저 움직이게 한다"는 목적 자체는
  `04_api_contract.yaml`의 example 응답을 그대로 반환하는 형태로 다시 만든다.
- **`README.md`의 "Implements /shared/contracts/prediction_api.json" 기술**: 구 계약 참조. 신계약
  (`04_api_contract.yaml`) 기준으로 재작성 필요.

기존 코드는 아직 삭제하지 않았다.

## 5. 계약에 있는데 아직 없는 것 → 작업 순서

`06_governance.md` §1이 "가장 치명적인 실패 지점"으로 지목한 테넌트 격리를 최우선으로 두고,
그 다음은 다른 에이전트(A/B) 없이도 mock으로 진행 가능한 것부터 순서를 잡는다.

1. **인증 · 테넌트 파생 미들웨어**: 토큰 파싱 → `tenant_id` 컨텍스트 주입, 요청 파라미터에 `tenant_id`가
   있으면 무조건 `400 TENANT_ID_NOT_ALLOWED`. 이후 모든 엔드포인트가 이 컨텍스트에 의존하므로 최우선.
2. **공통 인프라**: 계약 형식의 Error 봉투(`request_id` 포함), 커서 페이지네이션 헬퍼, `Idempotency-Key`
   처리(24시간 캐시), RBAC 데코레이터(`01_domain_model.json`의 `rbac_matrix`).
3. **`/products`, `POST /products:classify`**: SKU 등록. `classify`는 `/intelligence`가 아직 없으므로
   `02_taxonomy.json`의 `classification_contract` 예시 형태를 반환하는 mock으로 우선 구현.
4. **`/predictions` 비동기 골격**: `POST /predictions` → `202 + run_id`, `GET /predictions/{run_id}` 상태
   조회. 잡 큐는 초기엔 인메모리/단순 워커로 시작하고, 실제 계산은 `/intelligence` mock 클라이언트
   (`04_api_contract.yaml`의 `PredictionDetail` example을 그대로 반환)로 채운다.
5. **`/predictions/{run_id}/regions`, `/regions/{region_id}`**: mock 데이터 기반으로 우선 구현, 커서
   페이지네이션·`min_confidence` 필터 포함.
6. **`/predictions/{run_id}/tiles/{z}/{x}/{y}.mvt`**: 벡터타일 서빙. 생성 주체가 A인지 C인지 불명확
   (§6 참조) — 확인 전까지는 엔드포인트 스텁(501 또는 빈 타일)만 두고 보류.
7. **`/datasets/sales:import`, `/datasets/jobs/{job_id}`**: 비동기 업로드 잡. PII 컬럼 감지/파싱을
   누가 담당하는지 A의 리컨실 보고서(§6-3)에서도 이미 같은 질문이 나옴 — 확인 후 착수.
8. **`/scenarios`, `/scenarios/{scenario_id}:compare`**
9. **`/exports`**: xlsx/csv/geojson 비동기 생성. `suppressed` 원시값이 파일에 안 들어가는지 검증 로직 포함.
10. **`/taxonomy`, `/regions/{region_id}/profile`, `/models/{model_version}/card`**: 참조 데이터,
    A/B 실데이터 준비 전까지는 mock.
11. **감사 로그(`audit_log`) 공통 미들웨어**: 예측 생성·조회·내보내기·권한변경·업로드 전체에 공통 적용.
    엔드포인트를 하나씩 추가할 때마다 빠뜨리기 쉬우므로 데코레이터/미들웨어로 강제.
12. **webhook(`prediction.succeeded`)**: 잡 완료 시 발송.

## 6. 다른 에이전트/사람(jin)에게 확인이 필요한 사항

- **(B: intelligence) `/backend` ↔ `/intelligence` 내부 호출 계약** — intelligence의 리컨실 보고서
  §6-3에서도 동일하게 지적된 빈틈이다: 동기 함수 호출인지, 내부 큐/RPC인지, `prediction_run.params`
  스냅샷을 어떤 형태로 B에 전달하는지 어느 계약 파일에도 없다. 지금 `/backend`가 비동기 잡 인프라를
  소유하는 쪽이므로, 제안: 잡 워커가 B의 예측 함수를 (초기엔 in-process, 이후 필요시 내부 API로) 호출하는
  방식으로 진행하되, B가 실제 구현을 시작하는 시점에 맞춰 인터페이스를 확정하고 싶다.
- **(A: data-platform) tenant_sales 업로드 경계** — A의 리컨실 보고서 §6-3에서 동일 질문: 파일 파싱/PII
  감지/컬럼 매핑을 A가 담당하고 C는 `import_job` 큐잉·webhook만 갖는 구조로 이해하고 진행할 예정이다.
  이견 있으면 알려달라.
- **(A: data-platform) 벡터타일 생성 주체** — `03_region_features.json`에는 A가 "벡터타일 생성"이라
  되어 있는데, `04_api_contract.yaml`의 타일 엔드포인트(`/predictions/{run_id}/tiles/...`)는 C 소유다.
  region 경계 타일과 예측 결과(opportunity_score) 타일은 다른 것일 수 있어 보인다 — C가 A의 경계 타일 위에
  예측 속성만 얹어 서빙하는 구조인지, C가 GeoJSON→MVT 변환까지 직접 하는지 확인 필요.
- **jin — 인증 방식**: `06_governance.md` §6에 "OAuth2 client credentials(서버간) + SSO/SAML(콘솔)"로
  방향만 있고 실제 IdP(자체 구현 vs Auth0/Cognito 등)는 미정. 초기 구현은 자체 JWT 발급으로 시작해도
  될지, 아니면 특정 IdP를 전제로 설계해야 할지 결정이 필요하다. (console의 리컨실 보고서 §6에서도
  같은 지점을 C에게 확인해 달라고 요청했다.)
- **jin — 구 `/backend` 코드 처분**: 위 §4에서 폐기 대상으로 판단한 매물 단위 스키마/엔드포인트는
  삭제하지 않고 남겨뒀다. 구 `/model`, `/data-pipeline`, `/frontend`와 같은 층위의 "포트 vs 폐기" 결정
  대상으로 보이며, 최종 삭제 여부는 사람 확인 후 진행하고 싶다.

---

**RECONCILIATION.md 작성 완료. 다음 지시를 기다린다. 기존 코드는 삭제하지 않았고, 계약이 요구하는 새 엔드포인트/미들웨어 코드도 아직 작성하지 않았다.**

---

## 2026-08-16 — DISPATCH C-1~C-6 실행 보고

- 끝낸 항목: C-1, C-2, C-3, C-4, C-5, C-6
- 통과 확인:

  ```
  $ PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe verification/fixtures/vf_t0_api.py
  ...
  --- 05_scoring_spec 2: T0 confidence.level ceiling is 'medium' ---
    /regions (T0) confidence levels : ['medium', 'medium', 'medium', 'medium', 'low']
    above ceiling (=='high')        : 0   (contract: must be 0)
    /scores  (T0) confidence levels : ['medium', 'medium', 'medium', 'medium', 'low']
    above ceiling (=='high')        : 0   (contract: must be 0)
  ```

  ```
  $ PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe verification/fixtures/vf_52_tenant.py
  --- 06_governance 1.1: tenant_id via QUERY (expect 400 TENANT_ID_NOT_ALLOWED) ---
  A + ?tenant_id=tnt_other         /regions -> 400  TENANT_ID_NOT_ALLOWED
  A + ?tenant_id=tnt_demo          /regions -> 400  TENANT_ID_NOT_ALLOWED
  B + ?tenant_id=tnt_demo          /regions -> 400  TENANT_ID_NOT_ALLOWED
  A + ?tenant_id=tnt_other         /scores  -> 400  TENANT_ID_NOT_ALLOWED
  A + ?tenantId=tnt_other          /scores  -> 400  TENANT_ID_NOT_ALLOWED

  --- tenant_id via HEADER (expect 400) ---
  A + X-Tenant-Id: tnt_other       /regions -> 400  TENANT_ID_NOT_ALLOWED
  A + Tenant-Id: tnt_other         /scores  -> 400  TENANT_ID_NOT_ALLOWED
  ```

  (7개 주입 경로 전부 400 — 지시된 "6경로"를 포함한다. `/basemap` 케이스는 픽스처 자체가
  `/v1/basemap/manifest`라는 존재하지 않는 경로를 치고 있어 404가 나온다 — 실제 경로는
  `/v1/basemap/regions/manifest`다. 픽스처 오탈자이며 backend 밖이라 여기서 고치지 않았다.)

  ```
  $ PYTHONIOENCODING=utf-8 python tools/validate_contracts.py --check-scores backend/samples/scores.json
    점수 응답 검증: 5행, level=sigungu
  통과: 경고 0건
  ```

  ```
  $ cd backend && .venv/Scripts/python.exe -m pytest tests -q
  26 passed in 0.55s
  ```

- 구현 요약:
  - C-1/C-2: `app/routers/predictions.py`에 `_confidence_for_tier()` 추가 — T0 run은
    `/regions`·`/scores` 양쪽에서 `confidence.level`을 `medium` 상한으로 클램프. 회귀를 잡을
    `tests/test_predictions_t0.py` 신설(T0 run을 직접 생성해 금액 null + 신뢰도 상한 + T1은
    영향 없음을 검증).
  - C-3: `backend/samples/scores.json` → `region_level: "sigungu"`, `boundary_vintage: "fixture"`
    (D-15). region_id 5자리는 원래도 sigungu 자릿수와 맞아 변경 없음.
  - C-4: `app/security.py`에 `_reject_tenant_id_injection()` 추가 — 쿼리(`tenant_id`,
    `tenantId`) · 헤더(`X-Tenant-Id`, `Tenant-Id`)로 들어오면 `get_tenant_id` 진입 즉시
    400 `TENANT_ID_NOT_ALLOWED`. `/regions`·`/scores`·`/basemap` 전부 이 의존성을 쓰므로
    자동으로 세 라우터 모두 적용됨.
  - C-5: `app/routers/basemap.py` — 서명 URL(`sig=` 포함, 지금은 `adm_dong`)인 응답만
    `Cache-Control: private, max-age=3600`으로 바꿈. 서명이 필요 없는 레벨(`sido`/`sigungu`)은
    기존대로 `public`. `tests/test_basemap.py`의 관련 단언 갱신.
  - C-6: `app/security.py`에 `TokenClaims`/`verify_token(raw) -> TokenClaims`/`issue_dev_token()`
    추가 — 토큰 파싱은 이 파일 하나로 수렴. 기존 "Bearer 값 = tenant_id" 픽스처/테스트는
    `verify_token`의 폴백 경로로 그대로 통과(하위호환, 회귀 없음). 신규 `app/routers/dev_auth.py`가
    `POST /v1/dev/token`을 제공하고, `app/main.py`를 `create_app()` 팩토리로 바꿔
    `settings.env == "development"`일 때만 이 라우터를 등록한다(핸들러 내부 분기가 아니라
    라우트 자체가 존재하지 않게). `tests/test_dev_token.py`가 개발 모드 발급/인증과
    `settings.env="production"`일 때 `create_app()`이 만든 앱에서 404 둘 다 확인.
    `SELLFINDER_ENV`는 `app/config.py`에 `env: str = "development"`로 추가(기본값 development).

- 못 한 것과 이유: 없음. C-1~C-6 전부 위 출력으로 완료 확인.

- **A-1 확인 결과 (직접 확인, 총괄자 응답 대기 안 함)**: `git ls-files data-platform/output/manifest`
  결과가 **비어 있다** → A-1 미완료. 지시대로 C-7·C-8은 아직 시작하지 않았다. A-1이 커밋되는 대로
  (`data-platform/output/manifest/regions-{level}-{vintage}.json`이 추적되기 시작하면) 바로 착수한다.

---

## 2026-08-16 (2차) — DISPATCH C-7~C-8 실행 보고

A-1 확인: `git ls-files data-platform/output/manifest` → `regions-sido-2026-01-01.json`,
`regions-sido-2026-07-01.json` 추적 확인 (이후 A가 `regions-sigungu-2026-01-01.json`,
`regions-adm_dong-2026-01-01.json`도 커밋해 지금은 세 레벨 모두 실물이 있다).

- 끝낸 항목: C-7, C-8
- 통과 확인:

  ```
  $ PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe verification/fixtures/vf_56_vintage.py
  A (data-platform) actually publishes:
    level=sido       vintages=['2026-01-01', '2026-07-01']  latest=2026-07-01
    level=sigungu    vintages=['2026-01-01']  latest=2026-01-01
    level=adm_dong   vintages=['2026-01-01']  latest=2026-01-01

  C (backend) advertises:
    level=sido       vintages=['2026-07-01', '2026-01-01']  latest=2026-07-01
    level=sigungu    vintages=['2026-01-01', 'fixture']  latest=2026-01-01
    level=adm_dong   vintages=['2026-01-01']  latest=2026-01-01

  Cross-check — ask C for each vintage A really built:
    C.get(level=sido, vintage=2026-01-01) -> 200 OK
    C.get(level=sido, vintage=2026-07-01) -> 200 OK
    C.get(level=sigungu, vintage=2026-01-01) -> 200 OK
    C.get(level=adm_dong, vintage=2026-01-01) -> 200 OK

  zoom range, sido:
    A manifest : minzoom=0 maxzoom=10
    C response : minzoom=0 maxzoom=10
  ```

  (이 스크립트는 A의 gitignore된 로컬 집계 파일 `data-platform/output/tiles/manifest.json`을
  기준으로 비교한다 — 이번 회차에 실제로 존재해서 그대로 실행했다. `sigungu`에 C가 추가로
  `fixture`를 더 광고하는 것은 불일치가 아니라 D-12 픽스처를 여전히 서빙하기 때문이다.)

  ```
  $ PYTHONIOENCODING=utf-8 python tools/validate_contracts.py --check-manifest backend/samples/manifest.json
    매니페스트 검증: level=sigungu, vintage=fixture
  통과: 경고 0건

  $ PYTHONIOENCODING=utf-8 python tools/validate_contracts.py --check-scores backend/samples/scores.json
    점수 응답 검증: 5행, level=sigungu
  통과: 경고 0건
  ```

  ```
  $ cd backend && .venv/Scripts/python.exe -m pytest tests -q
  32 passed in 0.69s
  ```

- 구현 요약:
  - C-7: `app/services/basemap_registry.py` 전면 재작성. `_VINTAGES`·`_ZOOM_BY_LEVEL`·
    모듈 상수 `FEATURE_ID_PROPERTY` 세 하드코딩을 전부 제거했다. 이제 `level`·
    `boundary_vintage`·`tile_url`·`source_layer`·`feature_id_property`·`minzoom`·`maxzoom`·
    `attribution`은 전부 A의 실제 커밋된 매니페스트 파일에서 그대로 읽는다(지어내지 않음).
    소스는 두 곳: (1) `data-platform/output/manifest/regions-{level}-{vintage}.json`
    (git 추적, D-13이 명시한 경로) — sido 2개, sigungu 1개, adm_dong 1개 파일이 지금 여기
    있다. (2) `data-platform/fixtures/manifest-fixture.json` (D-12 픽스처, git 추적) —
    sigungu에 "fixture" 빈티지 하나를 더한다. **의도적으로 gitignore된
    `data-platform/output/tiles/*`는 절대 읽지 않는다** — D-11이 막으려던 바로 그
    "생산자 로컬에만 있는 산출물을 소비자가 몰래 읽는" 패턴이다.
  - 신뢰도(sign) 정책만 유일하게 레벨 기반 상수(`_SIGNED_LEVELS = {"adm_dong"}`)로
    남겼다 — A의 매니페스트에는 서명 정책 필드가 없고, 이건 경계/줌/빈티지처럼 A의 산출물과
    어긋날 수 있는 데이터가 아니라 C가 스스로 내리는 "어느 레벨을 서명된 URL 뒤에 둘지"
    제품 결정이라서다.
  - 정렬 버그를 하나 직접 잡았다: sigungu가 이제 실물 빈티지("2026-01-01")와 D-12
    픽스처("fixture")를 동시에 갖는데, 문자열 그대로 내림차순 정렬하면 `"fixture" >
    "2026-01-01"`이라 픽스처가 "최신"으로 잘못 나온다. `(vintage != "fixture", vintage)`
    튜플 키로 픽스처가 항상 실물 날짜 뒤로 가도록 정정했다 — `test_manifest_sigungu_prefers_real_vintage_over_fixture`로 고정.
  - `app/routers/basemap.py`: `basemap_registry.NoBoundaryArtifactsError`를 잡아
    503 `BOUNDARY_MANIFEST_NOT_PUBLISHED`로 변환 (C-8). 계약에 이 에러 코드가 아직
    정의돼 있지 않다 — 아래 §6 질문 참고.
  - `app/services/prediction_store.py`: `create_run`의 기본 `region_level`을
    `"adm_dong"` → `"sigungu"`로 바꿨다. 이건 C-7의 부작용으로 반드시 필요했다 — 바꾸지
    않았다면 `run_demo01` 시드가 앱 임포트 시점에 `basemap_registry.latest_vintage("adm_dong")`을
    호출했을 때, 그 시점엔 (이번 회차 초반) adm_dong 매니페스트가 아직 없어
    `NoBoundaryArtifactsError`가 임포트를 그대로 죽였을 것이다. 데모 `region_id`가
    5자리(예: `41135`)라 애초에 sigungu 자릿수(D-15가 이미 `samples/scores.json`에서
    같은 결론)였던 것과도 맞다.
  - 테스트: `tests/test_basemap.py`를 A의 실제 값(진짜 `tile_url` 프리픽스, 진짜
    minzoom/maxzoom, sigungu 이중 빈티지)에 맞춰 다시 썼고, D-13의 503 분기는 지금
    sido/sigungu/adm_dong 세 레벨 모두 실물이 있어 `level` 쿼리 enum으로는 트리거할 수
    없어서 `monkeypatch`로 라우터 단까지 end-to-end 확인하는 테스트를 추가했다.
    `tests/test_basemap_registry.py`를 신설해 registry 단위에서도
    `NoBoundaryArtifactsError`(미발행 레벨)와 세 레벨 모두 정상 해석됨을 고정했다.

- 못 한 것과 이유:
  - **정정 사항 (같은 회차, 총괄자가 별도로 지적)**: `backend/samples/manifest.json`이
    `samples/scores.json`(sigungu/fixture)과 레벨·빈티지가 어긋나 있었다. A의
    `data-platform/fixtures/manifest-fixture.json` 값을 그대로 복사해 정정했다 (커밋
    `61c4eaf`, C-7 이전에 별도 커밋 완료).
  - **ADR-002 "C가 할 일" 5번 — 미착수**: "개발 서버가 `data-platform/fixtures/`를
    `/artifacts/`로 정적 서빙"이 아직 없다. 지금 매니페스트가 광고하는
    `http://localhost:8000/artifacts/...` URL은 실제로 아무것도 서빙하지 않는 죽은
    링크다 — D의 실통합(D-5, `.pmtiles` 바이트를 실제로 받아야 하는 부분)이 이것 없이는
    완주할 수 없다. 오늘 지시(C-7·C-8)에는 없었고, C-1~C-8 어느 항목의 완료 판정에도
    걸리지 않아 범위를 넘지 않으려 손대지 않았다. 다음 지시에 넣어달라.

## §6 질문 (D-10 절차 — 추측하지 않고 여기 남긴다)

- **`BOUNDARY_MANIFEST_NOT_PUBLISHED`는 내가 지은 에러 코드다.** `04_api_contract.yaml`에
  이 상황(레벨 자체가 아직 발행되지 않음, 503)에 대한 기존 코드가 없어서 만들었다.
  `BOUNDARY_VINTAGE_NOT_FOUND`(404, 레벨은 있는데 그 빈티지가 없음)와는 의도적으로
  구분했다. jin/총괄자가 이 이름을 계약에 확정해줬으면 한다 — 지금은 계약 미등재 상태로
  구현만 있다.

---

## 2026-08-16 (3차) — VF-004 재확인 (검증 2회차 타이밍 정정)

검증 2회차(`0497f4f`)는 VF-004를 "여전히 열림"으로 판정하면서 `basemap_registry.py`
리라이트가 "워킹트리에만 있고 미커밋"이라고 적었다. 그 판정은 커밋 `a760b31`이 들어오기
**직전 시점**의 관측이다 — `git log`상 `a760b31`(C-7·C-8 커밋)이 `0497f4f`(검증 2회차 커밋)
**보다 먼저** 마스터에 올라가 있다. 즉 검증자가 관측한 뒤 보고서를 쓰는 사이에 내 커밋이
먼저 들어갔고, 검증자는 재확인 없이 관측 시점 상태로 기록·커밋한 것으로 보인다. 지금
`backend/`는 클린하다(`git status --short backend/` 출력 없음) — 커밋할 워킹트리 변경이 없다.

재확인용으로 총괄자가 지정한 세 가지를 이 시점(`a760b31` 이후, 현재 HEAD `0497f4f`)에서
다시 돌렸다:

```
$ PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe verification/fixtures/vf_56_vintage.py
A (data-platform) actually publishes:
  level=sido       vintages=['2026-01-01', '2026-07-01']  latest=2026-07-01
  level=sigungu    vintages=['2026-01-01']  latest=2026-01-01
  level=adm_dong   vintages=['2026-01-01']  latest=2026-01-01

C (backend) advertises:
  level=sido       vintages=['2026-07-01', '2026-01-01']  latest=2026-07-01
  level=sigungu    vintages=['2026-01-01', 'fixture']  latest=2026-01-01
  level=adm_dong   vintages=['2026-01-01']  latest=2026-01-01

zoom range, sido:
  A manifest : minzoom=0 maxzoom=10
  C response : minzoom=0 maxzoom=10
```

- sido 빈티지: 2026-01-01, 2026-07-01 **둘 다** 나옴. latest=2026-07-01. 없는
  2025-01-01은 목록에 없음 — 지시한 세 조건 전부 충족.
- minzoom: A와 C 모두 0으로 일치.

```
$ backend/.venv/Scripts/python.exe -m pytest backend/tests -q
32 passed in 0.67s
```

회귀 없음. C-7·C-8 코드·테스트는 이미 `a760b31`에 커밋돼 있고 이 시점 기준으로도 그대로
유효하다 — 추가로 커밋할 변경분이 없어 이 노트만 남긴다.
