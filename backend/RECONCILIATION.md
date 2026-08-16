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

---

## 2026-08-16 (4차) — VF-010 실행 보고

`06_governance.md` §2.3 / `05_scoring_spec.md` §8-6: `coverage_flag='suppressed'`
셀의 원시값은 응답·로그·에러 메시지 **어디로도** 나가면 안 된다. 지금까지
`backend/app` 전체에 "suppressed" 문자열이 0회 등장했다 — 차단이 B의 생성기
단계에만 있었다.

- 끝낸 항목: VF-010 (3개 경로 동시 차단 + 단일 차단 지점)
- 구현 요약:
  - **단일 차단 지점**: `app/services/privacy.py` 신설.
    `redact(value, coverage_flag, ...)` — 응답에 실릴 값을 반환하는 유일한
    통로, suppressed면 `None` + "값을 뺐다"는 사실만 로그(원시값은 로그에도
    안 씀). `guard_or_raise(...)` — 값을 거부해야 하는 자리용,
    `SuppressedValueError`를 던지며 이 예외의 `__str__`은 `region_id`·`field`만
    담고 원시값은 **생성자 시점부터 아예 받지 않는 것처럼** 메시지에 넣지 않는다.
    나중에 xlsx/csv 내보내기가 붙어도 이 두 함수를 통하기만 하면 같은 규칙이
    자동 적용된다 — VF-005(금액은 막고 신뢰도는 안 막음)처럼 경로마다 따로
    구현하다 하나 빠뜨리는 실패를 구조적으로 막는 목적이다.
  - **응답 경로**: `prediction_store.RegionScore`에 `coverage_flag: str | None = None`
    추가(계약의 `demand_signal.coverage_flag` 값과 동일한 타입, 기본값은 기존
    5개 데모 지역에 영향 없음). `routers/predictions.py`의 `_expected_revenue_for()`가
    T0 검사(D-03, 기존)와 `privacy.redact()`(신규) 둘 다 통과해야 `expected_revenue_krw`를
    채운다 — 하나라도 걸리면 null. `/scores`는 애초에 금액을 안 실어(D-07) 이
    경로엔 해당 없음, 확인만 함.
  - **로그 경로**: `privacy.redact()`가 재시도 없이 자체적으로
    `logging.getLogger("sellfinder.privacy")`에 사실만 기록(원시값 제외).
  - **에러 메시지 경로**: `SuppressedValueError`가 생성자 차원에서 원시값을
    받지 않아 구조적으로 못 새고, `app/main.py`에 전역 `Exception` 핸들러를
    추가해 **어떤** 미처리 예외든 `str(exc)`를 클라이언트에 그대로 돌려주지
    않게 방어했다(심층 방어 — SuppressedValueError뿐 아니라 다른 예외 타입이
    실수로 값을 물고 와도 이 겹이 막는다). 서버 로그에는 `exc_info`로 남아
    디버깅은 가능.
  - `create_run()`에 `regions: list[RegionScore] | None = None` 선택 인자를
    추가해, 기존 데모 5개 행을 건드리지 않고 테스트 전용으로 suppressed 셀
    시나리오를 실제 요청/응답 파이프라인에 태울 수 있게 했다.

- 완료 판정 확인 (지시된 3가지):

  ```
  $ grep -rl "suppressed" backend/app --include="*.py"
  backend/app/routers/predictions.py
  backend/app/services/prediction_store.py
  backend/app/services/privacy.py
  ```

  ```
  $ backend/.venv/Scripts/python.exe -m pytest backend/tests -q
  39 passed in 0.72s
  ```

  (7개 신규 테스트가 `test_privacy.py`에 있다 — 응답 경로 2개, 로그 경로 2개,
  에러 메시지 경로 3개. 실제 원시값 918273645를 심어 `/regions`·`/scores`
  응답 본문 텍스트에 그 문자열이 없는지, `caplog`로 로그 텍스트에 없는지,
  `SuppressedValueError` 문자열·전역 500 핸들러 응답 본문에 없는지를 각각
  직접 검사한다.)

- 못 한 것과 이유: 없음. 지시된 3개 경로(응답·로그·에러 메시지) 전부 테스트로
  고정했다.

## §6 질문 추가 (D-10 절차 — 추측하지 않고 여기 남긴다)

- **B의 `coverage_flag` → API 인터페이스 미정**: 지금 `RegionScore.coverage_flag`는
  내가 백엔드 내부에만 추가한 필드고, `intelligence/synthetic/demand_gen.py`가
  만드는 실제 `demand_signal.coverage_flag`가 `/backend`로 어떤 경로로
  들어올지(동기 호출? 잡 결과 스냅샷? region_feature 조인?)는 아직 어디에도
  정의돼 있지 않다 — 이전 §6 질문("backend ↔ intelligence 내부 호출 계약")과
  같은 미결이다. 지금 이 필드는 오직 `privacy.redact()`가 실제로 호출되는
  실제 파이프라인을 테스트로 고정하기 위한 자리이며, B의 실제 연동이
  붙을 때 이 필드의 채움 방식(그리고 필요하면 `demand_signal` 원본 셀 값 자체를
  별도 필드로 들고 있을지)은 그 인터페이스가 확정된 뒤 정할 문제로 남겨둔다.
  지금 추측해서 만들지 않았다.

---

## 2026-08-16 (5차) — VF-013 실행 보고

검증 4회차가 VF-010 대응(`19373ff`) 범위 밖의 4번째 경로를 찾았다: `GET
/v1/predictions/{run_id}/regions?sort=revenue_desc`(및 `profit_desc`)의 정렬 키가
`r.expected_revenue_p50` **원본**(redact 전)을 읽어서, `expected_revenue_krw` 자체는
`null`로 정확히 가려도 **정렬 순서**가 suppressed 지역의 원시값 상대 크기를 드러냈다.
VF-010이 막은 응답 본문·로그·에러 메시지 세 경로와 다른, 정렬이라는 네 번째 경로다.

- 끝낸 항목: VF-013
- 원인: `_expected_revenue_for()`(VF-010에서 신설, 응답 필드용 redact 초크포인트)를
  거치지 않고 정렬 키 계산이 `r.expected_revenue_p50 or -1`을 직접 읽고 있었다 —
  정렬 기능 자체가 아니라 정렬 키가 초크포인트를 우회한 것.
- 수정: `backend/app/routers/predictions.py`의 `get_prediction_regions()`에서
  `revenue_by_region_id = {r.region_id: _expected_revenue_for(r, run) for r in regions}`를
  정렬 **전에** 한 번만 계산해, 정렬 키(`revenue.p50 if revenue is not None else -1`)와
  응답 필드(`expected_revenue_krw=revenue_by_region_id[r.region_id]`) 둘 다 **같은
  redact-후 값**을 쓰도록 단일화했다. suppressed(또는 T0)라 null된 지역은 `-1`
  sentinel로 최하위 취급되며, 원시 크기가 정렬 위치에 반영되지 않는다. 정렬 기능
  자체(내림차순, revenue_desc/profit_desc)는 그대로 유지했다 — 키 계산 지점만 고쳤다.
  (부수 효과: 이 정렬 키는 T0에도 동일하게 적용되므로, 이전까지 있었을 T0 케이스의
  같은 유형 정렬 유출도 같은 수정으로 같이 막힌다.)
- 회귀 테스트: `backend/tests/test_privacy.py`에
  `test_revenue_desc_sort_does_not_leak_suppressed_raw_magnitude` 추가. 원시 p50이
  일반 지역(20,000,000)보다 훨씬 큰 suppressed 지역(918273645)을 같은 run에 넣고
  `sort=revenue_desc`로 조회해, 일반 지역이 suppressed 지역보다 먼저 나오는지 +
  원시값 문자열이 응답 본문에 없는지 확인.

- 완료 판정 재현 (지시된 그대로, 별도 스크립트로 독립 실행):

  ```
  $ backend/.venv/Scripts/python.exe /tmp/vf013_repro.py
  status=200
  order: [('11305', {'p10': 10000000, 'p50': 20000000, 'p90': 30000000}), ('99999', None)]
  raw value 999999999 present in response body? False
  suppressed region ranked first? False
  ```

  (원시 p50=999,999,999인 suppressed 지역(99999)과 p50=20,000,000인 일반 지역(11305)을
  같은 run에 넣고 `sort=revenue_desc`로 조회 — suppressed 지역이 1위로 오지 않고,
  원시값 문자열이 응답 어디에도 없다.)

  ```
  $ backend/.venv/Scripts/python.exe -m pytest backend/tests -q
  40 passed in 0.66s
  ```

- 못 한 것과 이유: 없음.

---

## 2026-08-16 (6차) — DISPATCH-2 C-1~C-5 실행 보고

이번 사이클의 핵심 사건(총괄자 표현): **`_build_demo_regions()` 삭제.** `backend/app`에
하드코딩 점수 테이블이 더 이상 존재하지 않는다 — `/scores`·`/regions`는 이제 전부
`/intelligence`의 실제 `predict_batch` 결과다.

### 끝낸 항목: C-1, C-2, C-3, C-4, C-5

### C-1 — `POST /v1/predictions`, 즉시 202 + `run_id`

- `app/services/job_runner.py` 신설: 백그라운드 스레드로 잡을 돌리고 핸들러는 `join()`하지
  않는다. `_FAKE_JOB_DELAY_SECONDS = 0.2` 지연을 잡 본문에 걸어 "202가 계산을 기다리지
  않는다"를 벽시계 타이밍으로 직접 증명 가능하게 했다(코드를 읽어서 "비동기처럼 보인다"가
  아니라 실측).
- `app/services/prediction_store.py`: `create_queued_run`(status="queued", regions=[]) /
  `complete_run` / `fail_run` 3상태 추가. `create_run`(기존 동기 데모시딩 경로)은
  테스트 전용으로 남기고 신규 경로와 분리.
- `tests/test_predictions_create.py::test_create_prediction_returns_202_immediately`가
  `elapsed < job_runner._FAKE_JOB_DELAY_SECONDS / 2` 로 강제.

### C-2 — 잡 워커가 B의 `predict_batch`를 in-process 호출 (이 사이클의 핵심)

- `intelligence/README.md`(B-1, 커밋 `b01e951`) 공개 확인 후 착수 — 총괄자 응답을 기다리지
  않고 직접 파일 존재로 확인했다(지시대로).
- `app/services/intelligence_client.py` 신설. README를 그대로 따랐다:
  - `SyntheticFeatureStore`를 프로세스당 1회만 빌드(README §2: "predict_batch 호출마다
    새로 하지 마라").
  - README §4-2가 요구한 대로 `KeyError`/`IndexError`/`ZeroDivisionError`를
    `PredictionInputError(ValueError)`로 감싼다.
  - `as_of = f"{period}-01"`을 항상 강제(README §4-3, 05_scoring_spec §5.1 누수 방지).
- `prediction_store.compute_regions()` 신설 — `_build_demo_regions()`를 **완전히 대체**.
  `predict_batch` 결과를 `total_multiplier` 기준으로 직접 정렬해 `rank`/`opportunity_score`/
  `score_percentile`을 계산한다(README §5: "opportunity_score는 여기서 계산되지 않는다.
  C가 total_multiplier 기준으로 직접 정렬해야 한다" — B의 지시를 그대로 구현).
- **이음매 테스트를 먼저 만들었다** (총괄자 원칙 그대로): `tests/test_intelligence_seam.py`가
  B의 `predict_batch`를 직접 호출한 결과(ground truth)와, 같은 요청을 실제 `POST
  /v1/predictions` → 잡 워커 → `/scores`로 통과시킨 결과를 **region_id 순서까지 완전히
  일치**하는지 대조한다. 통과 확인(재현 가능한 실제 출력):

  ```
  $ backend/.venv/Scripts/python.exe -m pytest backend/tests/test_intelligence_seam.py -v
  test_predict_batch_ground_truth_is_not_degenerate PASSED
  test_scores_response_matches_predict_batch_ranking PASSED
  ```

- **미결이었던 실질 문제 — 값을 지어내지 않고 직접 실행해서 확인한 것들**:
  1. **candidate region_ids**: backend에는 실제 지역 카탈로그가 없다. B의 합성
     `region_feature`는 **adm_dong 레벨에만** 실제로 채워져 있음을 직접 실행으로 확인했다
     (sigungu/sido `region_id`로 조회하면 전부 피처가 `None` → 모든 요인이 중립(1.0)으로
     붕괴 — README §4-3 "저장소에 없는 지역 → 중립"이 정확히 이 경우다). 그래서
     `create_run()`의 기본 `region_level`을 `"sigungu"` → `"adm_dong"`으로 바꿨다 —
     이제 실제로 분산된 점수가 나온다(직접 확인: `total_multiplier` 0.59~1.70).
  2. **`taxonomy_node_id`/`channel`**: `PredictionRequest.product_ids`는 backend에 상품
     카탈로그(`POST /products`)가 없어 실제 분류 노드로 해석할 수 없다. **지어내지 않고**
     계약(`04_api_contract.yaml`)이 스스로 전체 문서에서 반복 사용하는 실제 예시 쌍
     (`TX-FOOD-BEV-COFFEE-RTD` / `"cvs"`, PredictionDetail의 RTD커피/편의점 예시)을
     임시값으로 썼다 — `intelligence_client.py`에 이유를 명시하고 아래 §질문에도 남겼다.
  3. **`confidence_level`**: B의 모델은 아직 신뢰도를 계산하지 않는다(README에 명시 없음,
     `05_scoring_spec.md §4` 공식 미구현). 지어내지 않고 **`"low"`로 고정**했다 — D-19와
     같은 원칙("모르면 강제 하향, 조용히 채우지 않는다"). `medium`/`high`를 근거 없이 만들지
     않았다.

### C-3 — `Idempotency-Key`

- `prediction_store.find_run_id_for_idempotency_key`/`remember_idempotency_key` — 24시간
  TTL, `(tenant_id, key)`로 스코핑(계약 예시가 `tenant_id`로 나뉘지 않으면 다른 테넌트의
  키와 충돌할 수 있어서). 같은 키 재요청은 새 run을 만들지 않고 기존 run의 **현재** 상태를
  반환한다(원 202 응답을 그대로 재생하는 게 아니라 최신 status로 — "queued"였다가 이미
  끝났으면 "succeeded"를 보여주는 편이 더 유용하다고 판단).
- 테스트 3개: 같은 키 재사용 시 같은 `run_id`, 테넌트가 다르면 같은 키라도 다른 `run_id`,
  키가 없으면 매번 새 `run_id`.

### C-4 — 에러 봉투 `request_id` + 감사 로그 미들웨어

- (인용 정정: 총괄자 지시는 "06_governance.md §3"이라고 썼는데, 실제로 감사·재현성 내용은
  §4다 — §3은 "데이터 리니지·라이선스"로 무관하다. 지시 의도(§4 내용)를 따라 구현했다.)
- `app/main.py`에 `request_id_and_audit_middleware` 신설 — 요청마다 `request_id` 발급,
  `X-Request-Id` 응답 헤더, 요청 단위 감사 로그 1줄(method/path/status/duration/request_id).
- 세 예외 핸들러(HTTPException/RequestValidationError/전역 Exception) 전부
  `error.request_id`를 채우도록 수정 — `04_api_contract.yaml` `Error` 스키마의
  `required: [code, message, request_id]`를 지금까지 어기고 있었다.
- `app/security.py::get_tenant_id`(신원 확인의 유일한 지점, ADR-003 §3)에 행위자
  감사 로그 1줄 추가(tenant_id/method/path/request_id) — 토큰을 다른 곳에서 다시 파싱하지
  않기 위해 미들웨어가 아니라 여기서 "누가"를 기록한다.
- 테스트 7개: 404/401/422 응답 각각 `request_id` 존재, 두 요청의 `request_id`가 다름,
  성공 응답도 `X-Request-Id` 헤더를 가짐, 인증된 요청이 행위자 감사 로그를 남김, 모든
  요청이 요청 단위 감사 로그를 남김(`caplog`로 직접 검사).

### C-5 — `/api/v1/health` → `/v1/health`

- 라우트 하나만 프리픽스가 달랐다. 정정 + 옛 경로가 진짜 404인지 확인하는 회귀 테스트 추가.
  `grep '@router\.(get|post)'` 로 전 라우터 확인 — 이제 예외 없이 전부 `/v1/` 아래.

### 완료 판정 확인

```
$ backend/.venv/Scripts/python.exe -m pytest backend/tests -q
............................................................             [100%]
60 passed in 1.27s
```

```
$ grep -rn "_build_demo_regions\|demo_regions_snapshot\|_DEMO_REGIONS" backend/app --include="*.py"
(주석 두 줄 외 실제 정의/호출 0건 — 함수 자체가 존재하지 않는다)
```

### §7 질문 (D-10 절차 — 추측하지 않고 여기 남긴다)

- **상품 카탈로그 부재로 `taxonomy_node_id`를 지어내는 대신 계약의 예시 쌍을 임시로 씀**:
  `POST /products`가 아직 없어 `PredictionRequest.product_ids`를 실제 SKU로 해석할 방법이
  없다. `TX-FOOD-BEV-COFFEE-RTD`/`"cvs"`를 `intelligence_client.py`에 명시적 임시값으로
  박아뒀다 — 상품 카탈로그가 생기면 이 상수를 실제 `product.taxonomy_node_id` 조회로
  바꿔야 한다. 이건 backend 내부 스코프(상품 저장소 설계) 문제라 A/B/D 누구의 계약 문제도
  아니라고 판단해 CCR 없이 진행했다 — 이견 있으면 알려달라.
- **`confidence_level`을 전부 `"low"`로 고정한 것**: B의 `predict_batch`가 아직
  `05_scoring_spec.md §4`의 신뢰도 공식을 구현하지 않아서다(README에 confidence 관련
  반환값 언급이 아예 없음). 그 공식이 B 쪽에 붙기 전까지는 이 고정값이 유지된다 — B가
  신뢰도를 반환하기 시작하면 `compute_regions()`의 이 부분을 교체해야 한다.
- **ADR-002 "C가 할 일 #5"(정적 파일 서빙)는 여전히 미착수** — 5차 보고에서 이미 남긴
  질문이고 이번 사이클에서도 손대지 않았다. `tile_url`이 아직 죽은 링크다.
- **`GET /predictions/{run_id}`(상태 요약) 엔드포인트 미구현** — 계약에 정의돼 있고
  "queued"에서 "succeeded"로의 전이를 관찰할 자연스러운 자리이지만, DISPATCH-2 C 표에
  없어 이번엔 안 만들었다. 지금은 `/regions`가 빈 배열을 반환하는 것으로(또는
  `prediction_store.get_run().status`를 직접 봐야) 상태를 짐작해야 한다 — 다음 사이클
  후보로 남긴다.
