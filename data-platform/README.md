# data-platform (에이전트 A)

SellFinder 데이터 플랫폼. 범위는 `shared/contracts/README.md`의 폴더 소유권대로 이 폴더 안으로
한정한다. `/intelligence`, `/backend`, `/console`, `/shared/contracts`는 건드리지 않는다.

진행 경과는 [`RECONCILIATION.md`](./RECONCILIATION.md) 참고.

## 경계 타일 파이프라인 (`src/boundary_tiles/`)

지역 경계(GeoJSON)를 빈티지(boundary_vintage)별 `.pmtiles` + `manifest.json`으로 만드는 빌드 도구.
**여기까지가 A의 책임이다 — 이 아티팩트를 HTTP로 서빙하는 API는 만들지 않는다.**
소유권/설계 근거는 [`shared/contracts/ADR-001-map-tiles.md`](../shared/contracts/ADR-001-map-tiles.md)
참고: 경계 기하(정적, A)와 예측 점수(동적, backend)는 서버에서 합치지 않고 콘솔이
`setFeatureState`로 클라이언트에서 합친다. `backend`가 `GET /basemap/regions/manifest`에서
이 아티팩트를 가리키는(필요 시 서명된) URL만 내려준다 — 타일을 생성·프록시하지 않는다.

### 산출물 계약

필드는 `shared/contracts/04_api_contract.yaml`의 `GET /basemap/regions/manifest` 응답 예시와
정확히 맞췄다 — 계약이 근거이며, 다른 폴더의 구현 코드가 이와 달라 보이더라도 계약을 따른다.

- `output/tiles/manifest.json` — 레벨(`sido`/`sigungu`/`adm_dong`)별 vintage 목록.
  `levels.<level>.vintages.<boundary_vintage>`에 계약과 동일한 필드를 담는다:
  `level`, `boundary_vintage`, `tile_url`, `source_layer`("regions" 고정),
  `feature_id_property`("region_id" 고정), `minzoom`/`maxzoom`, `attribution`,
  `available_vintages`(그 레벨에 지금 존재하는 전체 vintage 목록 — 새 vintage가 추가될
  때마다 예전 항목에서도 함께 갱신됨. 단, `tile_url`/`sha256`/`feature_count` 등 그 vintage
  자체를 정의하는 필드는 절대 바뀌지 않는다).
  계약엔 없지만 리니지·재현성 확인용으로 `id_map_path`, `feature_count`, `bounds`,
  `source_id`, `sha256`, `built_at`, `valid_to`도 함께 싣는다.
  `tile_url`은 리포지토리 상대경로다 — 실제 CDN/오브젝트 스토리지 URL로 바꾸는 건 이
  아티팩트를 배포하는 쪽(운영/backend)의 몫이다.
- `output/tiles/regions-<level>-<vintage>.pmtiles` — 벡터 타일 아카이브
  (`ADR-001-map-tiles.md` 파일명 규칙 그대로). MVT 레이어명은 레벨과 무관하게 `regions`로
  고정 — 콘솔이 level/vintage가 바뀌어도 `source-layer: 'regions'` 하나로 스타일을 참조할 수
  있게 하기 위함.
- `output/tiles/regions-<level>-<vintage>.id_map.json` — `region_id_to_feature_id` /
  `feature_id_to_region_id` 양방향 매핑.
- **feature id 규칙**: 각 피처의 `region_id`는 MVT 속성(properties)에 넣지 않는다. 대신
  `region_id`를 결정론적으로 변환한 정수를 MVT의 네이티브 feature id로 싣는다
  (`src/boundary_tiles/feature_id.py`). 콘솔은 `setFeatureState({source, sourceLayer, id}, ...)`에
  이 id를 그대로 쓴다 — `promoteId`로 속성에서 끌어올 필요가 없다(`feature_id_property`는
  "이 id의 의미가 region_id"라는 문서화용 값이지, MapLibre `promoteId`에 넘길 속성 키가
  아니다). 숫자 region_id(행정표준코드 등)는 `int(region_id)` 그대로, 비숫자(`h3_`/`cst_`
  접두사 — v1에서는 등장하지 않음, custom_catchment는 애초에 이 파이프라인 대상이 아니라
  scores 응답에 GeoJSON으로 인라인됨)는 sha256 앞 48비트 해시를 쓴다(JS
  `Number.MAX_SAFE_INTEGER` 안에 들어오도록).
- **빈티지는 불변이다**: 동일 `(level, boundary_vintage)`로 다시 빌드하면 무조건 실패한다
  (`manifest.py`의 `VintageExistsError`). 소스 데이터가 바뀌면 새 vintage(날짜)를 쓴다.
  `prediction_run.boundary_vintage`가 참조하는 경계가 조용히 바뀌는 걸 막기 위함
  (`ADR-001-map-tiles.md` "경계 빈티지 — 조용히 터지는 지점").

### 알려진 한계

- tippecanoe류가 하는 줌별 지오메트리 단순화/일반화가 없다. 지금은 파이프라인 정합성(경계 →
  타일 → feature id 왕복)만 검증한 상태이고, 실제 경계 소스 연동 시점에 단순화를 추가해야 한다.
- 지금 쓰는 경계 소스는 `tests/fixtures/*.geojson`의 합성 사각형이다(각 feature에
  `is_synthetic_placeholder: true`로 표시됨, `attribution` 필드에도 명시). 실제 시도/시군구/
  행정동 경계는 통계청 SGIS 등에서 받아와야 한다(`03_region_features.json`의
  `recommended_public_sources` 참고) — 아직 미연동.

## 사용법

```bash
python -m venv .venv && .venv/Scripts/activate  # 또는 source .venv/bin/activate
pip install -r requirements.txt

python -m src.boundary_tiles.build \
  --level sido --vintage 2026-01-01 \
  --source tests/fixtures/sido_sample_2026-01-01.geojson \
  --source-id src_sample_boundary

pytest
```

## 레벨별 줌 범위 (`src/boundary_tiles/build.py`의 `LEVEL_ZOOM`)

adm_dong은 `04_api_contract.yaml` 예시(minzoom=5, maxzoom=12)와 동일하게 맞췄다. sido/sigungu는
계약에 예시가 없어 `03_region_features.json`의 `region_hierarchy` 용도에 맞춘 대략치.
`census_block`/`h3_r8`/`custom_catchment`은 v1 범위 밖(`00_product_spec.md` §6)이라 여기 없음.

| level | minzoom | maxzoom |
|---|---|---|
| sido | 0 | 8 |
| sigungu | 5 | 11 |
| adm_dong | 5 | 12 |
