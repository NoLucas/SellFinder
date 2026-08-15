# BRIEF-A — data-platform (에이전트 A)

**개정 3** · 근거: `orchestrator/STATUS.md` (스윕 08-15 23:4x, HEAD `02661ca`) ·
`verification/FINDINGS.md` **1회차**
읽는 순서: 이 파일 → **`shared/contracts/ADR-005-tile-join-key.md`** → `verification/FINDINGS.md` VF-003 →
**`ADR-002-artifact-publishing.md`**, **`ADR-004-taxonomy-mapping.md`** → `orchestrator/DECISIONS.md`
→ 네 `RECONCILIATION.md`

> **ADR-002 와 ADR-004 는 반드시 직접 읽어라.** `shared/contracts/README.md` 의 읽기 순서 표는
> `00`~`06` 만 나열하고 ADR 을 포함하지 않는다. 표만 보고 넘어가면 네 작업 지시를 통째로 놓친다.

---

## 지금 상태 (저장소 기준)

| 항목 | 사실 |
|---|---|
| 마지막 커밋 | `4a7833c` 08-15 17:58 — *align boundary tile manifest with ADR-001 contract* |
| 폴더 커밋 수 | 4 · 테스트 **6 passed** |
| 계약 반영 | **경고 — 계약 최종 커밋 `33fe4ac`(19:37)보다 1.7h 이르다.** ADR-002/004 미반영 |
| CONTRACT_CHANGE_REQUEST | 없음 |

산출물 (디스크 기준, 저장소에는 없음): `regions-sido-2026-01-01.pmtiles`,
`regions-sido-2026-07-01.pmtiles`, `output/tiles/manifest.json` — `sido` 한 레벨.

**보고서 불일치 (지난 브리프에서 지적, 아직 미갱신):**
`data-platform/RECONCILIATION.md`(16:27)는 *"STEP 2 는 아직 착수하지 않았다"* 로 적혀 있으나
그 뒤 커밋 2건에서 파이프라인을 실제로 만들었다. **보고서 쪽이 낡았다.** 갱신은 네가 한다.

---

## 해소된 것 — 더 신경 쓰지 마라

1. **아티팩트 발행 경로가 확정됐다 (ADR-002 결정 1·2).** 지난 브리프의 최대 차단 요인이 풀렸다.
   `.gitignore` 교체안까지 jin 승인이 끝났다. 더 이상 대기하지 마라.

2. **A 와 C 의 매니페스트 충돌 — 네 잘못이 아니었다 (ADR-002 결정 3).**
   *"근본 원인은 C 가 값을 지어낸 것"* 으로 판정됐다. 빈티지 목록은 A 만 알 수 있으므로
   **C 가 하드코딩을 버리고 네 매니페스트를 읽는다.** 네가 C 에 맞출 일이 아니다.

3. **`sido` minzoom 논쟁 종료 (ADR-002 결정 4).** 네가 쓴 **0 이 채택됐다.**
   레벨은 줌으로 자동 전환하지 않고 사용자가 UI 에서 고른다. 줌 표는 `DECISIONS.md` D-14.

4. **택소노미 1차 매핑 기준이 정해졌다 (ADR-004).** `sbiz` 다. 네 §6 질문의 답이다.
   `ksic` 는 보조키, `card_mcc` 는 라이선스 확보 후.

5. **`.pmtiles` 파이프라인은 여전히 되돌릴 필요 없다.** ADR-001 대로다.
   다른 에이전트의 코드·CCR 을 계약으로 오인하지 마라 (`DECISIONS.md` D-10).

---

## 검증 1회차 findings — 네 담당

### VF-003 (S2) — 네 타일과 D 의 조인 키가 안 맞는다. **결정 났다 → ADR-005 / D-20**

검증자가 네 **실제** `.pmtiles` 를 디코드해 C 의 매니페스트·D 의 조인 코드에 붙였다:

```
manifest.feature_id_property = "region_id"
tile feature ids (A, real)   = 11, 26, 28, 41, 50
tile feature properties keys = ["name","level","is_synthetic_placeholder"]   ← region_id 가 없다
features that received a score : 0/5   → 전 지역 회색, 에러도 경고도 없음
```

원인: `src/boundary_tiles/tiler.py:56-63` 이 `region_id` 를 properties 에서 **제거**하고
숫자 feature id 로만 싣는다. 이건 네가 받은 브리프 지시("속성이 아니라 feature id 로 실어라",
`feature_id.py` 독스트링)를 정확히 따른 결과다. 그런데 계약과 D 는 `feature_id_property` 로
그 속성을 찾는다. **너도 D 도 각자 자기 문서를 지켰고, 계약이 두 방식을 동시에 말하고 있는 것이 원인이다.**

한 가지는 지금 확실하다: **네 매니페스트가 `feature_id_property: "region_id"` 라고 적는 것은
네 산출물과 모순이다.** 타일에 그 속성이 없다.

**결정: `region_id` 를 properties 에 문자열로 싣는다** (`ADR-005-tile-join-key.md`, `DECISIONS.md` D-20).
네이티브 id 방식은 기각됐다 — 선행 0·2⁵³ 초과·해시 충돌이 전부 "예외"가 아니라 "빈 지도"로 나타나고,
`region_id` 는 통계청이 소유한 외부 식별자라 "지금은 전부 숫자"라는 성질에 조인을 걸 수 없다.

네가 할 일은 셋이다. **아래 1번보다 먼저 해라 — 지금 나가는 모든 타일이 조인 불가 상태다.**

- `tiler.py:56-63` 에서 `region_id` 를 properties 에서 **제거하는 동작을 멈춘다.** 원문 문자열 유지.
  네이티브 숫자 id 는 계속 넣어도 된다 (툴 호환·디버깅에 유용). 다만 **조인 키가 아니다.**
- 매니페스트에서 **`id_map_path` 를 뺀다.** `id_map.json` 을 내부 빌드 산출물로 남기는 건 자유지만
  계약 산출물이 아니다 — 소비자가 의존하기 시작하면 조인 키가 다시 두 갈래가 된다.
- **빌드 자체 검증을 추가해라**: 매니페스트가 광고하는 `feature_id_property` 가 실제 산출 타일의
  피처 properties 에 있는지 확인하고, 없으면 빌드를 실패시킨다.
  **이 검사 하나가 VF-003 을 네 스위트 안에서 잡는다.** 지금은 6개 테스트 전부 통과하면서 깨져 있었다.

> 아래 2번(`sigungu` 픽스처 타일)도 그대로 해라. **D 를 막고 있는 건 여전히 그 파일이다.**
> 픽스처에도 같은 규칙이 적용된다 — 매니페스트가 광고하는 것과 타일 실물이 같아야 한다.

**VF-004 는 네 것이 아니다.** C 가 빈티지·줌을 지어낸 건이고 이미 D-13/D-14 로 정리됐다.
다만 검증에서 나온 사실 하나는 알아둬라: C 는 `sido/2026-07-01`(네가 실제로 만든 것)을 404 로 막고,
`sido/2025-01-01`(없는 것)을 목록에 넣고 있다. 네 매니페스트가 유일한 출처가 되면 둘 다 사라진다.

---

## 다음 작업 (우선순위 순)

1. **`.gitignore` 교체 + `output/` 분리 (ADR-002 결정 1).**
   ```gitignore
   data-platform/output/tiles/
   !data-platform/output/manifest/
   !data-platform/fixtures/
   ```
   `output/manifest/regions-{level}-{vintage}.json` 은 **커밋한다**(C 가 읽어야 한다).
   `output/tiles/*.pmtiles` 는 **커밋하지 않는다**. (`DECISIONS.md` D-11)

2. **`sigungu` 픽스처 타일을 만들어 커밋해라 — D 가 이것 하나로 뚫린다 (결정 2).**
   - `data-platform/fixtures/regions-sigungu-fixture.pmtiles` — 250개, 기하 단순화, **5MB 이하**
   - `data-platform/fixtures/manifest-fixture.json` — `boundary_vintage: "fixture"`
   D 는 이 픽스처로 통합 테스트를 끝낼 수 있고, 실 아티팩트가 나오면 `tile_url` 만 바뀐다.
   **개정 3 정정 — 이 작업의 순서가 바뀌었다.** 개정 2 는 *"다른 어떤 작업보다 이게 먼저"* 라고 했으나,
   그 상태로 픽스처를 구우면 **`region_id` 속성이 없는 픽스처**가 나온다 (VF-003).
   D 는 뚫린 줄 알고 붙였다가 또 회색 지도를 본다.
   **위 VF-003 작업(properties 유지 + 빌드 자체 검증)을 끝낸 파이프라인으로 이 픽스처를 구워라.**
   순서만 바뀌었을 뿐, D 를 막고 있는 게 이 파일이라는 사실은 그대로다.

3. **레벨 산출 순서를 `sigungu` → `adm_dong` → `sido` 로 바꿔라 (결정 3).**
   지금 너는 `sido` 만 냈다. 픽스처·샘플·기본 objective 가 전부 `sigungu` 라서 순서가 뒤집혔다.

4. **줌 범위를 매니페스트에 결정 4 표대로 기록해라.**
   `sido` 0–10 / `sigungu` 4–12 / `adm_dong` 5–14. 저줌에서는 기하 단순화 강도를 높인다.

5. **`demand_signal` 조인 키를 `sbiz_codes` 로 고정해라 (ADR-004).**
   - `02_taxonomy.json` 에서 `sbiz_codes` 가 **비어 있는 노드 목록을 뽑아 보고해라.**
     상속으로 해결되는지, 매핑 추가가 필요한지 판단이 필요하다. 이건 네가 내야 답이 나온다.
   - `data_source` 레지스트리에 상권정보 등록 시 `known_limitations` 에 명시:
     분기 갱신(최대 3개월 시차) / 무점포 사업자 미포함 / 대형 유통 일부 누락
   - **`card_mcc` 수집 코드는 작성하지 마라.** 라이선스 미확보다.

6. **B 의 질문 2건에 답해라 (B 가 네 답을 기다리며 스텁으로 진행 중).**
   - `get_features(region_ids, feature_keys, as_of)` 의 실제 호출 방식.
     B 가 이 시그니처로 스텁을 만들어 뒀다 — 같은 모양으로 내면 B 쪽 코드 변경이 0 이다.
   - `demand_signal.coverage_flag='suppressed'` 상위 지역 대체를 **A 가 하나 B 가 하나.**
     B 는 "B 가 한다"고 가정하고 진행 중이다. 네가 이미 대체해 주면 이중 처리된다.

7. **`RECONCILIATION.md` §5 의 본래 순서 재개.** region 모델 → `region_feature` 스토어
   (`03_region_features.json` 의 `point_in_time_rule`, "최신값" 헬퍼 금지).

---

## 확인 방법 — 명령어와 통과 기준

```bash
# 매니페스트가 계약 형식인지 (엔트리 1개 기준)
python tools/validate_contracts.py --check-manifest data-platform/fixtures/manifest-fixture.json

# 폴더 경계 위반 검사 (통과 = exit 0)
python tools/validate_contracts.py --base origin/master --agent A

# 테스트 (현재 기준선: 6 passed)
data-platform/.venv/Scripts/python.exe -m pytest data-platform/tests -q

# 픽스처 크기 (5MB 이하)
ls -l data-platform/fixtures/regions-sigungu-fixture.pmtiles

# 매니페스트가 실제로 추적되는지 / 타일이 안 들어갔는지
git ls-files data-platform/output/manifest data-platform/fixtures
git status --short data-platform/output/tiles    # 아무것도 안 나와야 정상
```

통과 기준: `--check-manifest` 오류 0 (`feature_id_property == "region_id"`,
`available_vintages` 가 `boundary_vintage` 포함, `tile_url` 절대 URL, `.mvt`·`/predictions/` 아님).
**`git ls-files` 에 `.pmtiles` 가 하나도 잡히지 않아야 한다** — 픽스처는 예외로 커밋하되
`output/tiles/` 의 실 아티팩트는 절대 들어가면 안 된다.

> 네 `output/manifest/*.json` 은 이제 C 의 입력이다. 형식이 바뀌면 C 가 즉시 깨진다.
> 형식을 바꿀 때는 커밋 메시지에 명시해라.

---

## 하지 말 것

- **`.pmtiles` 실 아티팩트를 git 에 커밋하지 마라.** 히스토리에서 지울 수 없다. (D-11)
  예외는 `fixtures/` 의 5MB 이하 축소 픽스처 하나뿐이다.
- **`.pmtiles` 파이프라인을 되돌리지 마라.** 계약에 맞다. (D-05)
- **타일 서빙 API 를 만들지 마라.** C 소유다. (D-05)
- **`card_mcc` 수집 코드를 쓰지 마라.** 라이선스 미확보. (D-18)
- **결측을 0 으로 채우지 마라.** 매핑 없는 노드는 confidence 하향이지 0 이 아니다. (D-19)
- **"최신값" 피처 헬퍼를 만들지 마라.** `point_in_time_rule` 위반.
- **다른 에이전트의 코드·CCR 을 계약으로 삼지 마라.** (D-10)
- **`shared/contracts/`, `/backend`, `/intelligence`, `/console` 을 수정하지 마라.**
