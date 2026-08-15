"""Dump A's real tile features to JSON so the JS join harness can consume them."""
import gzip, json
from pathlib import Path
from pmtiles.reader import Reader, MmapSource
import mapbox_vector_tile

R = Path(__file__).resolve().parents[2]
pm = R / "data-platform" / "output" / "tiles" / "regions-sido-2026-01-01.pmtiles"
out = []
with open(pm, "rb") as f:
    rdr = Reader(MmapSource(f))
    raw = rdr.get(0, 0, 0)
    data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
    for layer, content in mapbox_vector_tile.decode(data).items():
        for ft in content["features"]:
            out.append({"layer": layer, "id": ft.get("id"), "properties": ft.get("properties")})
p = Path(__file__).parent / "a_tile_features.json"
p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {len(out)} features -> {p.name}")
