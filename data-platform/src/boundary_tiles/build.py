"""경계 타일 아티팩트 빌드 엔트리포인트.

경계(GeoJSON) 소스 하나 + 레벨(sido/sigungu/adm_dong) + 빈티지(boundary_vintage 날짜)를
받아 .pmtiles 를 만들고, 계약 형태의 인수인계 매니페스트를 `output/manifest/`
아래 레벨·빈티지별 파일로 커밋 대상에 등록한다.

산출물 필드는 shared/contracts/04_api_contract.yaml 의 `GET /basemap/regions/manifest`
응답 예시(ADR-001-map-tiles.md)를 그대로 따른다: `boundary_vintage`, `tile_url`,
`source_layer="regions"`, `feature_id_property="region_id"`, `minzoom`/`maxzoom`,
`attribution`, `available_vintages`. 계약은 shared/contracts/ 파일이지 다른 에이전트의
구현 코드가 아니므로, 다른 폴더의 코드가 이와 달라 보이더라도 여기서는 계약을 따른다.

이 모듈은 정적 아티팩트를 파일로 만드는 것까지만 한다. 만든 파일을 HTTP로
서빙하는 API는 여기 없다 — ADR-001: "C는 타일을 생성하지 않는다. A의 아티팩트를
가리키는 URL만 발급."(backend 몫). 오브젝트 스토리지/CDN 은 v1 배포 과제(ADR-002)라
`tile_url` 은 지금은 개발 정적 서빙 규약(`http://localhost:{PORT}/artifacts/...`)을
따른다 — 계약이 요구하는 절대 URL 형식은 개발에서도 지킨다. 배포 시점에
`--base-url` 하나만 바꾸면 된다.

동일 (level, boundary_vintage) 로 다시 빌드하면 항상 실패한다. 소스 데이터가
바뀌었으면 새 vintage(날짜)를 쓴다 — 과거 vintage의 파일은 절대 덮어쓰지 않는다.

ADR-005/D-20: `region_id` 는 조인 키로 properties 에 원문 문자열로 실린다.
빌드는 그 사실을 스스로 검증한다(`verify_feature_id_property`) — 광고한
`feature_id_property` 가 실제 타일에 없으면 예외를 던지고 빌드를 실패시킨다.
VF-003(테스트는 통과, 화면은 조용히 회색)이 같은 방식으로 다시 나는 것을 막는다.
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
from src.boundary_tiles.tiler import (
    build_tiles,
    collect_bounds,
    load_boundary_features,
    verify_feature_id_property,
)

SOURCE_LAYER = "regions"  # 04_api_contract.yaml 예시: 레벨과 무관하게 고정. 콘솔 스타일이
# level/vintage가 바뀌어도 source-layer 이름 하나로 참조할 수 있게 하기 위함.

FEATURE_ID_PROPERTY = "region_id"

# D-14 / ADR-002 결정 4. 레벨은 사용자가 UI 에서 고르고 줌으로 자동 전환되지 않으므로,
# 겹쳐도 무방하게 넉넉히 잡는다. adm_dong 은 ADR-001 의 5~12 를 14 로 확장(오버줌 여유).
LEVEL_ZOOM: dict[str, tuple[int, int]] = {
    "sido": (0, 10),
    "sigungu": (4, 12),
    "adm_dong": (5, 14),
}

# D-13 / ADR-002 결정 3: 레벨 산출 순서. sigungu 가 먼저인 이유는 픽스처·샘플·
# distribution_push 기본 objective 가 전부 이 레벨이기 때문. main() 의 --level
# choices 순서와 문서 목적으로만 쓰인다 — 강제하지는 않는다(개별 빌드는 레벨 하나씩).
LEVEL_BUILD_ORDER: tuple[str, ...] = ("sigungu", "adm_dong", "sido")

DEFAULT_ATTRIBUTION = "통계청 SGIS 연동 예정 (현재는 합성 표본 경계, is_synthetic_placeholder)"

# ADR-002: 오브젝트 스토리지/CDN 은 v1 배포 과제. 그때까지 개발 정적 서빙 규약을 쓴다.
# C 의 개발 서버가 data-platform/{output/tiles, fixtures}/ 를 이 prefix 로 정적 서빙한다.
DEV_ARTIFACT_BASE_URL = "http://localhost:8000/artifacts"


class VintageBuildError(ValueError):
    pass


def _validate_vintage(vintage: str) -> None:
    try:
        date.fromisoformat(vintage)
    except ValueError as e:
        raise VintageBuildError(f"vintage must be an ISO date (YYYY-MM-DD), got {vintage!r}") from e


def _load_features(source_geojson_path: Path) -> tuple[list, dict[str, int]]:
    with source_geojson_path.open("r", encoding="utf-8") as f:
        fc = json.load(f)
    region_ids = [feat["properties"]["region_id"] for feat in fc["features"]]
    id_map = build_id_map(region_ids)
    return load_boundary_features(fc, id_map), id_map


def _write_id_map(id_map_path: Path, id_map: dict[str, int]) -> None:
    """내부 디버깅용 산출물. 계약 매니페스트에는 실리지 않는다(ADR-005 결정 4)."""
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


def build_vintage(
    level: str,
    vintage: str,
    source_geojson_path: Path,
    output_root: Path,
    source_id: str,
    valid_to: str | None = None,
    attribution: str = DEFAULT_ATTRIBUTION,
    base_url: str = DEV_ARTIFACT_BASE_URL,
) -> dict:
    if level not in LEVEL_ZOOM:
        raise VintageBuildError(f"unknown level {level!r}, expected one of {sorted(LEVEL_ZOOM)}")
    _validate_vintage(vintage)

    tiles_root = output_root / "tiles"
    manifest_root = output_root / "manifest"
    # 파일명 규칙은 ADR-001-map-tiles.md 예시(regions-adm_dong-2026-01-01.pmtiles)를 그대로 따른다.
    stem = f"regions-{level}-{vintage}"
    pmtiles_path = tiles_root / f"{stem}.pmtiles"
    id_map_path = tiles_root / f"{stem}.id_map.json"
    tiles_manifest_path = tiles_root / "manifest.json"  # 내부 추적용(gitignore, output/tiles/ 아래)
    per_vintage_manifest_path = manifest_root / f"{stem}.json"  # 계약 인수인계물(git 추적)

    # 빈티지 불변성: manifest에 이미 있거나, 파일이 이미 디스크에 있으면 거부한다.
    tiles_manifest = load_manifest(tiles_manifest_path)
    if vintage_exists(tiles_manifest, level, vintage):
        raise VintageExistsError(f"level={level!r} boundary_vintage={vintage!r} already registered in manifest.json")
    if pmtiles_path.exists() or id_map_path.exists() or per_vintage_manifest_path.exists():
        raise VintageExistsError(f"level={level!r} boundary_vintage={vintage!r} artifact files already exist on disk")

    features, id_map = _load_features(source_geojson_path)
    minzoom, maxzoom = LEVEL_ZOOM[level]
    tiles = build_tiles(features, layer_name=SOURCE_LAYER, min_zoom=minzoom, max_zoom=maxzoom)
    bounds = collect_bounds(features)

    write_pmtiles(pmtiles_path, tiles, bounds, layer_name=SOURCE_LAYER, min_zoom=minzoom, max_zoom=maxzoom)

    # A-3 / ADR-005: 방금 쓴 파일을 다시 읽어 조인 키가 실제로 있는지 확인한다.
    # 여기서 예외가 나면 빌드는 실패한 것이고, 어떤 산출물도 매니페스트에 등록되지 않는다.
    verify_feature_id_property(pmtiles_path, FEATURE_ID_PROPERTY, tiles.keys())

    _write_id_map(id_map_path, id_map)

    sha256 = hashlib.sha256(pmtiles_path.read_bytes()).hexdigest()
    tile_url = f"{base_url}/tiles/{stem}.pmtiles"
    entry = {
        # --- shared/contracts/04_api_contract.yaml /basemap/regions/manifest 응답 예시와 동일한 필드 ---
        "level": level,
        "boundary_vintage": vintage,
        "tile_url": tile_url,
        "source_layer": SOURCE_LAYER,
        "feature_id_property": FEATURE_ID_PROPERTY,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "attribution": attribution,
        # available_vintages 는 manifest.append_entry 가 레벨 전체를 보고 채운다.
        # --- 계약엔 없지만 리니지/재현성/무결성 확인에 필요해 남기는 필드 ---
        # id_map_path 는 없다 — ADR-005 결정 4: 조인 키가 두 갈래가 되는 걸 막기 위해
        # 계약 산출물에서 뺐다. id_map.json 은 output/tiles/ 아래 내부 디버깅용으로만 남는다.
        "valid_to": valid_to,
        "feature_count": len(features),
        "bounds": list(bounds),
        "source_id": source_id,
        "sha256": sha256,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    append_entry(tiles_manifest_path, level, entry)  # available_vintages 를 entry 에 채워 넣는다(참조로 mutate)

    # 계약 인수인계물: output/manifest/regions-{level}-{vintage}.json — C 가 여기를 읽는다(D-13).
    manifest_root.mkdir(parents=True, exist_ok=True)
    with per_vintage_manifest_path.open("w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return entry


def build_fixture(
    level: str,
    source_geojson_path: Path,
    fixtures_root: Path,
    source_id: str,
    attribution: str = DEFAULT_ATTRIBUTION,
    base_url: str = DEV_ARTIFACT_BASE_URL,
) -> dict:
    """D-12 / ADR-002 결정 2: `boundary_vintage: "fixture"` 축소 픽스처를 만든다.

    `build_vintage` 와 같은 파이프라인(로드 -> 타일링 -> pmtiles 기록 -> **A-3 자체검증**)을
    타되, "fixture" 는 ISO 날짜가 아니므로 vintage 불변성 추적(append-only manifest)
    대상이 아니다 — 별도로 `fixtures/manifest-fixture.json` 하나만 남긴다.
    """
    if level not in LEVEL_ZOOM:
        raise VintageBuildError(f"unknown level {level!r}, expected one of {sorted(LEVEL_ZOOM)}")

    vintage = "fixture"
    stem = f"regions-{level}-{vintage}"
    pmtiles_path = fixtures_root / f"{stem}.pmtiles"
    manifest_path = fixtures_root / "manifest-fixture.json"

    if pmtiles_path.exists():
        raise VintageBuildError(f"fixture already exists on disk: {pmtiles_path}")

    features, _id_map = _load_features(source_geojson_path)
    minzoom, maxzoom = LEVEL_ZOOM[level]
    tiles = build_tiles(features, layer_name=SOURCE_LAYER, min_zoom=minzoom, max_zoom=maxzoom)
    bounds = collect_bounds(features)

    write_pmtiles(pmtiles_path, tiles, bounds, layer_name=SOURCE_LAYER, min_zoom=minzoom, max_zoom=maxzoom)
    verify_feature_id_property(pmtiles_path, FEATURE_ID_PROPERTY, tiles.keys())

    entry = {
        "level": level,
        "boundary_vintage": vintage,
        "tile_url": f"{base_url}/{stem}.pmtiles",
        "source_layer": SOURCE_LAYER,
        "feature_id_property": FEATURE_ID_PROPERTY,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "attribution": attribution,
        "available_vintages": [vintage],
        "feature_count": len(features),
        "bounds": list(bounds),
        "source_id": source_id,
        "sha256": hashlib.sha256(pmtiles_path.read_bytes()).hexdigest(),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    fixtures_root.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
        f.write("\n")

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
    parser.add_argument("--base-url", default=DEV_ARTIFACT_BASE_URL)
    args = parser.parse_args()

    entry = build_vintage(
        level=args.level,
        vintage=args.vintage,
        source_geojson_path=args.source,
        output_root=args.output_root,
        source_id=args.source_id,
        valid_to=args.valid_to,
        attribution=args.attribution,
        base_url=args.base_url,
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 기본 코드페이지가 한글 CLI 출력을 깨는 것 방지
    print(json.dumps(entry, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
