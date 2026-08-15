"""manifest.json 읽기/추가.

manifest는 append-only다: 레벨(level) 안에서 동일 vintage 항목을 다시 쓰지 않는다.
콘솔/백엔드는 이 파일 하나만 보고 "이 레벨에 어떤 빈티지들이 있고 각각 어디서
.pmtiles/id_map.json을 받아오는지"를 알 수 있어야 한다.
"""
from __future__ import annotations

import json
from pathlib import Path


class VintageExistsError(ValueError):
    pass


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"levels": {}}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def vintage_exists(manifest: dict, level: str, vintage: str) -> bool:
    return any(entry["vintage"] == vintage for entry in manifest.get("levels", {}).get(level, []))


def append_entry(path: Path, level: str, entry: dict) -> None:
    manifest = load_manifest(path)
    manifest.setdefault("levels", {}).setdefault(level, [])

    if vintage_exists(manifest, level, entry["vintage"]):
        raise VintageExistsError(
            f"level={level!r} vintage={entry['vintage']!r} already exists in manifest — "
            "vintages are immutable, use a new vintage date instead"
        )

    manifest["levels"][level].append(entry)
    manifest["levels"][level].sort(key=lambda e: e["vintage"])

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)
