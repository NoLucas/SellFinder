"""manifest.json 읽기/추가.

필드는 shared/contracts/04_api_contract.yaml 의 `GET /basemap/regions/manifest`
응답 예시(ADR-001-map-tiles.md)와 맞춘다 — 그래야 backend가 이 파일을 거의 그대로
읽어 응답을 만들 수 있다. 레벨 안에서 동일 vintage 항목은 절대 다시 쓰지 않는다
(append-only). 다만 `available_vintages` 는 "이 레벨에 지금 존재하는 전체 빈티지
목록"이라는 성격상, 새 빈티지가 추가될 때마다 같은 레벨의 기존 항목들에서도 함께
갱신된다 — 빈티지 자체(그 vintage가 가리키는 타일 내용·통계)는 절대 바뀌지 않지만,
"현재 몇 개가 있는지"를 보여주는 이 목록만은 최신 상태를 반영해야 하기 때문이다.
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
    return vintage in manifest.get("levels", {}).get(level, {}).get("vintages", {})


def _write_atomic(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)


def append_entry(path: Path, level: str, entry: dict) -> None:
    """entry 는 04_api_contract.yaml 의 manifest 응답 예시 필드를 갖춰야 한다:
    level, boundary_vintage, tile_url, source_layer, feature_id_property,
    minzoom, maxzoom, attribution. available_vintages 는 여기서 계산해 채운다.
    """
    manifest = load_manifest(path)
    level_entry = manifest.setdefault("levels", {}).setdefault(level, {"vintages": {}})
    vintages = level_entry["vintages"]

    vintage = entry["boundary_vintage"]
    if vintage in vintages:
        raise VintageExistsError(
            f"level={level!r} boundary_vintage={vintage!r} already exists in manifest — "
            "vintages are immutable, use a new vintage date instead"
        )

    vintages[vintage] = entry

    all_vintages = sorted(vintages.keys())
    for v_entry in vintages.values():
        v_entry["available_vintages"] = all_vintages
    level_entry["latest_vintage"] = all_vintages[-1]

    _write_atomic(path, manifest)
