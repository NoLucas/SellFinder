# SellFinder — 상태 스윕 (STATUS)

생성: `tools/status_sweep.py` · 2026-08-15 19:25 +0900 · 브랜치 `master` · HEAD `d17d7cf` · **워킹트리 변경 있음**

> 이 문서는 저장소에서 기계적으로 읽은 **사실**만 담는다. 에이전트의 자기 보고는 포함하지 않는다. 둘이 다르면 불일치 자체가 보고 대상이다.

---

## 1. 계약 상태

- **API 계약 버전**: `0.2.1` (`shared/contracts/04_api_contract.yaml`)
- **계약 최종 변경**: `af25b37` 08-15 17:01 — contracts: v0.2.1 - split map tile ownership (ADR-001)
- **`validate_contracts.py`**: 통과
- **검증기 플래그**: `--check-response`, `--check-scores`, `--check-manifest` 모두 지원

### 계약 변경 이력 (경계 위반 감시)

| 커밋 | 시각 | 작성자 | 메시지 |
|---|---|---|---|
| `af25b37` | 08-15 17:01 | NoLucas | contracts: v0.2.1 - split map tile ownership (ADR-001) |
| `0c3ed57` | 08-15 03:04 | NoLucas | Implement SellFinder prediction backend per shared contract |

> `shared/contracts/` 는 jin 전용이다. 위 목록에 에이전트 커밋이 있으면 경계 위반이다.

---

## 2. 에이전트 진행

| 에이전트 | 폴더 | 커밋수 | 마지막 커밋 | 시각 | 메시지 | RECONCILIATION | CCR |
|---|---|---|---|---|---|---|---|
| **A** | `data-platform` | 4 | `4a7833c` | 08-15 17:58 | data-platform: align boundary tile manifest with ADR-001 contract | 있음 | 없음 |
| **B** | `intelligence` | 3 | `ab92558` | 08-15 18:00 | intelligence: Step 2 invariant tests + 8-factor model skeleton | 있음 | 없음 |
| **C** | `backend` | 5 | `849354d` | 08-15 18:01 | backend: align basemap/scores endpoints to contract v0.2.1 (ADR-001) | 있음 | 없음 |
| **D** | `console` | 4 | `0d3c5d4` | 08-15 17:50 | console: rebuild map view against ADR-001 (basemap manifest + scores) | 있음 | 없음 |

---

## 3. 계약 반영 여부

기준: 계약 최종 커밋 `af25b37` (08-15 17:01).

| 에이전트 | 마지막 커밋 | 계약 이후? | 판정 |
|---|---|---|---|
| **A** | `4a7833c` 08-15 17:58 | 예 | OK (계약보다 0.9h 뒤) |
| **B** | `ab92558` 08-15 18:00 | 예 | OK (계약보다 1.0h 뒤) |
| **C** | `849354d` 08-15 18:01 | 예 | OK (계약보다 1.0h 뒤) |
| **D** | `0d3c5d4` 08-15 17:50 | 예 | OK (계약보다 0.8h 뒤) |

---

## 4. 에이전트 간 인수인계 산출물

**디스크에 있는 것과 소비자가 가져갈 수 있는 것은 다르다.** gitignore 된 산출물은 생산자 로컬에만 존재하므로 다른 에이전트에게 도달하지 않는다.

| 산출물 | 생산자 | 소비자 | 디스크 | git 추적 | 마지막 갱신 커밋 |
|---|---|---|---|---|---|
| `intelligence/synthetic/*`<br/><sub>공용 합성 픽스처</sub> | B | A, C, D | 8개 | 8 / 8 | `8f00729` 08-15 17:30 |
| `backend/samples/manifest.json`<br/><sub>지도 매니페스트 mock</sub> | C | D | 1개 | 1 / 1 | `849354d` 08-15 18:01 |
| `backend/samples/scores.json`<br/><sub>점수 응답 mock</sub> | C | D | 1개 | 1 / 1 | `849354d` 08-15 18:01 |
| `data-platform/**/manifest.json`<br/><sub>타일 매니페스트</sub> | A | C, D | 1개 | **0 / 1 — 전부 미추적** | **—** |
| `data-platform/**/*.pmtiles`<br/><sub>경계 타일 아티팩트</sub> | A | D | 2개 | **0 / 2 — 전부 미추적** | **—** |

> **`data-platform/**/manifest.json` 은 생산자(A) 디스크에만 있고 저장소에 없다.** 소비자(C, D)는 이 산출물을 가져갈 수 없다.  
>   무시 규칙: `data-platform/.gitignore:5:output/	data-platform/output/tiles/manifest.json`
> **`data-platform/**/*.pmtiles` 은 생산자(A) 디스크에만 있고 저장소에 없다.** 소비자(D)는 이 산출물을 가져갈 수 없다.  
>   무시 규칙: `data-platform/.gitignore:5:output/	data-platform/output/tiles/regions-sido-2026-01-01.pmtiles`

---

## 5. 교차 신선도 (가장 중요)

소비자의 마지막 커밋이 생산자의 산출물보다 이르면, 그 소비자는 최신 산출물을 보지 못한 상태에서 판단했을 수 있다. 소비자가 제기한 이슈가 이미 해소됐을 가능성이 여기서 나온다.

- **D 는 `backend/samples/manifest.json` 보다 0.2시간 이르다.** (생산자 C: `849354d` 08-15 18:01 / 소비자 D: `0d3c5d4` 08-15 17:50)  
  → D 가 C 의 최신 산출물을 못 봤을 수 있다. D 가 제기한 C 관련 이슈는 이미 해소됐을 가능성이 있다.
- **D 는 `backend/samples/scores.json` 보다 0.2시간 이르다.** (생산자 C: `849354d` 08-15 18:01 / 소비자 D: `0d3c5d4` 08-15 17:50)  
  → D 가 C 의 최신 산출물을 못 봤을 수 있다. D 가 제기한 C 관련 이슈는 이미 해소됐을 가능성이 있다.

---

## 6. jin 결정이 필요한 항목

- **교차 신선도 플래그 2건** — §5 참조. 낡은 정보에 근거한 이슈 제기 가능성.
- **`data-platform/**/manifest.json` 인수인계 경로 미정** — 생산자 A 가 만들었으나 gitignore 되어 저장소에 없다. 소비자(C, D)가 가져갈 방법이 정해져 있지 않다. 아티팩트 저장소/CDN 업로드 경로를 확정해야 한다.
- **`data-platform/**/*.pmtiles` 인수인계 경로 미정** — 생산자 A 가 만들었으나 gitignore 되어 저장소에 없다. 소비자(D)가 가져갈 방법이 정해져 있지 않다. 아티팩트 저장소/CDN 업로드 경로를 확정해야 한다.
