# BRIEF-D — console (에이전트 D)

**개정 3** · 근거: `orchestrator/STATUS.md` (스윕 08-15 23:4x, HEAD `02661ca`) ·
`verification/FINDINGS.md` **1회차**
읽는 순서: 이 파일 → **`verification/FINDINGS.md` VF-003·VF-009** →
**`shared/contracts/ADR-002-artifact-publishing.md`**, **`ADR-003-auth.md`**,
`ADR-005-tile-join-key.md`(네 코드는 안 바뀐다) → `orchestrator/DECISIONS.md` → 네 `RECONCILIATION.md` §7

> **ADR-002 와 ADR-003 은 반드시 직접 읽어라.** `shared/contracts/README.md` 의 읽기 순서 표는
> `00`~`06` 만 나열하고 ADR 을 포함하지 않는다. 표만 보고 넘어가면 로그인 방식과 픽스처 경로를 놓친다.

---

## 지금 상태 (저장소 기준)

| 항목 | 사실 |
|---|---|
| 마지막 커밋 | `0d3c5d4` 08-15 17:50 — *rebuild map view against ADR-001* |
| 폴더 커밋 수 | 4 |
| 계약 반영 | **경고 — 계약 최종 커밋 `33fe4ac`(19:37)보다 1.8h 이르다.** ADR-002/003 미반영 |
| CONTRACT_CHANGE_REQUEST | 없음 |

호출 경로는 계약과 일치한다 (`/basemap/regions/manifest`, `/predictions/{run_id}/scores`).

---

## 해소된 것 — 더 신경 쓰지 마라

### 1. `RECONCILIATION.md` §7 의 "계약과 backend 실제 구현이 다르다" — **이미 해소됐다**

| 시각 | 커밋 | 무슨 일 |
|---|---|---|
| 17:50 | `0d3c5d4` (**너**) | 지도 뷰 재구축 + §7 에 "backend 가 ADR-001 과 다르다" 기록 |
| **18:01** | `849354d` (**C**) | C 가 계약대로 수정. `/scores` 신설, manifest 를 PMTiles 형식으로 교체, 오해를 낳은 CCR 삭제, `backend/samples/{manifest,scores}.json` 커밋 |

**너는 C 의 수정보다 11분 이른 커밋에 머물러 있다.** §7 은 작성 시점엔 사실이었고 지금은 아니다.
"둘 중 하나로 수렴시켜 달라"는 요청은 이미 수렴됐다 — 계약(PMTiles), 즉 **네 구현이 맞은 방향으로**.
**네 지도 코드를 되돌리지 마라.** 너와 C 중 누구도 틀리지 않았다. 정보가 전달되지 않았을 뿐이다.

### 2. 통합 테스트를 막던 타일 부재 — 뚫렸다 (ADR-002 결정 2)

A 가 **`sigungu` 픽스처 타일**을 만들어 커밋한다:
`data-platform/fixtures/regions-sigungu-fixture.pmtiles` + `manifest-fixture.json`
(`boundary_vintage: "fixture"`). C 의 개발 서버가 이걸 `/artifacts/` 로 정적 서빙한다.
실 아티팩트가 발행되면 **`tile_url` 만 바뀐다.**

### 3. 지난 브리프에서 "믿지 마라"고 한 `scores.json` 의 region_id — 정정 방향이 정해졌다

`region_level` 을 `"sigungu"` 로 (region_id 는 그대로), `boundary_vintage` 를 `"fixture"` 로.
C 가 고친다. 픽스처 타일도 `sigungu` 라 **샘플과 타일 레벨이 맞는다** — 실제 렌더까지 간다.

### 4. 인증 방식이 확정됐다 (ADR-003) — 네 §6 질문의 답

- 콘솔 v1 로그인은 **이메일 + 매직링크**. 비밀번호 저장 없음.
- 개발 중에는 C 가 `POST /v1/dev/token { tenant_id, role, region_scope }` 를 제공한다.
  **이걸로 테넌트 전환과 권한별 UI 를 지금 테스트할 수 있다.**
- IdP 벤더는 안 고른다. `verify_token` 뒤에 숨겨서 나중에 바꾼다.

### 5. 벡터타일 소스(ADR-001), `/frontend` 폐기 — 이전에 이미 종료. 재논의 대상 아님.

---

## 검증 1회차 findings — 네 담당

### VF-009 (S3) — console 에 실행 가능한 테스트가 0개다

`tsc --noEmit` 은 통과한다(exit 0). 하지만 테스트 러너도 테스트 파일도 없다.
그래서 추적 매트릭스에서 **네 관련 조항이 전부 구멍**이다 — 조인 키 일치, `score_range` 로
색상 스케일 고정, `confidence='low'` 패턴 구분, T0 금액 자리 표기, T0 UI 문구.

검증자가 코드를 읽어 확인한 바로는 **구현은 맞다** (`scoreScale.ts` 가 `score_range` 를 받고
`PredictionMap.tsx:118` 이 전달한다). 문제는 누가 되돌려도 아무도 모른다는 것이다.
그리고 실제로 그 구멍 안에서 VF-003 이 살아남았다 — 세 폴더 전부 초록불인데 지도는 비어 있었다.

최소 한 개: `backend/samples/*.json` 을 입력으로 **파서 → `setFeatureState` 키 생성 →
fill expression** 까지 가는 노드 테스트. `verification/fixtures/vf_56_join.mjs` 가 참고 구현이다
(MapLibre 의 `getId()` 와 `String(featureId)` 강제 변환까지 원본에서 옮겨 놨다). 아래 1번과 같이 해라.

### VF-003 (S2) — 조인이 실제로 0/5 다. **네 잘못이 아니고, 네 코드는 안 바뀐다.**

A 의 실제 `.pmtiles` + C 의 실제 매니페스트 + 네 조인 코드를 붙인 결과:

```
manifest.feature_id_property = "region_id"
tile feature ids (A, real)   = 11, 26, 28, 41, 50
tile feature properties keys = ["name","level","is_synthetic_placeholder"]   ← region_id 가 없다
features that received a score : 0/5
→ 전 지역이 NO_DATA 회색. 에러도 콘솔 경고도 없다.
```

**너는 계약대로 했다.** `promoteId` 에 `feature_id_property` 를 쓰는 것이 v0.2.1 규약이었고,
**v0.2.2 에서도 그대로다.** A 는 브리프 지시대로 `region_id` 를 속성이 아니라 숫자 feature id 로
실었는데, 그 지시문(ADR-001)이 같은 문서 안에서 네 규약과 정반대였던 것이 원인이다.

**결정: `region_id` 는 properties 에 문자열로 실린다** (`ADR-005-tile-join-key.md`, `DECISIONS.md` D-20).
**A 가 타일을 고치고, 너는 코드를 바꾸지 않는다.** `promoteId` 를 빼거나 조인 키를 손대지 마라.
A 의 수정된 타일이 들어오면 지금 코드 그대로 매칭된다 — 그것을 테스트로 고정하는 게 아래 1번이다.

> 참고: 지금은 레벨도 안 맞는다 (A=시도 2자리 / C 샘플=시군구 5자리). 그건 A 의 픽스처 타일(D-12)과
> C 의 샘플 정정(D-15)으로 닫힌다. 네가 할 일은 없다.

---

## 다음 작업 (우선순위 순)

1. **A 의 픽스처 타일 + C 의 정정된 샘플로 통합 테스트를 끝내라. 이번엔 테스트로 남겨라 (VF-009).**
   `setFeatureState` 조인이 실제 `.pmtiles` 위에서 도는 것까지 확인한다.
   **`tile_url` 을 하드코딩하지 마라.** 매니페스트 응답에서 받아 써라 — 개발/운영 URL 이 바뀌어도
   코드가 안 바뀌어야 한다. (ADR-002 "D 가 할 일" 2번)

2. **레벨 선택 UI 를 넣어라 (ADR-002 결정 4).**
   **레벨은 줌으로 자동 전환되지 않는다. 사용자가 시도/시군구/행정동을 고른다.**
   줌 범위는 겹쳐도 무방하다: `sido` 0–10 / `sigungu` 4–12 / `adm_dong` 5–14.
   maxzoom 초과는 오버줌으로 처리한다.

3. **토큰 취급 규칙을 지켜라 (ADR-003 §5).**
   - **토큰을 `localStorage` 에 넣지 마라.** XSS 한 번이면 전부 털린다.
     httpOnly 쿠키 또는 메모리 보관 + 리프레시.
   - `role` 로 UI 를 가리는 건 **편의일 뿐 보안이 아니다.** `viewer` 에게 버튼을 숨기되,
     실제 차단은 서버가 한다고 전제해라.
   - `region_scope` 가 걸린 사용자에게는 보이지 않는 지역이 생긴다 — 빈 지도를
     "데이터 없음"과 구분해 표시해라.

4. **상단 제품(SKU)·채널·objective 선택 컨트롤** (네 §5-2 의 "다음 착수 항목").

5. **Tier 별 정직성 규칙 공통 컴포넌트** (§5-4). 여러 화면에 퍼지기 전에 공통 로직으로 빼라.
   `expected_revenue_krw === null`(T0)이면 금액 자리에 업로드 안내 + 상대 랭킹만.
   `DECISIONS.md` D-03, `05_scoring_spec.md` §2.
   > 참고: ADR-004 로 `card_mcc` 가 빠지면서 **당분간 금액이 비는 경우가 기본값에 가까워진다.**
   > 이 컴포넌트가 예외 처리가 아니라 주 경로다.

6. **지역 상세 패널** — 요인 분해 waterfall, evidence 문장 그대로 노출, p10/p50/p90 (§5-3).

7. **`custom_catchment` 분기 검증** (네 §7 기록). 이 경우에만 `custom_geometries` GeoJSON 을
   직접 쓴다 (D-09). C 샘플은 `null` 이라 이 경로를 타지 않는다 — 픽스처를 직접 만들어 확인해라.

---

## 확인 방법 — 명령어와 통과 기준

```bash
# C 의 샘플이 계약을 지키는지 직접 확인 (믿고 붙여도 되는지 스스로 검증)
python tools/validate_contracts.py --check-scores   backend/samples/scores.json
python tools/validate_contracts.py --check-manifest backend/samples/manifest.json

python tools/validate_contracts.py --base origin/master --agent D
cd console && npm run build
```

통과 기준: 두 검사 모두 **오류 0 + 경고 0**.
현재 `--check-scores` 는 경고 5건이며, C 가 위 "해소된 것" 3번을 반영하면 0 이 된다.
**경고가 0 이 되기 전까지 지역 코드에 의존하는 로직을 확정하지 마라.**

---

## 하지 말 것

- **§7 의 backend 불일치 이슈를 다시 제기하지 마라. 해소됐다.**
  다음에 의심되면 상대 폴더의 **최신 커밋**을 먼저 봐라 (`git log --oneline -5 -- backend`).
- **`tile_url` 을 하드코딩하지 마라.** 매니페스트에서 받아 쓴다. (D-12)
- **토큰을 `localStorage` 에 저장하지 마라.** (D-17)
- **`role` 기반 UI 숨김을 보안으로 취급하지 마라.**
- **줌으로 레벨을 자동 전환하지 마라.** 사용자가 고른다. (D-14)
- **네 ADR-001 기반 지도 구현을 되돌리지 마라.** 방향이 맞다.
- **`.mvt` 타일 엔드포인트로 돌아가지 마라.** (D-06)
- **`/scores` 에서 금액을 기대하지 마라.** 상세 조회 전용이다. (D-07)
- **T0 에서 금액 자리를 그냥 비우지 마라.** 안내 + 상대 랭킹을 표시한다. (D-03)
- **다른 에이전트의 코드·CCR 을 계약으로 삼지 마라.** (D-10)
- **`/backend`, `/data-platform`, `/intelligence`, `/verification`, `shared/contracts/` 를 수정하지 마라.**
  C 의 샘플이 잘못돼 보여도 직접 고치지 말고 보고해라.
