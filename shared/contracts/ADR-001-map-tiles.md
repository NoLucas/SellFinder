# ADR-001. 지도 타일 소유권 분리 (경계 타일 ≠ 예측 결과)

- **상태**: 채택 (2026-08-14)
- **제기자**: 에이전트 A, C, D — 세 곳이 독립적으로 동일한 모호성을 보고
- **영향 파일**: `04_api_contract.yaml` (v0.2.1), `03_region_features.json`, `01_domain_model.json`

---

## 문제

`04_api_contract.yaml` v0.2.0 에 있던 엔드포인트

```
GET /predictions/{run_id}/tiles/{z}/{x}/{y}.mvt
```

이 **지역 경계 기하(geometry)** 와 **예측 점수(dynamic data)** 를 하나의 타일에 담는 것처럼 읽혔다.
동시에 `03_region_features.json` 은 에이전트 A 에게 "벡터타일 생성"을 지시했다.
그 결과 A·C·D 세 곳이 각자 "타일을 누가 만드나"를 물었다. **계약 결함이다.**

## 결정

**둘은 완전히 다른 자원이며, 서버에서 합치지 않는다. 클라이언트에서 합친다.**

```
┌─────────────────────────────────────────────────────────────┐
│ 정적 경계 타일 (A 생성)                                        │
│  · 전 테넌트 공용 · 인증 불필요 · CDN 영구 캐시                  │
│  · 행정구역 개편 시에만 재생성 (연 1~2회)                        │
│  · 산출물: .pmtiles 아티팩트 + manifest.json                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │  ┌──────────────────────────────────┐
                        │  │ 예측 점수 JSON (C 서빙)            │
                        │  │  · 테넌트 전용 · 인증 필수          │
                        │  │  · run 마다 변경 · 캐시 불가        │
                        │  │  · 3,500행 ≈ 압축 후 30KB          │
                        │  └──────────────┬───────────────────┘
                        ▼                 ▼
              ┌───────────────────────────────────────┐
              │ D: 클라이언트에서 join                  │
              │ map.setFeatureState(                  │
              │   {source:'regions', id: region_id},  │
              │   {score, confidence}                 │
              │ )                                     │
              └───────────────────────────────────────┘
```

### 왜 타일에 점수를 굽지 않는가

1. **조합 폭발** — 테넌트 × 예측실행 × 줌레벨마다 타일셋을 새로 만들어야 한다.
   고객사 50곳이 하루 10번씩 예측하면 하루 500개 타일셋이다.
2. **캐싱 불가** — 점수가 들어간 타일은 테넌트 기밀이므로 공용 CDN에 올릴 수 없다.
   경계 기하(수백 MB)를 매번 인증 뒤로 내려보내게 된다.
3. **지연** — 타일 생성이 예측 완료의 후행 작업이 되어 결과 표시가 수십 초 늦어진다.
4. **점수 데이터는 작다** — 3,500개 행정동 × (region_id, score, confidence) 는
   압축하면 30KB 남짓이다. 타일로 만들 이유가 전혀 없다.

---

## 소유권 확정

| 자원 | 소유 | 산출 형태 | 비고 |
|---|---|---|---|
| 행정경계 기하 (sido/sigungu/adm_dong) | **A** | `.pmtiles` 아티팩트 + `manifest.json` | API 아님. 오브젝트 스토리지에 올리는 정적 파일. |
| 경계 타일 서빙 / 서명 URL 발급 | **C** | `GET /basemap/regions/manifest` | C 는 타일을 **생성하지 않는다.** A 의 아티팩트를 가리키는 URL만 발급. |
| 예측 점수 배열 | **C** | `GET /predictions/{run_id}/scores` | 지도 렌더링 전용 경량 응답 |
| 테넌트 정의 상권(custom_catchment) 기하 | **C** | 위 scores 응답에 GeoJSON 인라인 | 테넌트 전용이라 공용 타일에 넣을 수 없음. 개수가 수십 개 수준이라 인라인으로 충분. |
| 클라이언트 join · 렌더링 | **D** | `setFeatureState` | |

**폐기**: `GET /predictions/{run_id}/tiles/{z}/{x}/{y}.mvt` — v0.2.1 에서 삭제.

---

## 경계 빈티지(boundary vintage) — 조용히 터지는 지점

행정동 코드는 개편으로 바뀐다. 지금 실행한 예측을 6개월 뒤에 다시 열었을 때,
**그때의 경계 타일**이 아니라 **최신 경계 타일**을 불러오면 지역이 어긋나 엉뚱한 곳이 칠해진다.
사용자는 이걸 눈치채지 못한 채 잘못된 지역에 출점 결정을 내린다.

### 규칙

1. A 는 타일셋을 빈티지별로 보존한다. 덮어쓰지 않는다.
   `regions-adm_dong-2026-01-01.pmtiles`, `regions-adm_dong-2025-01-01.pmtiles` …
2. `prediction_run` 에 `boundary_vintage` 필드를 추가한다 (`01_domain_model.json` v0.2.1).
   예측 실행 시점의 빈티지를 고정 기록한다.
3. `/predictions/{run_id}/scores` 응답은 `boundary_vintage` 를 함께 반환한다.
4. D 는 그 빈티지에 해당하는 타일셋을 로드한다. 항상 최신을 로드하면 안 된다.
5. 코드가 바뀐 지역의 시계열은 `region_code_mapping` 으로 잇는다
   (`03_region_features.json` region_hierarchy.rules 참조).

---

## 신규 엔드포인트 (04_api_contract.yaml v0.2.1)

### `GET /v1/basemap/regions/manifest`

```
Query: level=adm_dong  &  vintage=2026-01-01   (vintage 생략 시 최신)
```

```json
{
  "level": "adm_dong",
  "boundary_vintage": "2026-01-01",
  "tile_url": "https://cdn.sellfinder.kr/tiles/regions-adm_dong-2026-01-01.pmtiles",
  "source_layer": "regions",
  "feature_id_property": "region_id",
  "minzoom": 5,
  "maxzoom": 12,
  "attribution": "통계청 SGIS",
  "available_vintages": ["2026-01-01", "2025-01-01", "2024-01-01"]
}
```

- 인증은 필요하지만 테넌트 무관. 캐시 가능 (`Cache-Control: public, max-age=3600`).
- `feature_id_property` 는 D 가 `setFeatureState` 의 키로 쓴다. 반드시 `region_id` 로 통일.

### `GET /v1/predictions/{run_id}/scores`

지도 렌더링 전용. **이 엔드포인트만 커서 페이지네이션 규칙의 예외다** —
지도는 전체 지역을 한 번에 칠해야 하므로 분할 전송이 무의미하다.

```json
{
  "run_id": "run_01J8XM2",
  "region_level": "adm_dong",
  "boundary_vintage": "2026-01-01",
  "objective": "distribution_push",
  "data_tier": "T1",
  "schema": ["region_id", "opportunity_score", "confidence_level"],
  "scores": [
    ["1111051500", 87.4, "high"],
    ["1111052000", 62.1, "medium"],
    ["1111053000", 31.8, "low"]
  ],
  "score_range": { "min": 12.3, "max": 94.8, "p50": 51.7 },
  "custom_geometries": null
}
```

**설계 근거**
- 객체 배열이 아니라 **튜플 배열 + schema** 를 쓴다. 3,500행에서 키 반복이 사라져 페이로드가 약 60% 줄어든다.
- `score_range` 를 함께 보내 D 가 색상 스케일을 서버 값 기준으로 고정한다.
  클라이언트가 받은 데이터로 min/max 를 계산하면, 필터를 바꿀 때마다 색이 흔들려 비교가 불가능해진다.
- `region_level=custom_catchment` 인 경우에만 `custom_geometries` 에 GeoJSON FeatureCollection 이 채워진다.
  이때 `tile_url` 은 사용하지 않는다.
- `expected_revenue_krw` 는 여기 넣지 않는다. 금액은 지역 상세 조회에서만 반환한다
  (T0 금지 규칙을 한 곳에서만 지키면 되도록).

---

## 각 에이전트가 지금 할 일

**A (data-platform)**
- 경계 타일을 빈티지별 `.pmtiles` 로 생성하고 `manifest.json` 을 함께 산출한다.
- 각 피처의 속성에 `region_id` 를 **feature id 로** 넣는다 (속성이 아니라 id). `setFeatureState` 가 이걸 쓴다.
- 타일 서빙 API 를 만들지 않는다. 아티팩트 생성까지가 A 의 책임이다.
- 빈티지를 덮어쓰지 않는다.

**C (backend)**
- 위 두 엔드포인트를 구현한다. `.mvt` 엔드포인트는 만들지 않는다.
- `basemap/regions/manifest` 는 A 아티팩트의 URL(필요 시 서명 URL)만 반환한다. 타일을 생성·프록시하지 않는다.
- `prediction_run.boundary_vintage` 를 기록하고 scores 응답에 실어 보낸다.

**D (console)**
1. `manifest` 로 타일 URL 확보 → 지도에 소스 등록
2. `scores` 로 점수 배열 확보
3. `setFeatureState` 로 join, 색상은 `score_range` 기준 고정 스케일
4. 지역 클릭 시에만 `/predictions/{run_id}/regions/{region_id}` 로 상세·요인분해 조회
- `confidence_level='low'` 는 색이 아니라 **해칭 패턴**으로 구분한다.
  색만 옅게 하면 "점수가 낮은 것"과 구분되지 않는다.

---

## 검토한 대안

| 대안 | 기각 사유 |
|---|---|
| 예측 점수를 타일에 굽기 | 조합 폭발, 캐싱 불가, 결과 표시 지연 |
| 매 요청마다 GeoJSON 전체 전송 | 전국 행정동 경계는 수십 MB. 모바일·저사양에서 사용 불가 |
| 서버가 PNG 히트맵 렌더링 | 클릭 인터랙션·툴팁 불가. 기업 콘솔에는 부적합 |
| A 가 타일 서빙 API 까지 소유 | 인증·RBAC·감사가 C 에 있는데 서빙만 A 로 가면 권한 경계가 두 군데로 쪼개짐 |
