# ADR-002. 아티팩트 발행 경로 · 지역 레벨 · 줌 범위

- **상태**: 채택 (2026-08-15)
- **제기**: 총괄자 첫 스윕 — 지시받지 않고 발견한 차단 요인
- **영향 파일**: `04_api_contract.yaml`, `03_region_features.json`, `.gitignore`
- **영향 에이전트**: A, C, D

---

## 문제 1 — 아티팩트가 소비자에게 도달하지 않는다

`data-platform/output/` 이 `.gitignore:5` 로 제외되어 있어 `.pmtiles` 와 `manifest.json` 이
A 의 디스크에만 존재한다. C 는 URL 을 발급할 근거가 없고, D 는 렌더할 타일이 없다.
**현재 프로젝트 최대 차단 요인.**

## 결정 1 — 메타데이터와 아티팩트를 분리한다

지금 둘이 같은 폴더에 있는 게 원인이다. 성격이 완전히 다르다.

| | manifest.json | .pmtiles |
|---|---|---|
| 크기 | 수 KB | 수십~수백 MB |
| 형식 | 텍스트 | 바이너리 |
| 변경 빈도 | 빈티지 추가 시 | 빈티지 추가 시 |
| git 적합성 | **적합** | **부적합** (히스토리 영구 오염) |
| 성격 | 계약 형태의 인수인계물 | 빌드 산출물 |

```
data-platform/
  output/
    manifest/                    ← git 추적 O
      regions-sido-2026-01-01.json
      regions-sigungu-2026-01-01.json
    tiles/                       ← git 추적 X (.gitignore)
      regions-sigungu-2026-01-01.pmtiles
  fixtures/                      ← git 추적 O (아래 결정 2)
    regions-sigungu-fixture.pmtiles
```

`.gitignore` 를 아래로 교체한다.

```gitignore
data-platform/output/tiles/
!data-platform/output/manifest/
!data-platform/fixtures/
```

**`.pmtiles` 를 git 에 커밋하지 마라.** 한 번 들어가면 히스토리에서 지울 수 없고,
빈티지가 늘 때마다 저장소가 수백 MB 씩 불어난다.

## 결정 2 — 픽스처 타일을 커밋해 D 를 지금 뚫는다

전체 아티팩트 발행 인프라(오브젝트 스토리지)는 v1 배포 시점 과제다.
그때까지 D 를 세워두면 안 된다.

**A 는 `sigungu` 레벨 250개만 담은 축소 픽스처 타일을 만들어 커밋한다.**

- 레벨: `sigungu` (250개 — 전국 커버, 파일 작음, 실사용과 형태 동일)
- 기하 단순화: 목표 파일 크기 **5MB 이하**
- 경로: `data-platform/fixtures/regions-sigungu-fixture.pmtiles`
- 대응 매니페스트: `data-platform/fixtures/manifest-fixture.json`
  (`boundary_vintage: "fixture"`, `tile_url` 은 상대경로 규약 아래 참조)

D 는 이 픽스처로 지금 통합 테스트를 완료할 수 있고,
실 아티팩트가 발행되면 `tile_url` 만 바뀐다.

### 개발 중 tile_url 규약

계약은 `tile_url` 이 절대 URL 이어야 한다고 정했다. 개발 환경도 이를 지킨다.

```
개발  : http://localhost:{PORT}/artifacts/regions-sigungu-fixture.pmtiles
운영  : https://cdn.sellfinder.kr/tiles/regions-sigungu-2026-01-01.pmtiles
```

C 의 개발 서버가 `data-platform/fixtures/` 와 로컬 `artifacts/` 를 정적 서빙한다.
계약 변경 없음.

---

## 문제 2 — A 와 C 의 매니페스트가 어긋난다

A: `sido` 한 레벨, 빈티지 `2026-01-01` / `2026-07-01`
C: 3레벨 하드코딩, 빈티지 `2026-01-01` / `2025-01-01` / `2024-01-01`
겹치는 항목이 하나뿐이다.

## 결정 3 — C 는 하드코딩을 버리고 A 의 매니페스트를 읽는다

**근본 원인은 C 가 값을 지어낸 것이다.** 빈티지 목록은 A 만 알 수 있다.

- C 는 `data-platform/output/manifest/*.json` 을 읽어 `available_vintages` 를 구성한다.
  하드코딩 금지. 파일이 없으면 빈 배열이 아니라 **503 + 명확한 사유**를 반환한다.
  (빈 배열은 "빈티지가 없다"는 거짓 정보다)
- C 코드의 `"A가 아직 안 냈다"` 주석은 낡았다. 제거한다.
- A 는 다음 순서로 레벨을 낸다: **`sigungu` → `adm_dong` → `sido`**
  (`sigungu` 가 먼저인 이유는 픽스처·샘플·기본 objective 가 모두 이 레벨이기 때문)

---

## 문제 3 — 레벨별 줌 범위가 미정이라 충돌

ADR-001 이 `adm_dong` 만 정해서 `sido` 는 A=0, C=5 로 갈렸다. 위반이 아니라 공백이다.

## 결정 4 — 레벨 선택은 사용자가, 줌은 겹쳐서 넉넉히

**레벨은 줌에 따라 자동 전환되지 않는다.** 사용자가 UI 에서 시도/시군구/행정동을 고른다.
따라서 줌 범위는 그 레벨이 읽히는 구간을 넉넉히 덮으면 되고, 겹쳐도 무방하다.

| level | minzoom | maxzoom | 비고 |
|---|---|---|---|
| `sido` | **0** | **10** | 전국 뷰에서 바로 보여야 함 |
| `sigungu` | **4** | **12** | 기본 작업 레벨 |
| `adm_dong` | **5** | **14** | ADR-001 의 5~12 를 14 로 확장 (오버줌 여유) |

- 저줌에서는 기하 단순화 강도를 높인다. 전국 뷰에서 행정동 원본 좌표는 불필요하다.
- maxzoom 을 넘는 줌은 오버줌으로 처리한다. 타일을 더 만들지 않는다.

`04_api_contract.yaml` 의 manifest 예시(minzoom 5 / maxzoom 12)는 `adm_dong` 기준 예시였다.
레벨별 실제 값은 A 의 매니페스트가 정하며, C 는 그대로 전달한다.

---

## 문제 4 — `backend/samples/scores.json` 의 레벨 불일치

`region_level: "adm_dong"` 인데 `region_id` 가 전부 5자리(sigungu)다.
새 `--check-scores` 가 경고 5건으로 잡았다. D 가 이 파일로 통합 테스트를 시작한다.

## 결정 5 — 샘플을 `sigungu` 로 정정한다

`region_level` 을 `"sigungu"` 로 바꾼다. `region_id` 는 그대로 둔다.

이유:
- 픽스처 타일이 `sigungu` 다 (결정 2). 샘플과 타일 레벨이 맞아야 D 가 실제로 렌더까지 간다.
- `distribution_push` objective 의 기본 단위가 `sigungu` 다 (`05_scoring_spec.md` §3.2).
- 변경이 한 줄이다.

`boundary_vintage` 는 픽스처를 가리키도록 `"fixture"` 로 맞춘다.

---

## 각 에이전트가 할 일

**A**
1. `.gitignore` 를 위 결정 1 대로 교체 (jin 승인 완료)
2. `output/` 을 `manifest/` 와 `tiles/` 로 분리, 매니페스트는 커밋
3. `sigungu` 픽스처 타일 생성 후 `data-platform/fixtures/` 에 커밋 (5MB 이하)
4. 레벨 산출 순서: `sigungu` → `adm_dong` → `sido`
5. 줌 범위를 결정 4 표대로 매니페스트에 기록

**C**
1. `available_vintages` 하드코딩 제거 → A 의 매니페스트 파일을 읽어 구성
2. 매니페스트 파일 부재 시 빈 배열이 아니라 503 + 사유 반환
3. 낡은 주석 제거
4. `backend/samples/scores.json` 을 `region_level: "sigungu"`, `boundary_vintage: "fixture"` 로 정정
5. 개발 서버가 `data-platform/fixtures/` 를 `/artifacts/` 로 정적 서빙

**D**
1. A 의 픽스처 타일 + C 의 정정된 샘플로 통합 테스트 완료
2. `tile_url` 을 하드코딩하지 말고 매니페스트 응답에서 받아 쓴다
   (개발/운영 URL 이 바뀌어도 코드가 안 바뀌게)
