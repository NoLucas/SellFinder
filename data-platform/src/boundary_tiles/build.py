"""경계 타일 아티팩트 빌드 엔트리포인트.

경계(GeoJSON) 소스 하나 + 레벨(sido/sigungu/adm_dong) + 빈티지(valid_from 날짜)를
받아 .pmtiles + id_map.json 을 만들고 manifest.json 에 등록한다.

이 모듈은 정적 아티팩트를 파일로 만드는 것까지만 한다. 만든 파일을 HTTP로
서빙하는 API는 여기 없다 — 그건 A(data-platform)의 책임 밖이다(브리프 지시사항).

동일 (level, vintage) 로 다시 빌드하면 항상 실패한다. 소스 데이터가 바뀌었으면
새 vintage(날짜)를 쓴다 — 과거 vintage의 파일은 덮어쓰지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from src.boundary_tiles.feature_id import build_id_map
from src.boundary_tiles.manifest import VintageExistsError, append_entry, load_manifest, vintage_exists
from src.boundary_tiles.pmtiles_writer import write_pmtiles
from src.boundary_tiles.tiler import build_tiles, collect_bounds, load_boundary_features

LEVEL_ZOOM: dict[str, tuple[int, int]] = {
    # (min_zoom, max_zoom) — 03_region_features.json region_hierarchy 의 용도에 맞춘 대략치.
    # census_block / h3_r8 / custom_catchment 는 v1 범위 밖(00_product_spec.md §6).
    "sido": (0, 8),
    "sigungu": (5, 11),
    "adm_dong": (8, 14),
}


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
) -> dict:
    if level not in LEVEL_ZOOM:
        raise VintageBuildError(f"unknown level {level!r}, expected one of {sorted(LEVEL_ZOOM)}")
    _validate_vintage(vintage)

    tiles_root = output_root / "tiles"
    level_dir = tiles_root / level
    pmtiles_path = level_dir / f"{vintage}.pmtiles"
    id_map_path = level_dir / f"{vintage}.id_map.json"
    manifest_path = tiles_root / "manifest.json"

    # 빈티지 불변성: manifest에 이미 있거나, 파일이 이미 디스크에 있으면 거부한다.
    manifest = load_manifest(manifest_path)
    if vintage_exists(manifest, level, vintage):
        raise VintageExistsError(f"level={level!r} vintage={vintage!r} already registered in manifest.json")
    if pmtiles_path.exists() or id_map_path.exists():
        raise VintageExistsError(f"level={level!r} vintage={vintage!r} artifact files already exist on disk")

    with source_geojson_path.open("r", encoding="utf-8") as f:
        fc = json.load(f)

    region_ids = [feat["properties"]["region_id"] for feat in fc["features"]]
    id_map = build_id_map(region_ids)

    features = load_boundary_features(fc, id_map)
    min_zoom, max_zoom = LEVEL_ZOOM[level]
    tiles = build_tiles(features, layer_name=level, min_zoom=min_zoom, max_zoom=max_zoom)
    bounds = collect_bounds(features)

    write_pmtiles(pmtiles_path, tiles, bounds, layer_name=level, min_zoom=min_zoom, max_zoom=max_zoom)

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
        "vintage": vintage,
        "valid_from": vintage,
        "valid_to": valid_to,
        "pmtiles_path": str(pmtiles_path.relative_to(output_root).as_posix()),
        "id_map_path": str(id_map_path.relative_to(output_root).as_posix()),
        "feature_count": len(features),
        "min_zoom": min_zoom,
        "max_zoom": max_zoom,
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
    parser.add_argument("--vintage", required=True, help="ISO date, e.g. 2026-01-01 (= valid_from)")
    parser.add_argument("--valid-to", default=None)
    parser.add_argument("--source", required=True, type=Path, help="GeoJSON FeatureCollection path")
    parser.add_argument("--source-id", required=True, help="data_source.source_id per shared/contracts")
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[2] / "output")
    args = parser.parse_args()

    entry = build_vintage(
        level=args.level,
        vintage=args.vintage,
        source_geojson_path=args.source,
        output_root=args.output_root,
        source_id=args.source_id,
        valid_to=args.valid_to,
    )
    print(json.dumps(entry, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
