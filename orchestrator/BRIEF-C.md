# BRIEF-C — backend (에이전트 C)

**개정 2** · 근거: `orchestrator/STATUS.md` (스윕 08-15 19:5x, HEAD `33fe4ac`)
읽는 순서: 이 파일 → **`shared/contracts/ADR-003-auth.md`**,
**`ADR-002-artifact-publishing.md`** → `orchestrator/DECISIONS.md` → 네 `RECONCILIATION.md`

> **ADR-002 와 ADR-003 은 반드시 직접 읽어라.** `shared/contracts/README.md` 의 읽기 순서 표는
> `00`~`06` 만 나열하고 ADR 을 포함하지 않는다. 표만 보고 넘어가면 인증 설계 전체를 놓친다.

---

## 지금 상태 (저장소 기준)

| 항목 | 사실 |
|---|---|
| 마지막 커밋 | `849354d` 08-15 18:01 — *align basemap/scores endpoints to contract v0.2.1 (ADR-001)* |
| 폴더 커밋 수 | 5 (최다) · 테스트 **19 passed** |
| 계약 반영 | **경고 — 계약 최종 커밋 `33fe4ac`(19:37)보다 1.6h 이르다.** ADR-002/003 미반영 |
| CONTRACT_CHANGE_REQUEST | 없음 (`849354d` 에서 삭제) |

구현된 것: `GET /v1/basemap/regions/manifest`, `GET /v1/predictions/{run_id}/scores`,
`GET /v1/predictions/{run_id}/regions`, `GET /api/v1/health`,
`app/security.py` 의 `get_tenant_id`(임시: Bearer 값 = tenant_id), `backend/samples/*.json`.

---

## 해소된 것 — 더 신경 쓰지 마라

1. **검증기 플래그 두 개는 이미 추가됐다.** `--check-scores`, `--check-manifest` 지금 돌아간다.
   더 이상 이걸로 막혀 있지 않다.

2. **인증 방식이 확정됐다 (ADR-003).** 네가 jin 에게 올린 IdP 질문의 답이다.
   **벤더는 안 고른다. 대신 클레임 형태를 고정하고 `verify_token` 한 지점으로 추상화한다.**
   지금 네가 필요한 건 그것뿐이다.

3. **A 와의 매니페스트 충돌 — 책임 소재가 정해졌다 (ADR-002 결정 3).**
   *"근본 원인은 C 가 값을 지어낸 것"* 이다. 빈티지는 A 만 알 수 있다.
   **네가 하드코딩을 버리고 A 의 매니페스트를 읽는 쪽으로 정리됐다.**

4. **`sido` 줌 논쟁 종료 (결정 4).** A 의 0 이 채택. 레벨별 값은 A 매니페스트가 정하고
   너는 **그대로 전달**한다. 네 `_ZOOM_BY_LEVEL` 하드코딩도 같이 없어진다.

5. **D 가 제기했던 "backend 가 계약과 다르다"는 이슈는 네 `849354d` 로 해소됐다.**
   D 에게 "이미 해소됨"으로 전달됐다. 다시 설명할 필요 없다.

6. **저장소에 6번째 에이전트(검증자)가 생겼다.** `verification/` — 적대적으로 실행해 보며
   깨진 곳을 찾는 역할이다. 네 코드가 주 대상이다(테넌트 격리가 S1 후보로 지정돼 있다).
   지금 미해결 findings 는 0건이다.

---

## 다음 작업 (우선순위 순)

1. **`backend/samples/scores.json` 을 정정해라 (ADR-002 결정 5). 한 줄이고, D 가 이걸 기다린다.**
   - `region_level` → `"sigungu"` (`region_id` 는 그대로 둔다 — 이미 5자리 sigungu 코드다)
   - `boundary_vintage` → `"fixture"`
   고치면 `--check-scores` 경고 5건이 0 이 된다. **커밋 전에 반드시 통과시켜라.**

2. **`available_vintages` 하드코딩을 제거해라 (결정 3).**
   - `data-platform/output/manifest/*.json` 을 읽어 구성한다. A 가 이제 이걸 커밋한다.
   - **파일이 없으면 빈 배열이 아니라 `503` + 명확한 사유.** 빈 배열은 "빈티지가 없다"는
     거짓 정보이고, D 는 그걸 구분할 방법이 없다.
   - `_ZOOM_BY_LEVEL` 도 없앤다. 줌은 A 매니페스트 값을 그대로 전달한다.
   - **낡은 주석을 지워라**: `basemap_registry.py` 상단의 *"A hasn't published real .pmtiles
     artifacts yet"* 은 사실이 아니다. A 는 냈다. 이 주석 때문에 다음 사람이 또 오해한다.

3. **개발 서버가 `data-platform/fixtures/` 를 `/artifacts/` 로 정적 서빙하게 해라 (결정 2).**
   `tile_url` 은 개발에서도 절대 URL 이다: `http://localhost:{PORT}/artifacts/...`.
   이게 되면 D 의 통합 테스트가 끝까지 간다.

4. **인증을 ADR-003 대로 구현해라. 지금 최대 미구현이다.**
   - JWT 클레임: `sub` / `tenant_id` / `role` / `region_scope` / `exp`
   - **`verify_token(raw) -> TokenClaims` 단일 지점.** 토큰 원문을 다른 곳에서 파싱하지 마라.
     IdP 를 바꿀 때 이 함수 하나만 교체된다.
   - 요청의 쿼리·바디·헤더에 `tenant_id` 가 오면 **400 `TENANT_ID_NOT_ALLOWED`.**
     **조용히 무시하지 마라** — 무시하면 언젠가 누가 그 값을 읽는다.
   - `tenant_id` 를 DB 세션 변수에 넣어 **RLS 로 강제**한다. 애플리케이션 `WHERE` 절만 믿지 마라.
   - **캐시 키에 `tenant_id` 를 포함해라.** 빠뜨리면 캐시를 통해 샌다.
   - `region_scope` 는 **접두사 매칭**이며 조회·내보내기·타일 **전 경로**에 적용한다.
     한 경로만 빠뜨려도 우회된다.

5. **`POST /v1/dev/token` 은 `SELLFINDER_ENV=development` 일 때만 등록해라.**
   운영 빌드에 이 경로가 존재하면 **S1 치명 결함**이고 검증 에이전트의 확인 항목이다.
   등록 조건을 테스트로 고정해 둬라 — 실수로 켜지는 게 정확히 이런 종류의 사고다.
   D 는 이걸로 테넌트 전환·권한별 UI 를 테스트한다.

6. **`POST /predictions` 비동기 골격 (네 §5-4).**
   지금 `predictions.py` 에는 GET 2개뿐이고 POST 가 없다. `00_product_spec.md` Anti-goals 가
   금지한 동기 예측 API 를 피하는 뼈대다. B 의 `predict_batch` 계열은 이미 동작한다(28 tests pass).
   B 도 in-process 호출에 동의했다 — 시그니처가 공개되면 그대로 호출해라.

7. **`/api/v1/health` 프리픽스 통일.** 다른 라우트는 `/v1/...` 인데 health 만 `/api/v1/...` 이다.
   네 §3-4 에서 스스로 지적한 문제의 잔여분이다.

8. **나머지 §5 순서 재개.** 에러 봉투(`request_id`) → 커서 페이지네이션 → `Idempotency-Key`
   → RBAC(`rbac_matrix`) → `/products`, `POST /products:classify`(mock) → 감사 로그 미들웨어.

---

## 확인 방법 — 명령어와 통과 기준

```bash
python tools/validate_contracts.py --check-scores   backend/samples/scores.json
python tools/validate_contracts.py --check-manifest backend/samples/manifest.json
python tools/validate_contracts.py --base origin/master --agent C
backend/.venv/Scripts/python.exe -m pytest backend/tests -q     # 현재 기준선: 19 passed
```

통과 기준:
- `--check-scores`: **오류 0 + 경고 0.** (지금은 경고 5건 — 위 1번을 고치면 0)
- `--check-manifest`: 오류 0.
- 두 샘플은 D 의 통합 테스트 입력이다. **커밋 전에 두 명령을 반드시 통과시켜라.**

이번 회차에 스스로 걸어야 할 테스트:
- 쿼리·바디·헤더 각각에 `tenant_id` 를 넣어 **셋 다 400** 인지
- `SELLFINDER_ENV` 가 development 가 아닐 때 `/v1/dev/token` 이 **404** 인지
- A 매니페스트 파일이 없을 때 `/basemap/regions/manifest` 가 **503** 인지 (빈 배열 아님)
- 서로 다른 `tenant_id` 두 토큰으로 같은 경로를 쳤을 때 캐시가 섞이지 않는지

---

## 하지 말 것

- **빈티지·줌을 하드코딩하지 마라.** A 의 매니페스트가 유일한 출처다. (D-13, D-14)
- **매니페스트 파일 부재 시 빈 배열을 반환하지 마라.** 503 + 사유다. (D-13)
- **`tenant_id` 를 요청에서 받아 조용히 무시하지 마라.** 400 이다. (D-17)
- **토큰 원문을 `verify_token` 밖에서 파싱하지 마라.** (D-16)
- **`/v1/dev/token` 을 운영 빌드에 남기지 마라.** S1 이다. (D-17)
- **`/predictions/{run_id}/tiles/*.mvt` 를 되살리지 마라.** (D-06)
- **`/scores` 에 페이지네이션·금액을 넣지 마라. `/regions` 를 없애지 마라.** (D-07)
- **표준 행정경계를 GeoJSON 으로 내보내지 마라.** (D-09)
- **경계 타일을 직접 생성·프록시하지 마라.** URL 전달만. (D-05)
- **`shared/contracts/` 를 수정하지 마라.** CCR 을 쓰되 **병합 전까지 그 CCR 을 근거로 구현하지
  마라** — A 가 네 CCR 을 계약으로 오인한 사고의 원인이다. (D-10)
- **`/data-platform`, `/intelligence`, `/console`, `/verification` 을 수정하지 마라.**
