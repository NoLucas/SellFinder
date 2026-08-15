"""경계 타일 아티팩트 빌드 엔트리포인트.

경계(GeoJSON) 소스 하나 + 레벨(sido/sigungu/adm_dong) + 빈티지(boundary_vintage 날짜)를
받아 .pmtiles + id_map.json 을 만들고 manifest.json 에 등록한다.

산출물 필드는 shared/contracts/04_api_contract.yaml 의 `GET /basemap/regions/manifest`
응답 예시(ADR-001-map-tiles.md)를 그대로 따른다: `boundary_vintage`, `tile_url`,
`source_layer="regions"`, `feature_id_property="region_id"`, `minzoom`/`maxzoom`,
`attribution`, `available_vintages`. 계약은 shared/contracts/ 파일이지 다른 에이전트의
구현 코드가 아니므로, 다른 폴더의 코드가 이와 달라 보이더라도 여기서는 계약을 따른다.

이 모듈은 정적 아티팩트를 파일로 만드는 것까지만 한다. 만든 파일을 HTTP로
서빙하는 API는 여기 없다 — ADR-001: "C는 타일을 생성하지 않는다. A의 아티팩트를
가리키는 URL만 발급."(backend 몫). `tile_url`은 여기서는 리포지토리 상대경로이며,
실제 CDN/오브젝트 스토리지 URL로 바꾸는 건 이 아티팩트를 배포하는 쪽의 몫이다.

동일 (level, boundary_vintage) 로 다시 빌드하면 항상 실패한다. 소스 데이터가
바뀌었으면 새 vintage(날짜)를 쓴다 — 과거 vintage의 파일은 절대 덮어쓰지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from src.boundary_tiles.feature_id import build_id_map
from src.boundary_tiles.manifest import VintageExistsError, append_entry, load_manifest, vintage_exists
from src.boundary_tiles.pmtiles_writer import write_pmtiles
from src.boundary_tiles.tiler import build_tiles, collect_bounds, load_boundary_features

SOURCE_LAYER = "regions"  # 04_api_contract.yaml 예시: 레벨과 무관하게 고정. 콘솔 스타일이
# level/vintage가 바뀌어도 source-layer 이름 하나로 참조할 수 있게 하기 위함.

LEVEL_ZOOM: dict[str, tuple[int, int]] = {
    # (minzoom, maxzoom). adm_dong은 04_api_contract.yaml 예시(5, 12)와 동일하게 맞췄다.
    # sido/sigungu는 예시가 없어 03_region_features.json region_hierarchy 용도에 맞춘 대략치.
    # census_block / h3_r8 / custom_catchment 는 v1 범위 밖(00_product_spec.md §6) — custom_catchment는
    # ADR-001에 따라 애초에 타일이 아니라 scores 응답에 GeoJSON 인라인이라 이 파이프라인 대상이 아니다.
    "sido": (0, 8),
    "sigungu": (5, 11),
    "adm_dong": (5, 12),
}

DEFAULT_ATTRIBUTION = "통계청 SGIS 연동 예정 (현재는 합성 표본 경계, is_synthetic_placeholder)"


class VintageBuildError(ValueError):
    pass


def _validate_vintage(vintage: str) -> None:
    try:
        date.fromisoformat(vintage)
    except ValueError as e:
        raise VintageBuildError(f"vintage must be an ISO date (YYYY-MM-DD), got {vintage!r}") from e


def build_vintage(
    level: str,
    vintage: str,
    source_geojson_path: Path,
    output_root: Path,
    source_id: str,
    valid_to: str | None = None,
    attribution: str = DEFAULT_ATTRIBUTION,
) -> dict:
    if level not in LEVEL_ZOOM:
        raise VintageBuildError(f"unknown level {level!r}, expected one of {sorted(LEVEL_ZOOM)}")
    _validate_vintage(vintage)

    tiles_root = output_root / "tiles"
    # 파일명 규칙은 ADR-001-map-tiles.md 예시(regions-adm_dong-2026-01-01.pmtiles)를 그대로 따른다.
    stem = f"regions-{level}-{vintage}"
    pmtiles_path = tiles_root / f"{stem}.pmtiles"
    id_map_path = tiles_root / f"{stem}.id_map.json"
    manifest_path = tiles_root / "manifest.json"

    # 빈티지 불변성: manifest에 이미 있거나, 파일이 이미 디스크에 있으면 거부한다.
    manifest = load_manifest(manifest_path)
    if vintage_exists(manifest, level, vintage):
        raise VintageExistsError(f"level={level!r} boundary_vintage={vintage!r} already registered in manifest.json")
    if pmtiles_path.exists() or id_map_path.exists():
        raise VintageExistsError(f"level={level!r} boundary_vintage={vintage!r} artifact files already exist on disk")

    with source_geojson_path.open("r", encoding="utf-8") as f:
        fc = json.load(f)

    region_ids = [feat["properties"]["region_id"] for feat in fc["features"]]
    id_map = build_id_map(region_ids)

    features = load_boundary_features(fc, id_map)
    minzoom, maxzoom = LEVEL_ZOOM[level]
    tiles = build_tiles(features, layer_name=SOURCE_LAYER, min_zoom=minzoom, max_zoom=maxzoom)
    bounds = collect_bounds(features)

    write_pmtiles(pmtiles_path, tiles, bounds, layer_name=SOURCE_LAYER, min_zoom=minzoom, max_zoom=maxzoom)

    id_map_path.parent.mkdir(parents=True, exist_ok=True)
    with id_map_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "region_id_to_feature_id": id_map,
                "feature_id_to_region_id": {v: k for k, v in id_map.items()},
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")

    sha256 = hashlib.sha256(pmtiles_path.read_bytes()).hexdigest()
    entry = {
        # --- shared/contracts/04_api_contract.yaml /basemap/regions/manifest 응답 예시와 동일한 필드 ---
        "level": level,
        "boundary_vintage": vintage,
        "tile_url": str(pmtiles_path.relative_to(output_root).as_posix()),
        "source_layer": SOURCE_LAYER,
        "feature_id_property": "region_id",
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "attribution": attribution,
        # available_vintages 는 manifest.append_entry 가 레벨 전체를 보고 채운다.
        # --- 계약엔 없지만 리니지/재현성/무결성 확인에 필요해 남기는 필드 ---
        "valid_to": valid_to,
        "id_map_path": str(id_map_path.relative_to(output_root).as_posix()),
        "feature_count": len(features),
        "bounds": list(bounds),
        "source_id": source_id,
        "sha256": sha256,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    append_entry(manifest_path, level, entry)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", required=True, choices=sorted(LEVEL_ZOOM))
    parser.add_argument("--vintage", required=True, help="ISO date, e.g. 2026-01-01 (= boundary_vintage)")
    parser.add_argument("--valid-to", default=None)
    parser.add_argument("--source", required=True, type=Path, help="GeoJSON FeatureCollection path")
    parser.add_argument("--source-id", required=True, help="data_source.source_id per shared/contracts")
    parser.add_argument("--attribution", default=DEFAULT_ATTRIBUTION)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[2] / "output")
    args = parser.parse_args()

    entry = build_vintage(
        level=args.level,
        vintage=args.vintage,
        source_geojson_path=args.source,
        output_root=args.output_root,
        source_id=args.source_id,
        valid_to=args.valid_to,
        attribution=args.attribution,
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 기본 코드페이지가 한글 CLI 출력을 깨는 것 방지
    print(json.dumps(entry, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
