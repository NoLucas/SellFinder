# SellFinder — 상태 스윕 (STATUS)

생성: `tools/status_sweep.py` · 2026-08-16 18:25 +0900 · 브랜치 `master` · HEAD `3e7e6e3` · **워킹트리 변경 있음**

> 이 문서는 저장소에서 기계적으로 읽은 **사실**만 담는다. 에이전트의 자기 보고는 포함하지 않는다. 둘이 다르면 불일치 자체가 보고 대상이다.

---

## 1. 계약 상태

- **API 계약 버전**: `0.2.2` (`shared/contracts/04_api_contract.yaml`)
- **계약 최종 변경**: `91dc71d` 08-16 00:15 — contracts: ADR-005 - tile join key is the region_id property (v0.2.2)
- **`validate_contracts.py`**: 통과
- **검증기 플래그**: `--check-response`, `--check-scores`, `--check-manifest` 모두 지원

### 계약 변경 이력 (경계 위반 감시)

| 커밋 | 시각 | 작성자 | 메시지 |
|---|---|---|---|
| `91dc71d` | 08-16 00:15 | NoLucas | contracts: ADR-005 - tile join key is the region_id property (v0.2.2) |
| `33fe4ac` | 08-15 19:37 | NoLucas | contracts: ADR-002/003/004 - artifact publishing, auth, taxonomy mapping |
| `af25b37` | 08-15 17:01 | NoLucas | contracts: v0.2.1 - split map tile ownership (ADR-001) |
| `0c3ed57` | 08-15 03:04 | NoLucas | Implement SellFinder prediction backend per shared contract |

> `shared/contracts/` 는 jin 전용이다. 위 목록에 에이전트 커밋이 있으면 경계 위반이다.

---

## 2. 에이전트 진행

| 에이전트 | 폴더 | 커밋수 | 마지막 커밋 | 시각 | 메시지 | RECONCILIATION | CCR |
|---|---|---|---|---|---|---|---|
| **A** | `data-platform` | 7 | `3925555` | 08-16 16:21 | data-platform: sbiz taxonomy mapping + demand_signal + SGIS scaffolding (DISPATCH-2 A-1/A-2/A-3) | 있음 | 없음 |
| **B** | `intelligence` | 11 | `bb55f25` | 08-16 16:22 | intelligence: DISPATCH-2 B-3 - verify model card's backtest numbers survived the B-2 refactor | 있음 | 없음 |
| **C** | `backend` | 12 | `3e7e6e3` | 08-16 16:52 | backend: DISPATCH-2 C-1~C-5 - real predictions replace the demo hardcoding | 있음 | 없음 |
| **D** | `console` | 7 | `acc99ac` | 08-16 16:26 | console: DISPATCH-2 D-1~D-4 - region detail panel, T0/hatch/token tests | 있음 | 없음 |

---

## 3. 계약 반영 여부

기준: 계약 최종 커밋 `91dc71d` (08-16 00:15).

| 에이전트 | 마지막 커밋 | 계약 이후? | 판정 |
|---|---|---|---|
| **A** | `3925555` 08-16 16:21 | 예 | OK (계약보다 16.1h 뒤) |
| **B** | `bb55f25` 08-16 16:22 | 예 | OK (계약보다 16.1h 뒤) |
| **C** | `3e7e6e3` 08-16 16:52 | 예 | OK (계약보다 16.6h 뒤) |
| **D** | `acc99ac` 08-16 16:26 | 예 | OK (계약보다 16.2h 뒤) |

---

## 4. 에이전트 간 인수인계 산출물

**디스크에 있는 것과 소비자가 가져갈 수 있는 것은 다르다.** gitignore 된 산출물은 생산자 로컬에만 존재하므로 다른 에이전트에게 도달하지 않는다.

| 산출물 | 생산자 | 소비자 | 디스크 | git 추적 | 마지막 갱신 커밋 |
|---|---|---|---|---|---|
| `intelligence/synthetic/*`<br/><sub>공용 합성 픽스처</sub> | B | A, C, D | 8개 | 8 / 8 | `d7421f9` 08-16 10:38 |
| `backend/samples/manifest.json`<br/><sub>지도 매니페스트 mock</sub> | C | D | 1개 | 1 / 1 | `61c4eaf` 08-16 10:59 |
| `backend/samples/scores.json`<br/><sub>점수 응답 mock</sub> | C | D | 1개 | 1 / 1 | `a8f1e34` 08-16 10:19 |
| `data-platform/**/manifest.json`<br/><sub>타일 매니페스트</sub> | A | C, D | 1개 | **0 / 1 — 전부 미추적** | **—** |
| `data-platform/**/*.pmtiles`<br/><sub>경계 타일 아티팩트</sub> | A | D | 5개 | **1 / 5 — 일부 미추적** | `a0a5eb2` 08-16 10:40 |

> **`data-platform/**/manifest.json` 은 생산자(A) 디스크에만 있고 저장소에 없다.** 소비자(C, D)는 이 산출물을 가져갈 수 없다.  
>   무시 규칙: `data-platform/.gitignore:5:output/tiles/	data-platform/output/tiles/manifest.json`

---

## 5. 교차 신선도 (가장 중요)

소비자의 마지막 커밋이 생산자의 산출물보다 이르면, 그 소비자는 최신 산출물을 보지 못한 상태에서 판단했을 수 있다. 소비자가 제기한 이슈가 이미 해소됐을 가능성이 여기서 나온다.


### 검증 신선도

- **A 의 최신 변경은 아직 검증되지 않았다** (A: `3925555` 08-16 16:21 / 검증자: `d2ddbee` 08-16 15:21 — 1.0시간 뒤처짐)  
  → 검증 회차가 A 의 최신 커밋을 아직 보지 않았다. §7 참조.
- **B 의 최신 변경은 아직 검증되지 않았다** (B: `bb55f25` 08-16 16:22 / 검증자: `d2ddbee` 08-16 15:21 — 1.0시간 뒤처짐)  
  → 검증 회차가 B 의 최신 커밋을 아직 보지 않았다. §7 참조.
- **C 의 최신 변경은 아직 검증되지 않았다** (C: `3e7e6e3` 08-16 16:52 / 검증자: `d2ddbee` 08-16 15:21 — 1.5시간 뒤처짐)  
  → 검증 회차가 C 의 최신 커밋을 아직 보지 않았다. §7 참조.
- **D 의 최신 변경은 아직 검증되지 않았다** (D: `acc99ac` 08-16 16:26 / 검증자: `d2ddbee` 08-16 15:21 — 1.1시간 뒤처짐)  
  → 검증 회차가 D 의 최신 커밋을 아직 보지 않았다. §7 참조.

---

## 6. jin 결정이 필요한 항목

- **검증자 S2(심각) 미해결 1건** — `VF-013`. §7 참조. 계약 위반이거나 다른 에이전트를 깨뜨리는 건이다.
- **교차 신선도 플래그 4건** — §5 참조. 낡은 정보에 근거한 이슈 제기 가능성.
- **`data-platform/**/manifest.json` 인수인계 경로 미정** — 생산자 A 가 만들었으나 gitignore 되어 저장소에 없다. 소비자(C, D)가 가져갈 방법이 정해져 있지 않다. 아티팩트 저장소/CDN 업로드 경로를 확정해야 한다.

---

## 7. 검증 현황

검증 에이전트는 산출물이 코드가 아니라 findings 라서 §2 의 에이전트 표와 지표가 다르다. 여기서는 '무엇을 커밋했는가'가 아니라 '무엇이 아직 열려 있는가'를 본다.

- **마지막 `verification/` 커밋**: `d2ddbee` 08-16 15:21 — verification: round 4 - VF-010/VF-012 closed, VF-013 (S2) and VF-014 (S4) opened
- **FINDINGS.md 회차 표기**: 4회차 · 2026-08-16 · HEAD `822a259`

| S1 치명 | S2 심각 | S3 보통 | S4 낮음 | 미해결 합계 | 추정 | 해결됨 | 확인 불가 |
|---|---|---|---|---|---|---|---|
| 0 | 1 | 0 | 1 | **2** | 0 | 0 | 0 |

- **가장 오래된 미해결**: `VF-013` (S2 심각) — **0.1일**
- **마지막 검증 이후 A~D 변경 파일**: **44개** (backend 15개, console 12개, data-platform 11개, intelligence 6개)
  - → **다음 검증 회차가 필요하다.** 변경분이 쌓였다.
