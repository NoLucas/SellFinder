"""02_taxonomy.json 의 sbiz_codes 를 1차 조인 키로 해석한다 (ADR-004 / D-18).

매핑이 노드 자신에 없으면 조상 체인을 따라 상속을 시도하고, 그래도 없으면
`None` 을 반환한다 — 이 경우 호출자는 그 노드에 대해 절대 값을 지어내면 안 되고
(D-19), `02_taxonomy.json`의 `public_data_mapping_note`가 명시한 대로
"상속도 없으면 demand_signal 을 만들 수 없다"를 그대로 따른다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONTRACTS_ROOT = Path(__file__).resolve().parents[3] / "shared" / "contracts"
TAXONOMY_PATH = CONTRACTS_ROOT / "02_taxonomy.json"


@dataclass(frozen=True)
class LeafMapping:
    node_id: str
    level: int
    sbiz_codes: tuple[str, ...] | None
    resolution: str  # "direct" | "inherited" | "none"
    resolved_from: str | None  # sbiz_codes 를 실제로 가진 node_id (self 또는 조상)


def load_taxonomy(path: Path = TAXONOMY_PATH) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_leaf_chains(nodes: list[dict], ancestors: tuple[dict, ...] = ()):
    """(leaf_node, [self, ..., root] 순서의 조상 체인 포함 자기 자신) 을 yield 한다."""
    for node in nodes:
        chain = ancestors + (node,)
        children = node.get("children")
        if children:
            yield from _iter_leaf_chains(children, chain)
        else:
            yield node, chain


def resolve_sbiz_codes(chain: tuple[dict, ...]) -> tuple[list[str] | None, str, str | None]:
    """chain 은 (조상..., 자기자신) 순서. self 부터 뒤에서부터(가까운 조상부터) 찾는다."""
    for depth, node in enumerate(reversed(chain)):
        codes = node.get("sbiz_codes")
        if codes:
            resolution = "direct" if depth == 0 else "inherited"
            return list(codes), resolution, node["node_id"]
    return None, "none", None


def leaf_mappings(taxonomy: dict) -> list[LeafMapping]:
    """전체 리프 노드에 대해 sbiz_codes 해석 결과를 계산한다.

    ADR-004 "A 가 할 일" #2: sbiz_codes 가 비어 있는 노드 목록을 뽑아 보고하는 것이
    바로 이 함수의 출력이다.
    """
    out: list[LeafMapping] = []
    for leaf, chain in _iter_leaf_chains(taxonomy["taxonomy"]):
        codes, resolution, resolved_from = resolve_sbiz_codes(chain)
        out.append(
            LeafMapping(
                node_id=leaf["node_id"],
                level=leaf["level"],
                sbiz_codes=tuple(codes) if codes else None,
                resolution=resolution,
                resolved_from=resolved_from,
            )
        )
    return out


def coverage_report(taxonomy: dict) -> dict:
    """A 가 ADR-004 에 따라 매번 보고해야 하는 커버리지 요약."""
    mappings = leaf_mappings(taxonomy)
    by_resolution: dict[str, list[str]] = {"direct": [], "inherited": [], "none": []}
    for m in mappings:
        by_resolution[m.resolution].append(m.node_id)
    return {
        "total_leaf_nodes": len(mappings),
        "direct": by_resolution["direct"],
        "inherited": by_resolution["inherited"],
        "none": by_resolution["none"],
        "mappable_count": len(by_resolution["direct"]) + len(by_resolution["inherited"]),
        "unmappable_count": len(by_resolution["none"]),
    }
