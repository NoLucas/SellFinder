# BRIEF-A — data-platform (에이전트 A)

생성: 총괄자 · 근거: `orchestrator/STATUS.md` (스윕 08-15 19:1x, HEAD `849354d`)
읽는 순서: 이 파일 → `orchestrator/DECISIONS.md` → 네 `RECONCILIATION.md`

---

## 지금 상태 (저장소 기준)

| 항목 | 사실 |
|---|---|
| 마지막 커밋 | `4a7833c` 08-15 17:58 — *align boundary tile manifest with ADR-001 contract* |
| 폴더 커밋 수 | 4 |
| 테스트 | `data-platform/tests` **6 passed** |
| 계약 반영 | 계약 최종 커밋 `af25b37`(17:01) **이후**에 커밋함 — OK |
| CONTRACT_CHANGE_REQUEST | 없음 |

**네 보고서와 저장소가 다르다 (불일치 그대로 보고한다).**
`data-platform/RECONCILIATION.md`(16:27 작성)는 *"STEP 2 는 아직 착수하지 않았다"* 라고 적혀 있다.
그러나 저장소에는 그 뒤로 커밋 2건(`f284573` 17:22, `4a7833c` 17:58)이 있고 경계 타일 파이프라인이
실제로 동작한다. **보고서 쪽이 낡았다.** 어느 쪽이 맞는지는 네가 판단해 보고서를 갱신해라 —
총괄자가 대신 고치지 않는다.

실제로 만들어진 산출물 (디스크 기준):
- `data-platform/output/tiles/regions-sido-2026-01-01.pmtiles`
- `data-platform/output/tiles/regions-sido-2026-07-01.pmtiles`
- `data-platform/output/tiles/manifest.json` (level `sido` 만, 빈티지 2종)

---

## 해소된 것 — 더 신경 쓰지 마라

1. **`.pmtiles` 파이프라인은 되돌리지 마라. 계약에 맞다.**
   ADR-001 이 확정한 소유권 분리(경계=A 정적 아티팩트 / 점수=C JSON / 조인=D 클라이언트)를
   네 구현이 이미 따르고 있다. `orchestrator/DECISIONS.md` D-05 ~ D-09.

2. **"backend 가 계약을 GeoJSON 방식으로 바꿨다"는 인식은 사실이 아니었다.**
   너는 `backend/CONTRACT_CHANGE_REQUEST.md` 를 읽고 그렇게 판단했지만, 그 문서는 **병합되지 않은
   제안**이었고 jin 이 실제로 확정한 것은 ADR-001(PMTiles)이다. C 가 커밋 `849354d` 에서
   자기 구현을 계약에 맞게 고치고 그 CCR 파일을 삭제했다. 지금 저장소에 그 파일은 없다.
   → **다른 에이전트의 코드·문서는 계약이 아니다** (`DECISIONS.md` D-10). 계약은 `shared/contracts/` 뿐이다.

3. **타일 서빙 API 는 네 일이 아니다.** ADR-001 대로 C 소유다. 네 산출물은 정적 아티팩트까지다.

---

## 다음 작업 (우선순위 순)

1. **[jin 결정 대기] 아티팩트 발행 경로를 확정받아라 — 지금 최대 차단 요인이다.**
   `data-platform/.gitignore:5` 의 `output/` 때문에 네 `.pmtiles` 와 `manifest.json` 은
   **저장소에 없다. 네 로컬 디스크에만 있다.** C 와 D 는 이 산출물을 가져갈 방법이 없다.
   ADR-001 은 "아티팩트 저장소에 업로드"라고만 하고 그 저장소가 무엇인지 정하지 않았다.
   → 네가 결정할 사항이 아니다. 이 브리프로 jin 에게 올라가 있다. **그 사이에 2번부터 진행해라.**
   (gitignore 를 풀어 바이너리를 커밋하는 쪽으로 임의 결정하지 마라.)

2. **C 와 매니페스트 값이 어긋난다. 확인하고 네 쪽 근거를 밝혀라.**
   C 의 `backend/app/services/basemap_registry.py` 는 A 의 산출물을 읽지 않고 **하드코딩**되어 있다
   (C 도 코드 주석에 "A 가 아직 안 냈으므로 임시"라고 적어놨다 — 그 주석이 지금은 낡았다). 대조:

   | | A 실제 산출물 | C 하드코딩 |
   |---|---|---|
   | level | `sido` 만 | `sido`, `sigungu`, `adm_dong` |
   | 빈티지 | 2026-01-01, **2026-07-01** | 2026-01-01, **2025-01-01**, 2024-01-01 |
   | sido zoom | minzoom **0** / maxzoom 8 | minzoom **5** / maxzoom 8 |

   겹치는 것은 `sido` + `2026-01-01` 하나뿐이다. ADR-001 의 예시는 `adm_dong`(5–12)만 정하고
   sido zoom 은 정하지 않았다 — 그래서 이건 계약 위반이 아니라 **미정 영역의 충돌**이다.
   sido minzoom 을 0 으로 둔 근거(전국 뷰에서 시도 경계가 보여야 함 등)를 네 README 나 보고서에 적어라.
   최종 조정은 1번이 풀린 뒤 C 와 맞춘다.

3. **`sigungu` / `adm_dong` 레벨 타일을 생산해라.**
   C 의 점수 응답 샘플과 D 의 지도는 `adm_dong` 을 전제로 움직인다. 지금 그 레벨 타일이 없어서
   D 는 실제 경계 위에서 통합 테스트를 할 수 없다. 레벨별 zoom 범위는 `ADR-001-map-tiles.md` 참조.

4. **네 `RECONCILIATION.md` §5 의 본래 작업 순서를 재개해라.**
   region 모델(행정표준코드 + `region_code_mapping`) → `region_feature` 스토어.
   피처 스토어 인터페이스는 `03_region_features.json` 의 `point_in_time_rule` 을 따른다
   ("최신값" 헬퍼 금지). B 가 이미 같은 시그니처의 스텁을 만들어 뒀다 — 아래 5번.

5. **B 의 질문에 답해라 (B 는 네 답을 기다리며 스텁으로 진행 중).**
   - `get_features(region_ids, feature_keys, as_of)` 의 실제 호출 방식(함수/내부 API/DB).
     B 는 이 시그니처로 스텁을 만들어 뒀으니, 네가 같은 모양으로 내면 B 쪽 코드 변경이 없다.
   - `demand_signal.coverage_flag='suppressed'` 셀의 상위 지역 대체를 **A 가 하는가 B 가 하는가.**
     B 는 "B 가 모델 입력 단계에서 처리"로 가정하고 진행 중이다. 네가 이미 대체해서 주면 이중 처리된다.
   답은 네 보고서에 적어라. 총괄자가 다음 사이클에 B 에게 전달한다.

6. **B 의 합성 픽스처를 시드로 쓸 수 있는지 검토해라.**
   `intelligence/synthetic/sample/regions.json` 은 계약의 코드 자릿수 규칙
   (`03_region_features.json` `region_hierarchy.rules`)을 지키는 유일한 픽스처다
   (sido 2자리 `91`, sigungu 5자리 `91001`, adm_dong 8자리 `91001001`, 실제 코드와 충돌 없는 가상 접두사).
   네 타일의 `region_id` 와 정합되면 A/B/D 가 같은 지역 세계를 공유하게 된다.

---

## 확인 방법 — 명령어와 통과 기준

```bash
# 폴더 경계 위반 검사 (통과 = 오류 0건, exit 0)
python tools/validate_contracts.py --base origin/master --agent A

# 네 매니페스트가 계약 형식인지 (엔트리 1개를 파일로 떼서 검사)
python tools/validate_contracts.py --check-manifest <매니페스트-엔트리.json>

# 테스트 (현재 기준선: 6 passed)
data-platform/.venv/Scripts/python.exe -m pytest data-platform/tests -q
```

`--check-manifest` 통과 기준: `feature_id_property` 가 `"region_id"`,
`available_vintages` 가 비어있지 않고 `boundary_vintage` 를 포함, `tile_url` 이 절대 URL 이며
`.mvt` / `/predictions/` 를 가리키지 않을 것.

> 주의: 네 `output/tiles/manifest.json` 은 `{levels:{...}}` 중첩 **색인** 구조라 그대로는 이 검사에
> 걸리지 않는다. 검사 대상은 C 가 API 로 내보내는 **엔트리 1개** 모양이다. 색인 구조 자체는
> 네 내부 산출물이므로 유지해도 된다 — 다만 엔트리 하나를 떼면 계약 모양이어야 한다.

---

## 하지 말 것

- **`.pmtiles` 파이프라인을 되돌리지 마라.** 계약에 맞다. (`DECISIONS.md` D-05)
- **다른 에이전트의 코드나 CCR 을 계약으로 삼지 마라.** 계약은 `shared/contracts/` 파일뿐이다. (D-10)
- **`shared/contracts/` 를 수정하지 마라.** 변경이 필요하면 `data-platform/CONTRACT_CHANGE_REQUEST.md` 를 쓴다.
- **`.gitignore` 의 `output/` 를 임의로 풀어 타일 바이너리를 커밋하지 마라.** 1번 결정 대기 중이다.
- **타일 서빙 API 를 만들지 마라.** C 소유다. (D-05)
- **`/backend`, `/intelligence`, `/console` 을 수정하지 마라.**
