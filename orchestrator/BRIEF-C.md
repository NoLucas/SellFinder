# BRIEF-C — backend (에이전트 C)

생성: 총괄자 · 근거: `orchestrator/STATUS.md` (스윕 08-15 19:1x, HEAD `849354d`)
읽는 순서: 이 파일 → `orchestrator/DECISIONS.md` → 네 `RECONCILIATION.md`

---

## 지금 상태 (저장소 기준)

| 항목 | 사실 |
|---|---|
| 마지막 커밋 | `849354d` 08-15 18:01 — *align basemap/scores endpoints to contract v0.2.1 (ADR-001)* |
| 폴더 커밋 수 | 5 (4개 에이전트 중 최다) |
| 테스트 | `backend/tests` **19 passed** |
| 계약 반영 | 계약 최종 커밋 `af25b37`(17:01) **이후**에 커밋함 — OK |
| CONTRACT_CHANGE_REQUEST | 없음 (`849354d` 에서 삭제됨) |

구현된 것: `GET /v1/basemap/regions/manifest`, `GET /v1/predictions/{run_id}/scores`,
`GET /v1/predictions/{run_id}/regions`, `GET /api/v1/health`,
`app/security.py` 의 `get_tenant_id` 의존성(토큰에서만 tenant 파생), `backend/samples/*.json` 2개.

---

## 해소된 것 — 더 신경 쓰지 마라

1. **네가 요청한 검증기 플래그 두 개가 추가되었다. 더 이상 막혀 있지 않다.**
   `tools/validate_contracts.py` 에 `--check-scores`, `--check-manifest` 가 들어갔다.
   지금 바로 돌릴 수 있다 (아래 "확인 방법"). 이건 도구 문제였지 계약 문제가 아니었다.

2. **ADR-001 정렬 작업은 끝났고, D 가 제기했던 "backend 가 계약과 다르다"는 이슈는 네 커밋으로 해소됐다.**
   D 는 17:50 에 커밋했고 너는 18:01 에 고쳤다 — **D 는 그 시점 이후로 아직 커밋이 없어서
   네 수정을 보지 못한 상태다.** D 에게는 "이미 해소됨"으로 전달된다. 네가 다시 설명할 필요 없다.

3. **네 CCR 을 삭제한 판단은 옳았다.** 병합되지 않은 제안이 저장소에 남아 A 가 그것을 계약으로
   오인했다. `DECISIONS.md` D-10 에 원칙으로 기록해 뒀다.

---

## 다음 작업 (우선순위 순)

1. **네 샘플 픽스처의 `region_id` 가 `region_level` 과 맞지 않는다. 먼저 고쳐라. (5분짜리)**
   ```bash
   python tools/validate_contracts.py --check-scores backend/samples/scores.json
   ```
   → exit 0 이지만 **경고 5건**이 뜬다. `backend/samples/scores.json` 은
   `region_level: "adm_dong"` 인데 `region_id` 가 `"41135"`, `"11650"` … 전부 **5자리**다.
   `03_region_features.json` 의 `region_hierarchy` 는 sido 2자리 / sigungu 5자리 /
   adm_dong 8~10자리로 정하고, "region_id 는 자기 레벨을 알 수 있어야 한다"를 규칙으로 둔다.
   지금 값은 sigungu 코드다.
   → `region_level` 을 `sigungu` 로 바꾸거나, `region_id` 를 8~10자리로 바꿔라.
   **D 가 이 파일로 통합 테스트를 시작한다.** 지금 고치면 D 가 잘못된 전제로 출발하지 않는다.
   (B 의 `intelligence/synthetic/sample/regions.json` 이 자릿수 규칙을 지키는 픽스처다. 참고해라.)

2. **`basemap_registry.py` 의 하드코딩을 A 의 실제 산출물과 대조해라 — 주석이 낡았다.**
   파일 상단 주석: *"A hasn't published real .pmtiles artifacts yet … Swap it for a real lookup
   once A ships"*. **A 는 이미 냈다** (`f284573` 17:22, `4a7833c` 17:58). 다만 대조하면 어긋난다:

   | | A 실제 산출물 | 네 `_VINTAGES` |
   |---|---|---|
   | level | `sido` 만 | `sido`, `sigungu`, `adm_dong` |
   | 빈티지 | 2026-01-01, **2026-07-01** | 2026-01-01, **2025-01-01**, 2024-01-01 |
   | sido zoom | minzoom **0** / maxzoom 8 | minzoom **5** / maxzoom 8 |

   겹치는 건 `sido` + `2026-01-01` 하나뿐이다.
   **단, 지금 실제 조회로 교체할 수는 없다.** A 의 `output/` 은 `data-platform/.gitignore:5` 로
   무시되어 저장소에 없다 — 네가 읽을 파일이 존재하지 않는다. 아티팩트 발행 경로는 jin 결정 대기다.
   → 지금 할 일은 **주석을 사실로 갱신**하는 것까지다("A 가 아티팩트를 냈으나 발행 경로 미정").
   하드코딩 값 자체는 그대로 둬도 된다.

3. **`POST /predictions` 비동기 골격 — 네 보고서 §5-4. 지금 가장 중요한 미구현이다.**
   현재 `predictions.py` 에는 GET 2개뿐이고 POST 가 없다.
   `00_product_spec.md` 의 Anti-goals 가 금지한 동기 예측 API 를 피하려면 이게 뼈대다.
   `202 {run_id, status, ...}` → 잡 워커 → `GET /predictions/{run_id}` 상태 조회.
   B 의 실제 모델은 `intelligence/scoring/model.py` 의 `predict_batch` 계열이 이미 동작한다
   (총괄자 확인: 28 tests passed). B 도 in-process 호출에 동의한다 — 아래 5번.

4. **`/api/v1/health` 의 프리픽스가 다른 라우트와 어긋난다.**
   `basemap.py` / `predictions.py` 는 `/v1/...`, `health.py` 만 `/api/v1/...` 다.
   네 보고서 §3-4 에서 스스로 지적한 그 문제의 잔여분이다. 계약(`04_api_contract.yaml` `servers.url`)
   기준으로 통일해라.

5. **B 와의 내부 호출 인터페이스를 확정해라 — B 가 동의했다.**
   너는 §6 에서 "잡 워커가 B 의 예측 함수를 in-process 로 호출, B 착수 시점에 확정"을 제안했고,
   B 도 §6-3 에서 같은 빈틈을 지적하며 네 제안과 같은 방향을 기다리고 있다.
   **양쪽 입장이 이미 일치한다.** B 에게 진입점 시그니처를 README 에 고정하라고 전달했다.
   그 시그니처가 나오면 그대로 호출해라. 새 계약 질문으로 올리지 마라.

6. **네 보고서 §5 의 나머지 순서를 재개해라.**
   공통 인프라(계약 형식 에러 봉투 + `request_id`, 커서 페이지네이션, `Idempotency-Key`, RBAC)
   → `/products`, `POST /products:classify`(B 전까지 mock) → 감사 로그 미들웨어.

---

## 확인 방법 — 명령어와 통과 기준

```bash
# 새로 추가된 두 플래그 — 지금 바로 쓸 수 있다
python tools/validate_contracts.py --check-scores   backend/samples/scores.json
python tools/validate_contracts.py --check-manifest backend/samples/manifest.json

# 폴더 경계 위반 검사 (통과 = exit 0)
python tools/validate_contracts.py --base origin/master --agent C

# 테스트 (현재 기준선: 19 passed)
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
```

통과 기준:
- `--check-scores`: **오류 0 + 경고 0** (지금은 경고 5건 — 위 1번). 튜플배열+schema,
  점수 0~100, confidence low|medium|high, `score_range.min/max` 존재,
  응답 어디에도 `expected_revenue_krw` 없음, `custom_geometries` 는 custom_catchment 일 때만.
- `--check-manifest`: 오류 0. `feature_id_property == "region_id"`, `available_vintages` 가
  `boundary_vintage` 포함, `tile_url` 이 절대 URL 이고 `.mvt` / `/predictions/` 를 가리키지 않음.
- 두 샘플 파일은 D 의 통합 테스트 입력이다. **커밋 전에 위 두 명령을 반드시 통과시켜라.**

---

## 하지 말 것

- **`/predictions/{run_id}/tiles/*.mvt` 를 되살리지 마라.** 폐기됐다. (`DECISIONS.md` D-06)
- **`/scores` 에 페이지네이션이나 금액을 넣지 마라.** (D-07)
- **`/predictions/{run_id}/regions` 를 없애지 마라.** `/scores` 가 대체하는 게 아니다. (D-07)
- **표준 행정경계를 GeoJSON 으로 내보내지 마라.** GeoJSON 은 `custom_catchment` 전용. (D-09)
- **경계 타일을 직접 생성하거나 프록시하지 마라.** A 의 아티팩트를 가리키는 URL 만 반환한다. (D-05)
- **`tenant_id` 를 요청 파라미터로 받지 마라.** 토큰에서만 파생. (`06_governance.md` §1)
- **`shared/contracts/` 를 수정하지 마라.** 필요하면 CCR 을 쓰되, **병합 전까지 그 CCR 을 근거로
  구현하지 마라** — 이번에 A 가 네 CCR 을 계약으로 오인한 사고의 원인이다. (D-10)
- **`/data-platform`, `/intelligence`, `/console` 을 수정하지 마라.**
