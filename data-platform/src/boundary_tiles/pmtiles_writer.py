"""{(z,x,y): gzip(mvt bytes)} 딕셔너리를 .pmtiles 아카이브 파일로 직렬화한다."""
from __future__ import annotations

from pathlib import Path

from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer


def write_pmtiles(
    path: Path,
    tiles: dict[tuple[int, int, int], bytes],
    bounds: tuple[float, float, float, float],
    layer_name: str,
    min_zoom: int,
    max_zoom: int,
) -> None:
    if not tiles:
        raise ValueError("no tiles to write")

    west, south, east, north = bounds
    header = {
        "tile_type": TileType.MVT,
        "tile_compression": Compression.GZIP,
        "min_lon_e7": int(west * 1e7),
        "min_lat_e7": int(south * 1e7),
        "max_lon_e7": int(east * 1e7),
        "max_lat_e7": int(north * 1e7),
        "center_zoom": min_zoom,
        "center_lon_e7": int((west + east) / 2 * 1e7),
        "center_lat_e7": int((south + north) / 2 * 1e7),
    }
    metadata = {
        "name": layer_name,
        "vector_layers": [{"id": layer_name, "fields": {}}],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("wb") as f:
        writer = Writer(f)
        for (z, x, y), tile_bytes in sorted(tiles.items(), key=lambda kv: zxy_to_tileid(*kv[0])):
            writer.write_tile(zxy_to_tileid(z, x, y), tile_bytes)
        writer.finalize(header, metadata)
    tmp_path.replace(path)
