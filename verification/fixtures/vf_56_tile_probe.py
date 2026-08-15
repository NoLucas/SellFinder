"""VF 5.6b - decode A's REAL .pmtiles artifact and report what D's
setFeatureState join key would actually have to match.
Contract: 04_api_contract.yaml v0.2.1 feature_id_property, ADR-001."""
import gzip, json, os, sys
from pathlib import Path
from pmtiles.reader import Reader, MmapSource
import mapbox_vector_tile

R = Path(__file__).resolve().parents[2]
tile_dir = R / "data-platform" / "output" / "tiles"

for pm in sorted(tile_dir.glob("*.pmtiles")):
    print(f"\n=== {pm.name} ===")
    with open(pm, "rb") as f:
        rdr = Reader(MmapSource(f))
        hdr = rdr.header()
        minz, maxz = hdr["min_zoom"], hdr["max_zoom"]
        print(f"  zoom range in header: {minz}..{maxz}")
        found = False
        for z in range(minz, maxz + 1):
            for x in range(2 ** z):
                for y in range(2 ** z):
                    try:
                        raw = rdr.get(z, x, y)
                    except Exception:
                        raw = None
                    if not raw:
                        continue
                    data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
                    dec = mapbox_vector_tile.decode(data)
                    for layer, content in dec.items():
                        feats = content["features"]
                        print(f"  tile z{z}/{x}/{y} layer={layer!r} features={len(feats)}")
                        for ft in feats[:3]:
                            print(f"     feature id = {ft.get('id')!r}  (type {type(ft.get('id')).__name__})")
                            print(f"     properties = {ft.get('properties')}")
                            print(f"     'region_id' in properties? -> {'region_id' in (ft.get('properties') or {})}")
                        found = True
                    if found:
                        break
                if found:
                    break
            if found:
                break
