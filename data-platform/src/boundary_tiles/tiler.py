"""GeoJSON 지역 경계 -> MVT(z/x/y) 타일 바이트 생성.

지원 대상 도형은 Polygon/MultiPolygon(지역 경계)뿐이다. 좌표계는 입력 GeoJSON이
표준대로 WGS84(EPSG:4326)라고 가정하고, 웹 메르카토르(EPSG:3857)로 투영한 뒤
타일 경계와 교차시켜 타일별 조각을 만든다 — MapLibre 등 표준 슬리피맵 클라이언트가
기대하는 좌표계다.

알려진 한계: tippecanoe류 도구가 하는 줌별 지오메트리 단순화/일반화는 하지 않는다.
지금은 파이프라인 정합성(경계->타일->feature id 왕복)을 검증하는 단계이고, 실제
경계 소스(예: 통계청 SGIS) 연동 시점에 단순화를 추가해야 한다.
"""
from __future__ import annotations

import gzip
from dataclasses import dataclass

import mapbox_vector_tile
import mercantile
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.validation import make_valid

_POLYGONAL = {"Polygon", "MultiPolygon"}


@dataclass(frozen=True)
class BoundaryFeature:
    region_id: str
    feature_id: int
    properties: dict
    geometry: BaseGeometry  # lon/lat (EPSG:4326)


def _to_mercator(geom: BaseGeometry) -> BaseGeometry:
    return transform(lambda lon, lat: mercantile.xy(lon, lat), geom)


def _polygonal_only(geom: BaseGeometry) -> BaseGeometry | None:
    """intersection 결과에서 점/선 부스러기를 버리고 면(polygon)만 남긴다."""
    if geom.is_empty:
        return None
    if geom.geom_type in _POLYGONAL:
        return geom
    if geom.geom_type == "GeometryCollection":
        parts = [g for g in geom.geoms if g.geom_type in _POLYGONAL and not g.is_empty]
        if not parts:
            return None
        return unary_union(parts)
    return None


def load_boundary_features(feature_collection: dict, id_map: dict[str, int]) -> list[BoundaryFeature]:
    """GeoJSON FeatureCollection(EPSG:4326)을 BoundaryFeature 리스트로 변환한다.

    각 feature.properties 는 최소 region_id 를 가져야 한다. 변환 결과의
    properties 에도 region_id 를 **문자열 원문 그대로** 유지한다 — ADR-005/D-20:
    `feature_id_property`("region_id")가 유일한 조인 키이고, D 는 이 속성을
    `promoteId` 로 읽는다. 네이티브 MVT feature id(정수, id_map 경유)는 계속
    함께 싣지만 툴 호환/디버깅용일 뿐 어떤 소비자도 여기에 의존하지 않는다.
    """
    out: list[BoundaryFeature] = []
    for feat in feature_collection["features"]:
        props = dict(feat["properties"])
        region_id = props["region_id"]
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = make_valid(geom)
        if geom.geom_type not in _POLYGONAL:
            raise ValueError(f"region_id={region_id!r}: polygonal geometry expected, got {geom.geom_type}")
        out.append(
            BoundaryFeature(
                region_id=region_id,
                feature_id=id_map[region_id],
                properties=props,
                geometry=geom,
            )
        )
    return out


def build_tiles(
    features: list[BoundaryFeature],
    layer_name: str,
    min_zoom: int,
    max_zoom: int,
    extents: int = 4096,
) -> dict[tuple[int, int, int], bytes]:
    """레벨 하나(예: sido)의 전체 지역 경계로부터 {(z,x,y): gzip(mvt_bytes)} 를 만든다.

    타일 후보 x 피처 전수에 대해 shapely `.intersection()`(정확 기하 연산)을 매번
    돌리면 adm_dong(zoom 5~14, 전국 bbox)처럼 고줌·다피처 조합에서 타일 후보 수가
    수만~수십만으로 뛰어 비현실적으로 느려진다. 실제로 겹칠 여지가 없는 조합은
    바운딩박스 비교(수치 비교 4회, O(1))로 먼저 걸러내고, 겹칠 가능성이 있는
    조합에만 정확 연산을 돌린다 — 결과는 동일하고 속도만 다르다.
    """
    merc_features = [(f, _to_mercator(f.geometry)) for f in features]
    merc_features_with_bounds = [(f, mg, mg.bounds) for f, mg in merc_features]

    west = min(f.geometry.bounds[0] for f in features)
    south = min(f.geometry.bounds[1] for f in features)
    east = max(f.geometry.bounds[2] for f in features)
    north = max(f.geometry.bounds[3] for f in features)

    tiles: dict[tuple[int, int, int], bytes] = {}
    for zoom in range(min_zoom, max_zoom + 1):
        for t in mercantile.tiles(west, south, east, north, [zoom]):
            tb = mercantile.xy_bounds(t)
            tile_box = box(tb.left, tb.bottom, tb.right, tb.top)

            layer_features = []
            for f, merc_geom, (fminx, fminy, fmaxx, fmaxy) in merc_features_with_bounds:
                if fmaxx < tb.left or fminx > tb.right or fmaxy < tb.bottom or fminy > tb.top:
                    continue  # 바운딩박스가 안 겹치면 정확 교차 연산 자체를 건너뛴다
                clipped = _polygonal_only(merc_geom.intersection(tile_box))
                if clipped is None:
                    continue
                layer_features.append(
                    {
                        "geometry": mapping(clipped),
                        "properties": f.properties,
                        "id": f.feature_id,
                    }
                )

            if not layer_features:
                continue

            mvt_bytes = mapbox_vector_tile.encode(
                {"name": layer_name, "features": layer_features},
                default_options={
                    "quantize_bounds": (tb.left, tb.bottom, tb.right, tb.top),
                    "extents": extents,
                },
            )
            tiles[(zoom, t.x, t.y)] = gzip.compress(mvt_bytes)

    return tiles


class TileJoinKeyVerificationError(ValueError):
    """A-3 / ADR-005: 광고한 feature_id_property 가 실제 산출 타일에 없다.

    VF-003 이 이 상태(테스트는 전부 통과, 화면만 조용히 회색)로 발생했다.
    이 검사가 빌드 파이프라인 안에 있어야 같은 실패가 A 의 스위트 안에서 잡힌다.
    """


def verify_feature_id_property(
    pmtiles_path,
    feature_id_property: str,
    tile_keys,
) -> None:
    """방금 쓴 .pmtiles 를 다시 읽어, 실제 피처 속성에 조인 키가 있는지 확인한다.

    `tile_keys` 는 이번 빌드가 실제로 쓴 (z,x,y) 목록이다 (전세계 그리드를
    다시 스캔하지 않는다 — 고줌에서는 그 자체로 수백만 타일이라 비현실적이다).
    빌드가 만든 타일 전부를 열어, 하나라도 `feature_id_property` 가 없는
    피처가 있으면 즉시 빌드를 실패시킨다.
    """
    import gzip

    import mapbox_vector_tile
    from pmtiles.reader import MmapSource, Reader

    checked_any = False
    with open(pmtiles_path, "rb") as f:
        reader = Reader(MmapSource(f))
        for z, x, y in tile_keys:
            raw = reader.get(z, x, y)
            if not raw:
                continue
            data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
            decoded = mapbox_vector_tile.decode(data)
            for _layer_name, layer in decoded.items():
                for feat in layer["features"]:
                    checked_any = True
                    if feature_id_property not in (feat.get("properties") or {}):
                        raise TileJoinKeyVerificationError(
                            f"feature_id_property={feature_id_property!r} 가 산출 타일 "
                            f"z{z}/{x}/{y} 의 피처 properties 에 없습니다: "
                            f"{list((feat.get('properties') or {}).keys())}"
                        )
    if not checked_any:
        raise TileJoinKeyVerificationError("검증 대상 피처를 하나도 찾지 못했습니다 (빈 타일셋).")


def collect_bounds(features: list[BoundaryFeature]) -> tuple[float, float, float, float]:
    west = min(f.geometry.bounds[0] for f in features)
    south = min(f.geometry.bounds[1] for f in features)
    east = max(f.geometry.bounds[2] for f in features)
    north = max(f.geometry.bounds[3] for f in features)
    return (west, south, east, north)
