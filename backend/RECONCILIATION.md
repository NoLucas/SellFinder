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
