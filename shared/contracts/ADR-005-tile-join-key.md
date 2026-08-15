# ADR-005. 타일 조인 키 — `region_id` 는 **속성**으로 싣는다

- **상태**: 채택 (2026-08-16)
- **제기**: 검증 에이전트 1회차 `VF-003` (S2) — 실제 아티팩트를 붙여 0/5 매칭 확인
- **영향 파일**: `ADR-001-map-tiles.md`(정정), `04_api_contract.yaml` (v0.2.2)
- **영향 에이전트**: A, C, D

---

## 문제 — 계약이 서로 반대되는 두 지시를 담고 있었다

`ADR-001-map-tiles.md` 안에서 두 문장이 충돌한다.

| 위치 | 문장 | 누가 읽었나 |
|---|---|---|
| §"신규 엔드포인트" | *"`feature_id_property` 는 D 가 `setFeatureState` 의 키로 쓴다. 반드시 `region_id` 로 통일."* | **D** |
| §"각 에이전트가 지금 할 일" · A | *"각 피처의 속성에 `region_id` 를 **feature id 로** 넣는다 (속성이 아니라 id)."* | **A** |

A 는 두 번째를 따라 `region_id` 를 properties 에서 제거하고 숫자 feature id 로 실었다
(`tiler.py`, `feature_id.py`, 역매핑은 `*.id_map.json`).
D 는 첫 번째를 따라 `promoteId: {regions: "region_id"}` 로 그 속성을 찾는다.

결과 (검증자가 A 의 실제 `.pmtiles` + C 의 실제 매니페스트 + D 의 실제 조인 코드로 실행):

```
manifest.feature_id_property = "region_id"
tile feature ids (A, real)   = 11, 26, 28, 41, 50
tile feature properties keys = ["name","level","is_synthetic_placeholder"]   ← region_id 가 없다
features that received a score : 0/5
→ 전 지역이 NO_DATA 회색. 에러도 콘솔 경고도 없다.
```

세 폴더의 테스트와 `validate_contracts.py` 가 **전부 통과하는 상태**에서 화면만 조용히 비어 있었다.

**A 도 D 도 틀리지 않았다. 계약이 틀렸다.** 두 번째 문장은 MapLibre 의 `promoteId` 가
"속성을 feature id 로 승격시키는" 표준 메커니즘이라는 사실을 모른 채 쓰였다.
`promoteId` 가 있으므로 "속성이 아니라 id 로 넣어야 한다"는 전제 자체가 성립하지 않는다.

---

## 결정 — `region_id` 를 properties 에 싣는다. `feature_id_property` 가 유일한 조인 키다

1. **A 는 모든 타일 피처의 `properties` 에 `region_id` 를 넣는다.**
   문자열 원문 그대로다. 가공·정규화·정수화하지 않는다.
2. **`feature_id_property` 규약은 그대로 유지된다** (`"region_id"` 고정).
   D 는 지금 코드를 바꾸지 않는다.
3. **네이티브 MVT feature id 는 계속 넣어도 된다** (툴 호환·디버깅에 유용하다).
   다만 **조인 키가 아니다.** 어떤 소비자도 여기에 의존하지 않는다.
4. **`id_map.json` 은 계약 산출물에서 제외한다.** A 의 매니페스트에서 `id_map_path` 를 뺀다.
   내부 빌드 산출물로 남기는 것은 자유지만, 소비자가 의존하기 시작하면 조인 키가 다시 두 갈래가 된다.

### 왜 반대 방향(네이티브 id + id_map)이 아닌가

| | 속성 `region_id` (채택) | 네이티브 id + id_map (기각) |
|---|---|---|
| 조인 양변 타입 | 문자열 ↔ 문자열 (`/scores` 도 문자열) | 문자열 → 정수 변환 필요 |
| 조용한 실패 경로 | 없음 | **선행 0**(`"01100"`→1100), **2⁵³ 초과**, **해시 충돌** 3종 |
| 클라이언트 크리티컬 패스 | 타일 + 점수 2개 | + `id_map.json` (빈티지마다, 캐시 무효화 대상) |
| JS 쪽 구현 | 없음 (`promoteId` 한 줄) | sha256 48비트 변환을 JS 에 중복 구현 |
| 사람이 디버깅 | 타일 인스펙터에서 바로 읽힘 | 역매핑 파일을 열어야 함 |
| 비용 | 피처당 문자열 1개 (3,500개 기준 gzip 후 수십 KB) | — |

정수 변환은 **지금은 맞다.** 표준 행정코드가 전부 숫자이기 때문이다.
그러나 `region_id` 는 통계청이 소유한 외부 식별자이고 코드 체계는 바뀐다.
"현재 값이 전부 숫자"라는 성질에 조인을 거는 것은, 깨질 때 **예외가 아니라 빈 지도**로 나타난다.
VF-003 이 정확히 그 모습이었다. 타일 크기 몇십 KB 로 그 실패 모드를 통째로 없앤다.

---

## 각 에이전트가 할 일

**A (data-platform)**
- `tiler.py` 가 `region_id` 를 properties 에서 제거하는 동작을 멈춘다. 원문 문자열로 유지한다.
- 매니페스트에서 `id_map_path` 제거.
- **빌드 자체 검증을 추가한다**: 매니페스트가 광고하는 `feature_id_property` 가
  실제로 산출된 타일의 첫 피처 properties 에 존재하는지 확인하고, 없으면 빌드를 실패시킨다.
  이 검사 하나가 VF-003 을 A 의 스위트 안에서 잡는다.

**C (backend)**
- `FEATURE_ID_PROPERTY` 하드코딩을 지우고 **A 매니페스트의 값을 그대로 전달**한다 (D-13 과 같은 성격).

**D (console)**
- 코드 변경 없음. `promoteId` 를 유지한다.
- 조인이 실제로 성립하는지 테스트로 고정한다 (VF-009).
  `verification/fixtures/vf_56_join.mjs` 가 참고 구현이다.

## 완료 판정

다음 검증 회차에 `vf_56_join.mjs` 재실행 결과가 **0/5 → 전건 매칭**이면 VF-003 을 닫는다.
레벨 불일치(A=시도 / C 샘플=시군구)는 D-12·D-15 로 별도로 닫힌다 — 이 ADR 의 범위가 아니다.
