# BRIEF-D — console (에이전트 D)

생성: 총괄자 · 근거: `orchestrator/STATUS.md` (스윕 08-15 19:1x, HEAD `849354d`)
읽는 순서: 이 파일 → `orchestrator/DECISIONS.md` → 네 `RECONCILIATION.md` §7

---

## 지금 상태 (저장소 기준)

| 항목 | 사실 |
|---|---|
| 마지막 커밋 | `0d3c5d4` 08-15 17:50 — *rebuild map view against ADR-001 (basemap manifest + scores)* |
| 폴더 커밋 수 | 4 |
| 계약 반영 | 계약 최종 커밋 `af25b37`(17:01) 이후 — OK |
| CONTRACT_CHANGE_REQUEST | 없음 |
| **교차 신선도** | **플래그 2건 — 4개 에이전트 중 유일하게 낡은 상태다** |

구현된 것: `PredictionMap.tsx`, `RegionDetailPanel.tsx`, `lib/api/client.ts`, `lib/api/types.ts`,
`lib/color/scoreScale.ts`, `lib/map/hatchPattern.ts`. 호출 경로는 계약과 일치한다
(`/basemap/regions/manifest`, `/predictions/{run_id}/scores`).

---

## 해소된 것 — 더 신경 쓰지 마라

### 1. 네 `RECONCILIATION.md` §7 의 "계약과 backend 실제 구현이 다르다" — **이미 해소됐다.**

이게 이번 사이클의 핵심이다. 시간선을 그대로 보여준다.

| 시각 | 커밋 | 무슨 일 |
|---|---|---|
| 17:50 | `0d3c5d4` (**너**) | 지도 뷰 재구축 + §7 에 "backend 가 ADR-001 과 다르게 구현했다" 기록 |
| **18:01** | `849354d` (**C**) | C 가 자기 구현을 계약대로 고침. `/scores` 신설, manifest 를 PMTiles 형식으로 교체, 오해를 낳은 CCR 삭제, **`backend/samples/{manifest,scores}.json` 커밋** |

**너는 C 의 수정보다 11분 이른 커밋에 머물러 있다.** 그래서 네가 §7 에 적은 내용은 작성 시점엔
사실이었지만 지금은 사실이 아니다. 구체적으로:

- ~~"backend 의 manifest 는 쿼리 파라미터 없이 레벨별 GeoJSON URL 목록을 반환한다"~~
  → 지금은 `?level=&vintage=` 를 받고 **단일 `.pmtiles` 매니페스트**를 반환한다.
- ~~"`GET /predictions/{run_id}/scores` 엔드포인트 자체가 없다"~~
  → 지금은 **존재한다.** 튜플배열 + `schema` + `score_range`, 페이지네이션 없음, 금액 미포함.
- ~~"`/regions` 에 `boundary_vintage` 를 얹어 재사용"~~
  → C 가 `/regions` 를 원래 v0.2.0 모양으로 되돌렸다. `boundary_vintage` 는 `/scores` 에만 있다.

**너와 C 중 누구도 틀리지 않았다. 정보가 전달되지 않았을 뿐이다.**
"둘 중 하나로 수렴시켜 달라"고 jin 에게 요청한 건 이미 수렴됐다 — 계약(PMTiles) 쪽으로,
네 구현이 맞은 방향으로. **네 지도 코드를 되돌리지 마라.**

### 2. 벡터타일 소스 문제 — 해결됨 (ADR-001). 네 §6 기록이 맞다. 재확인 불필요.

### 3. `/frontend` 폐기 — 완료. 재논의 대상 아님.

---

## 다음 작업 (우선순위 순)

1. **C 의 샘플로 통합 테스트를 진행해라. 이제 파일이 저장소에 있다.**
   ```
   backend/samples/manifest.json   ← GET /v1/basemap/regions/manifest 응답 모양
   backend/samples/scores.json     ← GET /v1/predictions/{run_id}/scores 응답 모양
   ```
   총괄자가 두 파일을 계약 검증기에 통과시켜 확인했다. 네가 계약 example 로 만든 타입과
   대조해라 — 특히 `scores` 가 **객체 배열이 아니라 튜플배열 + `schema`** 라는 점,
   `score_range` 로 색상 도메인을 고정한다는 점.

2. **다만 `scores.json` 의 `region_id` 는 아직 신뢰하지 마라 — C 에게 수정 요청이 나갔다.**
   `region_level: "adm_dong"` 인데 `region_id` 가 `"41135"`, `"11650"` … 전부 **5자리**다.
   `03_region_features.json` 기준 5자리는 sigungu 다 (adm_dong 은 8~10자리).
   → **응답 모양(shape) 검증에는 그대로 써도 된다. 지역 코드 자체를 전제로 한 로직은 미루자.**
   C 가 고치면 값만 바뀌고 구조는 그대로다.

3. **실제 경계 타일과의 조인은 아직 못 한다 — 사실을 알고 있어라.**
   A 는 `.pmtiles` 를 만들었지만 **`sido` 레벨 하나뿐**이고(빈티지 2026-01-01 / 2026-07-01),
   그마저 `data-platform/.gitignore` 의 `output/` 때문에 **저장소에 없다.**
   C 의 샘플은 `adm_dong` 을 가리킨다 — 그 레벨 타일은 아직 존재하지 않는다.
   → `setFeatureState` 조인은 지금은 **합성 픽스처로만** 검증할 수 있다. 4번 참고.
   아티팩트 발행 경로는 jin 결정 대기 항목으로 올라가 있다. 네가 해결할 사항이 아니다.

4. **조인 테스트용 지역 픽스처는 B 것을 써라.**
   `intelligence/synthetic/sample/regions.json` — 저장소에서 계약의 코드 자릿수 규칙을 지키는
   유일한 지역 픽스처다 (sido `91` / sigungu `91001` / adm_dong `91001001`, 실제 코드와 충돌 없음).
   `region_features.json`, `demand_signal.json` 도 같은 폴더에 있다.

5. **네가 미룬 UI 를 진행해라 — 의존이 이미 충족돼 있다.**
   - 상단 제품(SKU)·채널·objective 선택 컨트롤 (네 §5-2 에서 "다음 착수 항목"으로 남긴 것)
   - **Tier 별 정직성 규칙 공통 컴포넌트** (§5-4). `expected_revenue_krw === null`(T0) 처리는
     여러 화면에 퍼지기 전에 공통 로직으로 빼는 게 맞다. `DECISIONS.md` D-03,
     `05_scoring_spec.md` §2. C 의 샘플/계약 example 만으로 충분히 만들 수 있다.
   - 지역 상세 패널의 요인 분해 waterfall + evidence 문장 그대로 노출 (§5-3).

6. **`custom_catchment` 분기는 테스트되지 않은 채로 남아 있다 (네 §7 기록).**
   계약상 이 경우에만 `custom_geometries` GeoJSON 을 직접 쓴다 (`DECISIONS.md` D-09).
   C 의 샘플은 `custom_geometries: null` 이라 이 경로를 타지 않는다.
   직접 픽스처를 만들어 분기만이라도 검증해 둬라.

---

## 확인 방법 — 명령어와 통과 기준

```bash
# C 의 샘플이 계약을 지키는지 직접 확인 (네가 믿고 붙여도 되는지 스스로 검증)
python tools/validate_contracts.py --check-scores   backend/samples/scores.json
python tools/validate_contracts.py --check-manifest backend/samples/manifest.json

# 폴더 경계 위반 검사 (통과 = exit 0)
python tools/validate_contracts.py --base origin/master --agent D

# 빌드 (네가 기준선으로 삼은 것)
cd console && npm run build
```

통과 기준: `--check-manifest` 는 오류 0. `--check-scores` 는 현재 **오류 0 / 경고 5** 이며,
그 경고 5건이 위 2번의 `region_id` 자릿수 문제다. C 가 고치면 경고 0 이 된다.
**경고가 0 이 되기 전까지 지역 코드에 의존하는 로직을 확정하지 마라.**

---

## 하지 말 것

- **§7 의 backend 불일치 이슈를 다시 제기하지 마라. 해소됐다.**
  다음에 같은 상황이 의심되면, 상대 폴더의 **최신 커밋**을 먼저 확인해라
  (`git log --oneline -5 -- backend`). 네가 본 코드가 이미 낡았을 수 있다.
- **다른 에이전트의 코드나 CCR 을 계약으로 삼지 마라.** 계약은 `shared/contracts/` 뿐이다.
  (`DECISIONS.md` D-10)
- **네 ADR-001 기반 지도 구현을 되돌리지 마라.** 방향이 맞다.
- **`.mvt` 타일 엔드포인트로 돌아가지 마라.** 폐기됐다. (D-06)
- **`/scores` 응답에서 금액을 기대하지 마라.** 금액은 상세 조회 전용이다. (D-07)
- **T0 에서 금액 자리를 비우고 넘어가지 마라.** 안내 문구 + 상대 랭킹을 반드시 표시한다. (D-03)
- **`/backend`, `/data-platform`, `/intelligence`, `shared/contracts/` 를 수정하지 마라.**
  C 의 샘플이 잘못돼 보여도 직접 고치지 말고 보고해라.

---

## 아직 열려 있는 것 (네 책임 아님, jin 대기)

- **인증/토큰 발급 방식** — 네 §6 질문. C 도 같은 질문을 jin 에게 올렸다
  (`06_governance.md` §6 은 방향만 있고 실제 IdP 미정). 지금은 C 의 `get_tenant_id` 가
  "Bearer 토큰 값 = tenant_id" 인 임시 구현이다. 로컬 개발은 이걸로 붙이면 된다.
