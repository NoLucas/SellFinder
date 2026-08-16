"""Dump A's real tile features to JSON so the JS join harness can consume them.

2회차 갱신: 통합 경로가 sido 산출물이 아니라 D-12 sigungu 픽스처로 바뀌었으므로
(DISPATCH.md A-4, orchestrator 지시) 픽스처 타일을 덤프 대상으로 삼는다.
sido 산출물을 다시 봐야 할 경우를 위해 --source sido 로 되돌릴 수 있게 남겨둔다.
"""
import argparse
import gzip
import json
from pathlib import Path

from pmtiles.reader import Reader, MmapSource
import mapbox_vector_tile

R = Path(__file__).resolve().parents[2]

SOURCES = {
    "fixture": R / "data-platform" / "fixtures" / "regions-sigungu-fixture.pmtiles",
    "sido": R / "data-platform" / "output" / "tiles" / "regions-sido-2026-01-01.pmtiles",
}

ap = argparse.ArgumentParser()
ap.add_argument("--source", choices=SOURCES.keys(), default="fixture")
args = ap.parse_args()

pm = SOURCES[args.source]
out = []
seen_ids = set()

with open(pm, "rb") as f:
    rdr = Reader(MmapSource(f))
    hdr = rdr.header()
    minz, maxz = hdr["min_zoom"], hdr["max_zoom"]
    for z in range(minz, maxz + 1):
        found_any_at_z = False
        for x in range(2 ** z):
            for y in range(2 ** z):
                try:
                    raw = rdr.get(z, x, y)
                except Exception:
                    raw = None
                if not raw:
                    continue
                found_any_at_z = True
                data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
                for layer, content in mapbox_vector_tile.decode(data).items():
                    for ft in content["features"]:
                        fid = ft.get("id")
                        key = (layer, fid)
                        if key in seen_ids:
                            continue
                        seen_ids.add(key)
                        out.append({"layer": layer, "id": fid, "properties": ft.get("properties")})
        if found_any_at_z:
            print(f"  z{z}: scanned, {len(out)} unique features so far")
            break  # lowest populated zoom is enough — same features repeat at deeper zooms

p = Path(__file__).parent / "a_tile_features.json"
p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"source={args.source} ({pm.name}) -> wrote {len(out)} features -> {p.name}")
