# DECISIONS — 확정 결정 기록

**여기 있는 것은 재논의하지 않는다.**

에이전트는 세션이 끝나면 컨텍스트를 잃는다. 이 파일은 남는다.
같은 논쟁이 다시 올라오면 답하지 말고 이 파일의 해당 항목을 가리켜 닫는다.

각 항목은 **근거 문서**를 함께 적는다. 결정의 본문이 아니라 근거를 가리키는 것이 원칙이다
(본문을 복사하면 계약이 갱신될 때 이 파일이 거짓말을 시작한다).

---

## 제품 정의

### D-01. 예측 단위는 업종이 아니라 테넌트의 SKU 다
근거: `shared/contracts/00_product_spec.md`

기업용 B2B SaaS 다. "카페 업종이 잘 되는 동네"를 찾는 상권분석 툴이 아니라,
"우리 회사의 이 제품(SKU)이 잘 팔릴 동네"를 찾는 제품이다.
지역×카테고리 단위로 회귀하려는 설계는 전부 이 결정 위반이다.

### D-02. 채널은 1급 차원이다. 예측 키 = (제품 × 지역 × 채널 × 기간)
근거: `shared/contracts/00_product_spec.md`, `01_domain_model.json`

네 축 중 하나라도 빠진 예측 응답은 계약 위반이다.
채널을 사후 필터로 취급하는 설계는 허용되지 않는다.

---

## 점수·모델

### D-03. T0 테넌트에는 금액 추정을 반환하지 않는다 (null 고정)
근거: `shared/contracts/05_scoring_spec.md` §2

자사 판매 데이터가 없는 테넌트에 금액을 추정해 주는 것은 근거 없는 숫자를 파는 것이다.
`expected_revenue_krw` 는 항상 `null`, `confidence.level` 상한은 medium.
UI 는 금액 자리에 데이터 업로드 안내와 상대 랭킹만 표시한다.

### D-04. 요인 로그 기여도의 합 = 최종 배수의 로그. 오차 < 1e-6
근거: `shared/contracts/05_scoring_spec.md` §1

승법 요인 모델의 불변식이다. 이게 깨지면 화면에 보여준 요인 분해가 실제 점수와 무관해지고,
**설명이 거짓이 된다.** 단위 테스트로 강제한다. 8개 `factor_key` 는 고정이며 추가·개명 불가.

---

## 지도 (ADR-001)

아래 5개는 모두 `shared/contracts/ADR-001-map-tiles.md` 및 `04_api_contract.yaml` v0.2.1 근거.
A/C/D 세 곳이 독립적으로 같은 질문을 제기해 jin 이 확정한 사안이다.

### D-05. 경계 타일(A) 과 점수 JSON(C) 을 분리하고 클라이언트(D) 에서 조인한다
- 경계 지오메트리: A 가 `.pmtiles` **정적 아티팩트**로 생산. A 는 타일 서빙 API 를 만들지 않는다.
- 예측 점수: C 가 경량 JSON 으로 서빙.
- 조인: D 가 MapLibre `setFeatureState` 로 클라이언트에서 결합.
- **서버가 둘을 하나의 타일로 합치지 않는다.** 테넌트 데이터를 타일에 굽는 순간 CDN 캐시가 불가능해진다.

### D-06. `/predictions/{run_id}/tiles/{z}/{x}/{y}.mvt` 는 폐기되었다
이 엔드포인트를 구현하거나 참조하는 코드는 전부 제거 대상이다.

### D-07. `/predictions/{run_id}/scores` 는 튜플배열 + schema 형식이다
- 객체 배열이 아니다. `{"schema":[...], "scores":[["1111051500",87.4,"high"]]}`.
  3,500행에서 키 반복이 사라져 페이로드가 약 60% 줄어든다.
- **페이지네이션 없음** — 계약에서 문서화된 유일한 예외다. 지도는 전체 지역을 한 번에 칠해야 한다.
- **금액 미포함.** `expected_revenue_krw` 는 상세 조회 전용이다.
- `score_range`(min/max) 필수 — 없으면 클라이언트가 색상 스케일을 고정하지 못해
  필터를 바꿀 때마다 지도 색이 흔들린다.
- **`/predictions/{run_id}/regions` 는 그대로 유지된다.** `/scores` 가 대체하는 것이 아니다.

검증: `python tools/validate_contracts.py --check-scores <파일>`

### D-08. `prediction_run` 에 `boundary_vintage` 를 추가한다
어느 시점의 행정경계 위에서 계산된 예측인지 응답이 스스로 밝혀야 한다.
빈티지는 보존하며 덮어쓰지 않는다. "최신" 으로 조회하면 시계열이 어긋난다.

### D-09. GeoJSON 은 `custom_catchment` 에만. 표준 행정경계는 전부 타일이다
sido / sigungu / adm_dong 을 GeoJSON 으로 내보내는 설계는 이 결정 위반이다.
GeoJSON 은 `/scores` 응답의 `custom_geometries` 필드에만 인라인으로 등장한다.

검증: `python tools/validate_contracts.py --check-manifest <파일>`

---

## 절차

### D-10. 계약은 `shared/contracts/` 파일뿐이다. 타 에이전트의 구현 코드는 계약이 아니다
근거: `shared/contracts/README.md` "절대 규칙"

- 다른 에이전트의 코드나 문서를 읽고 계약으로 오인해 자기 작업을 되돌리지 마라.
  **실제로 A 가 이것 때문에 정상 파이프라인을 되돌릴 뻔했다** (C 의 구 구현을 계약으로 오인).
- 계약과 자기 구현이 다르면 **계약이 이긴다.** 구현을 고친다.
- 계약을 바꿔야 하면 자기 폴더에 `CONTRACT_CHANGE_REQUEST.md` 를 쓴다.
  승인·병합은 jin 만 한다. CCR 은 **제안**이지 결정이 아니며,
  병합되지 않은 CCR 을 근거로 구현하면 안 된다.
- 미결이면 자기 폴더 문서에 질문으로 남기고, 계약 기준으로 진행한다.

---

## 아티팩트 발행 · 지역 레벨 · 줌 (ADR-002)

근거: `shared/contracts/ADR-002-artifact-publishing.md`
총괄자 첫 스윕이 발견한 차단 요인에 대한 응답이다.

### D-11. 매니페스트는 git 에 커밋하고, `.pmtiles` 는 커밋하지 않는다
`output/` 을 `manifest/`(추적 O) 와 `tiles/`(추적 X) 로 분리한다.
`.pmtiles` 는 한 번 들어가면 히스토리에서 지울 수 없고 빈티지마다 저장소가 불어난다.
매니페스트는 계약 형태의 인수인계물이므로 반대로 반드시 추적한다.

### D-12. `sigungu` 픽스처 타일을 커밋해 D 를 지금 뚫는다
`data-platform/fixtures/regions-sigungu-fixture.pmtiles` (5MB 이하) + `manifest-fixture.json`
(`boundary_vintage: "fixture"`). 오브젝트 스토리지는 v1 배포 과제이고, 그때까지 D 를 세워두지 않는다.
개발 `tile_url` 은 `http://localhost:{PORT}/artifacts/...` — 절대 URL 규약은 개발에서도 지킨다.

### D-13. C 는 빈티지를 지어내지 않는다. A 의 매니페스트를 읽는다
`available_vintages` 하드코딩 금지. `data-platform/output/manifest/*.json` 을 읽어 구성한다.
파일이 없으면 **빈 배열이 아니라 503 + 사유** — 빈 배열은 "빈티지가 없다"는 거짓 정보다.
A 의 레벨 산출 순서는 `sigungu` → `adm_dong` → `sido`.

### D-14. 레벨은 사용자가 고른다. 줌으로 자동 전환하지 않는다
| level | minzoom | maxzoom |
|---|---|---|
| `sido` | 0 | 10 |
| `sigungu` | 4 | 12 |
| `adm_dong` | 5 | 14 |

겹쳐도 무방하다. maxzoom 초과는 오버줌으로 처리하고 타일을 더 만들지 않는다.
레벨별 실제 값은 A 의 매니페스트가 정하고 C 는 그대로 전달한다.

### D-15. `backend/samples/scores.json` 은 `sigungu` 로 정정한다
`region_level` 을 `"sigungu"` 로, `boundary_vintage` 를 `"fixture"` 로. `region_id` 는 그대로 둔다.
픽스처 타일이 `sigungu` 이고 `distribution_push` 기본 단위도 `sigungu` 다.

---

## 인증 (ADR-003)

근거: `shared/contracts/ADR-003-auth.md`

### D-16. 토큰 형태는 지금 확정하고 IdP 선택은 미룬다
JWT 클레임 고정: `sub` / `tenant_id` / `role` / `region_scope` / `exp`.
`region_scope` 는 지역코드 **접두사 매칭** (`"41"` → `41135` 포함), 비었으면 전체.
검증은 `verify_token(raw) -> TokenClaims` **단일 지점**으로 추상화한다 — 애플리케이션 코드는
`TokenClaims` 만 보고, 토큰 원문을 다른 곳에서 파싱하지 않는다. IdP 벤더는 이 함수 뒤에 숨는다.
콘솔 v1 로그인은 이메일 + 매직링크.

### D-17. 개발 전용 토큰 엔드포인트는 운영에 존재하면 S1 이다
`POST /v1/dev/token` 은 `SELLFINDER_ENV=development` 일 때만 등록한다.
운영 빌드에 이 경로가 있으면 **S1 치명 결함**이며 검증 에이전트의 확인 항목이다.
그 외 재확인: `tenant_id` 가 요청에 오면 400 `TENANT_ID_NOT_ALLOWED`(조용히 무시 금지),
`tenant_id` 를 DB 세션 변수에 넣어 RLS 로 강제, **캐시 키에 `tenant_id` 포함**,
`region_scope` 는 조회·내보내기·타일 **전 경로**에 적용. D 는 토큰을 `localStorage` 에 넣지 않는다.

---

## 택소노미 (ADR-004)

근거: `shared/contracts/ADR-004-taxonomy-mapping.md`

### D-18. 1차 조인 키는 `sbiz`. `ksic` 는 보조, `card_mcc` 는 후속
`competition` 요인의 원천인 점포 수를 무료로 얻을 수 있는 유일한 경로가 `sbiz` 다.
`card_mcc` 는 라이선스 확보 전까지 스키마에만 두고 파이프라인에 넣지 않는다.
따라서 `demand_signal.spend_krw` 는 당분간 항상 null 이고, `spend_index` 를 점포 수와
지역 소비력 프록시로 유도한다. 이는 D-03(T0 금액 null)과 충돌하지 않는다 — 일관성 확인이다.

### D-19. 택소노미 매핑이 없는 노드는 confidence 를 강제 하향한다
상위 노드 매핑을 상속하고, 그래도 없으면 `confidence.level = 'low'` 로 내린다
(`05_scoring_spec.md` §4 의 강제 하향 조건). **조용히 0 으로 채우지 마라.**

---

## 타일 조인 키 (ADR-005)

근거: `shared/contracts/ADR-005-tile-join-key.md`, `04_api_contract.yaml` v0.2.2

### D-20. `region_id` 는 타일 피처의 **properties 에 문자열로** 싣는다. 네이티브 feature id 는 조인 키가 아니다
검증 1회차 `VF-003` — A 의 실제 타일·C 의 매니페스트·D 의 조인 코드를 붙이면 **0/5 매칭**,
에러 없이 지도 전체가 회색이었다. 원인은 `ADR-001` 안의 두 문장이 서로 반대였던 것이다
(D 에게는 "`feature_id_property` 를 키로 써라", A 에게는 "속성이 아니라 id 로 넣어라").
**A 도 D 도 자기 문서를 지켰다. 계약이 틀렸다** — `promoteId` 가 속성을 id 로 승격시키는
표준 메커니즘이라는 사실을 모른 채 쓰인 문장이었다. ADR-001 의 해당 줄은 취소선 처리했다.

- A: `region_id` 를 properties 에 원문 문자열로 유지. 매니페스트에서 `id_map_path` 제거.
  **빌드가 "광고한 속성이 타일에 실제로 있는지"를 스스로 검사하고 없으면 실패한다.**
- C: `FEATURE_ID_PROPERTY` 하드코딩 제거, A 매니페스트 값 그대로 전달 (D-13 과 같은 성격).
- D: **코드 변경 없음.** `promoteId` 유지. 조인 성립을 테스트로 고정한다 (VF-009).

정수 변환 방식(네이티브 id + `id_map.json`)은 기각했다. 선행 0·2⁵³ 초과·해시 충돌이라는
조용한 실패 경로 3종을 만들고, 그 실패가 예외가 아니라 **빈 지도**로 나타난다.
타일 크기 증가는 3,500 피처 기준 gzip 후 수십 KB 로 무시 가능하다.

완료 판정: `verification/fixtures/vf_56_join.mjs` 재실행이 전건 매칭이면 VF-003 을 닫는다.

---

## 기록 규칙

새 결정이 확정되면 여기에 `D-NN` 으로 추가한다. 항목은 삭제하지 않는다.
결정이 뒤집히면 지우지 말고 **취소선과 대체 항목 번호**를 남긴다 —
왜 뒤집혔는지가 다음 논쟁을 막는다.
