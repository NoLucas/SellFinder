# data-platform (에이전트 A)

SellFinder 데이터 플랫폼. 범위는 `shared/contracts/README.md`의 폴더 소유권대로 이 폴더 안으로
한정한다. `/intelligence`, `/backend`, `/console`, `/shared/contracts`는 건드리지 않는다.

진행 경과는 [`RECONCILIATION.md`](./RECONCILIATION.md) 참고.

## 경계 타일 파이프라인 (`src/boundary_tiles/`)

지역 경계(GeoJSON)를 빈티지(vintage)별 `.pmtiles` + `manifest.json`으로 만드는 빌드 도구.
**여기까지가 A의 책임이다 — 이 아티팩트를 HTTP로 서빙하는 API는 만들지 않는다** (`/backend`가
`04_api_contract.yaml`의 타일 엔드포인트에서 이 산출물을 읽어 서빙한다).

### 산출물 계약 (콘솔/백엔드가 알아야 할 것)

- `output/tiles/manifest.json` — 레벨(`sido`/`sigungu`/`adm_dong`)별 vintage 목록. 각 항목에
  `pmtiles_path`, `id_map_path`, `valid_from`/`valid_to`, `bounds`, `source_id`, `sha256`을 담는다.
- `output/tiles/<level>/<vintage>.pmtiles` — 벡터 타일 아카이브. 레이어명은 `level`과 동일.
- `output/tiles/<level>/<vintage>.id_map.json` — `region_id_to_feature_id` / `feature_id_to_region_id`
  양방향 매핑.
- **feature id 규칙**: 각 피처의 `region_id`는 MVT 속성(properties)에 넣지 않는다. 대신
  `region_id`를 결정론적으로 변환한 정수를 MVT의 네이티브 feature id로 싣는다
  (`src/boundary_tiles/feature_id.py`). 콘솔의 `setFeatureState({source, sourceLayer, id}, ...)`가
  이 id를 그대로 키로 쓴다 — `promoteId`로 속성에서 끌어올 필요가 없다. 숫자 region_id(행정표준코드
  등)는 `int(region_id)` 그대로, 비숫자(`h3_`/`cst_` 접두사)는 sha256 앞 48비트 해시를 쓴다(JS
  `Number.MAX_SAFE_INTEGER` 안에 들어오도록). region_id → feature_id 역참조가 필요하면 반드시
  `id_map.json`을 거친다.
- **빈티지는 불변이다**: 동일 `(level, vintage)`로 다시 빌드하면 무조건 실패한다
  (`manifest.py`의 `VintageExistsError`). 소스 데이터가 바뀌면 새 vintage(날짜)를 쓴다. 과거
  예측(`prediction_run.feature_as_of`)이 참조하는 경계가 조용히 바뀌는 걸 막기 위함 —
  `06_governance.md`의 "피처 스토어를 덮어쓰기로 갱신하면 과거 예측이 재현 불가능해진다"와 같은 이유.

### 알려진 한계

- tippecanoe류가 하는 줌별 지오메트리 단순화/일반화가 없다. 지금은 파이프라인 정합성(경계 →
  타일 → feature id 왕복)만 검증한 상태이고, 실제 경계 소스 연동 시점에 단순화를 추가해야 한다.
- 지금 쓰는 경계 소스는 `tests/fixtures/*.geojson`의 합성 사각형이다(각 feature에
  `is_synthetic_placeholder: true`로 표시됨). 실제 시도/시군구/행정동 경계는 통계청 SGIS 등에서
  받아와야 한다(`03_region_features.json`의 `recommended_public_sources` 참고) — 아직 미연동.

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

`03_region_features.json`의 `region_hierarchy` 용도에 맞춘 대략치. `census_block`/`h3_r8`/
`custom_catchment`은 v1 범위 밖(`00_product_spec.md` §6)이라 여기 없음.

| level | min_zoom | max_zoom |
|---|---|---|
| sido | 0 | 8 |
| sigungu | 5 | 11 |
| adm_dong | 8 | 14 |
