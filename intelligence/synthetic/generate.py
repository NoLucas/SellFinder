"""CLI + library entrypoint for the SellFinder synthetic data generator.

    python -m synthetic.generate                       # regenerates the committed sample/ exactly
    python -m synthetic.generate --out-dir /tmp/bigger --start-period 2023-01 --end-period 2026-06 --seed 7

Region count is fixed (50 adm_dong regions across 4 synthetic types - see
region_gen.SIDO_DEFS) rather than a --regions flag: the point is a
realistic *shape* (extreme size spread, 4 region-type buckets for the
backtest's by-region-type breakdown), and 50 is already enough to give
every quantile-based ground_truth relationship a clean top-quartile/
top-tercile split. Widen SIDO_DEFS directly if a bigger set is needed.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from . import contracts, demand_gen, feature_gen, ground_truth, region_gen

DEFAULT_START_PERIOD = "2025-01"
DEFAULT_END_PERIOD = "2026-06"
DEFAULT_SEED = 42
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "sample"

DATA_SOURCES = [
    {
        "source_id": "src_syn_public",
        "name": "(합성) 공공 인구·상권·개발 통계",
        "provider": "synthetic",
        "license": "N/A (generated data)",
        "commercial_use_allowed": True,
        "refresh_cadence": "monthly",
        "granularity": "adm_dong / monthly",
        "known_limitations": ["합성 데이터입니다. 실제 통계가 아닙니다."],
    },
    {
        "source_id": "src_syn_card",
        "name": "(합성) 카드 소비 통계",
        "provider": "synthetic",
        "license": "N/A (generated data)",
        "commercial_use_allowed": True,
        "refresh_cadence": "monthly",
        "granularity": "adm_dong / monthly",
        "known_limitations": ["합성 데이터입니다. 실제 카드사 라이선스 검토가 필요 없습니다."],
    },
    {
        "source_id": "src_syn_online",
        "name": "(합성) 이커머스 주문 밀도",
        "provider": "synthetic",
        "license": "N/A (generated data)",
        "commercial_use_allowed": True,
        "refresh_cadence": "monthly",
        "granularity": "adm_dong / monthly",
        "known_limitations": ["합성 데이터입니다."],
    },
    {
        "source_id": "src_syn_demand",
        "name": "(합성) 업종별 소비 신호 (demand_signal)",
        "provider": "synthetic",
        "license": "N/A (generated data)",
        "commercial_use_allowed": True,
        "refresh_cadence": "monthly",
        "granularity": "adm_dong × taxonomy_node × channel / monthly",
        "known_limitations": ["합성 데이터입니다. ground_truth.json의 planted relationship 계수가 반영되어 있습니다."],
    },
]

_SOURCE_ID_BY_CATEGORY = {
    "population": "src_syn_public",
    "commercial": "src_syn_public",
    "development": "src_syn_public",
    "traffic_access": "src_syn_public",
    "income_spend": "src_syn_card",
    "online": "src_syn_online",
    "default": "src_syn_public",
}


def generate_all(
    seed: int = DEFAULT_SEED,
    start_period: str = DEFAULT_START_PERIOD,
    end_period: str = DEFAULT_END_PERIOD,
) -> dict:
    """Returns the full in-memory synthetic dataset. No file I/O.

    Deterministic: same (seed, start_period, end_period) always produces
    byte-identical output (see tests/test_synthetic_generator.py's
    reproducibility test).
    """
    region_hier = region_gen.generate_region_hierarchy(seed=seed)
    feature_rng = random.Random(seed + 1)  # separate stream from region_gen's internal one

    profiles = feature_gen.build_region_profiles(
        region_hier["adm_dong_ids_by_type"], region_hier["pop_by_region"], feature_rng
    )
    resolved_relationships = ground_truth.resolve_relationships(profiles)

    taxonomy_leaves = contracts.flatten_taxonomy_leaves()
    leaves_by_id = {leaf["node_id"]: leaf for leaf in taxonomy_leaves}
    periods = feature_gen.period_list(start_period, end_period)

    demand_rows = demand_gen.generate_demand_signal_rows(
        profiles=profiles,
        taxonomy_leaves_by_id=leaves_by_id,
        periods=periods,
        resolved_relationships=resolved_relationships,
        rng=feature_rng,
        source_id="src_syn_demand",
    )

    feature_rows = feature_gen.generate_region_feature_rows(
        profiles=profiles,
        start_period=start_period,
        end_period=end_period,
        rng=feature_rng,
        source_ids=_SOURCE_ID_BY_CATEGORY,
        demand_rows=demand_rows,
        include_leakage_trap=True,
    )
    feature_rows = feature_gen.attach_derived_from_demand(feature_rows, demand_rows, _SOURCE_ID_BY_CATEGORY)

    regions_out = [r.to_contract_dict() for r in region_hier["regions"]]

    manifest = {
        "seed": seed,
        "start_period": start_period,
        "end_period": end_period,
        "periods": periods,
        "region_count": len(regions_out),
        "adm_dong_count": sum(len(v) for v in region_hier["adm_dong_ids_by_type"].values()),
        "adm_dong_count_by_type": {k: len(v) for k, v in region_hier["adm_dong_ids_by_type"].items()},
        "region_feature_row_count": len(feature_rows),
        "demand_signal_row_count": len(demand_rows),
        "curated_taxonomy_nodes": demand_gen.CURATED_NODES,
        "suggested_backtest_split": {
            "train": f"{start_period}..2025-12",
            "validation": "2026-01..2026-06",
            "note": (
                "05_scoring_spec.md §5.1 예시와 동일한 경계. leakage trap feature "
                f"({ground_truth.LEAKAGE_TRAP_FEATURE_KEY})도 이 경계(2026-01-01)부터 존재한다."
            ),
        },
    }

    ground_truth_export = {
        "planted_relationships": resolved_relationships,
        "leakage_trap": {
            "feature_key": ground_truth.LEAKAGE_TRAP_FEATURE_KEY,
            "cutoff_valid_from": ground_truth.LEAKAGE_TRAP_CUTOFF,
            "source_node_for_proxy": ground_truth.LEAKAGE_TRAP_SOURCE_NODE,
            "description": ground_truth.LEAKAGE_TRAP_DESCRIPTION,
        },
        "generation_params": {"seed": seed, "start_period": start_period, "end_period": end_period},
    }

    return {
        "regions": regions_out,
        "region_features": feature_rows,
        "demand_signal": demand_rows,
        "data_sources": DATA_SOURCES,
        "ground_truth": ground_truth_export,
        "manifest": manifest,
        "_profiles": profiles,  # not written to disk by default; useful for tests/notebooks
    }


#  region_features.json and demand_signal.json are row-heavy (10k-100k+
# rows depending on --start-period/--end-period range) - pretty-printing
# those would roughly double an already large file for no real benefit,
# so they're written compact. The small reference files stay indented
# since people actually read those directly.
_COMPACT_FILES = {"region_features.json", "demand_signal.json"}


def write_output(dataset: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "regions.json": dataset["regions"],
        "region_features.json": dataset["region_features"],
        "demand_signal.json": dataset["demand_signal"],
        "data_sources.json": dataset["data_sources"],
        "ground_truth.json": dataset["ground_truth"],
        "manifest.json": dataset["manifest"],
    }
    for filename, payload in files.items():
        with (out_dir / filename).open("w", encoding="utf-8") as f:
            if filename in _COMPACT_FILES:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            else:
                json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=False)
            f.write("\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--start-period", default=DEFAULT_START_PERIOD, help="YYYY-MM")
    parser.add_argument("--end-period", default=DEFAULT_END_PERIOD, help="YYYY-MM")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    dataset = generate_all(seed=args.seed, start_period=args.start_period, end_period=args.end_period)
    write_output(dataset, args.out_dir)
    m = dataset["manifest"]
    print(
        f"wrote {m['region_count']} regions ({m['adm_dong_count']} adm_dong), "
        f"{m['region_feature_row_count']} region_feature rows, "
        f"{m['demand_signal_row_count']} demand_signal rows to {args.out_dir}"
    )


if __name__ == "__main__":
    main()
