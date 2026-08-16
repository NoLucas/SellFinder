"""Read-only loader for shared/contracts/*.

Never write to these files. This module only extracts the pieces the
synthetic generator needs: the region_feature registry (03) and the
product taxonomy + channels (02). Keeping this as a loader (instead of
hardcoding a copy of the registry) means the generator can't silently
drift from the contract - if jin changes the contract, this reflects it
on the next run.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "shared" / "contracts"

# tenant_scoped features are per-tenant by contract ($warning in
# 03_region_features.json) and must never appear in the shared
# region_feature store this generator produces.
_EXCLUDED_FEATURE_CATEGORIES = {"tenant_scoped"}


def _load_json(name: str) -> dict[str, Any]:
    path = CONTRACTS_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_feature_registry() -> dict[str, dict[str, Any]]:
    """Flatten 03_region_features.json's feature_registry into {feature_key: meta}.

    meta gets an extra "_category" field (population/income_spend/...) so
    generators can group related features.
    """
    doc = _load_json("03_region_features.json")
    registry = doc["feature_registry"]
    flat: dict[str, dict[str, Any]] = {}
    for category, keys in registry.items():
        if category.startswith("$") or category in _EXCLUDED_FEATURE_CATEGORIES:
            continue
        for key, meta in keys.items():
            if key.startswith("$"):
                continue
            flat[key] = {**meta, "_category": category}
    return flat


def load_tenant_scoped_feature_keys() -> set[str]:
    """Return the raw key set under 03_region_features.json's `tenant_scoped`
    category - the features load_feature_registry() excludes. Exists so
    tests can assert "none of these ever leak into the shared store" by
    reading the contract instead of hardcoding a copy of the key list,
    which would silently stop catching a leak the moment jin adds a new
    tenant_scoped key to the contract without anyone updating the test.
    """
    doc = _load_json("03_region_features.json")
    tenant_scoped = doc["feature_registry"]["tenant_scoped"]
    return {key for key in tenant_scoped if not key.startswith("$")}


def load_taxonomy() -> dict[str, Any]:
    """Return the raw 02_taxonomy.json document (channels + taxonomy tree)."""
    return _load_json("02_taxonomy.json")


def flatten_taxonomy_leaves(taxonomy_doc: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Flatten the taxonomy tree into leaf nodes only (deepest nodes per branch).

    A "leaf" here is any node with no children key, matching how
    classification_contract expects node_id references: 02_taxonomy.json
    says level-2 nodes are only acceptable when no level-3 children exist.
    """
    doc = taxonomy_doc or load_taxonomy()
    leaves: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], parent_id: str | None) -> None:
        children = node.get("children")
        record = {k: v for k, v in node.items() if k != "children"}
        record["parent_id"] = parent_id
        if children:
            for child in children:
                walk(child, node["node_id"])
        else:
            leaves.append(record)

    for top in doc["taxonomy"]:
        walk(top, None)
    return leaves


def channels() -> dict[str, Any]:
    return load_taxonomy()["channels"]
