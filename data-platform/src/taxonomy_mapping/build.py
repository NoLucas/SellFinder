"""sbiz 택소노미 매핑 + demand_signal 빌드 엔트리포인트 (DISPATCH-2 A-1/A-2).

`output/manifest/` 아래(계약 인수인계물, git 추적) 세 산출물을 만든다:
- `taxonomy_sbiz_coverage.json` — 리프 노드별 sbiz_codes 해석 결과(direct/inherited/none).
  ADR-004 "A 가 할 일" #2 의 보고 산출물.
- `demand_signal-{level}-{period}.json` — 매핑 있는 노드에 한해서만 지역별 행.
  매핑 없는 노드는 행 자체가 없다(D-19). `coverage_flag='suppressed'` 행도 실제로 섞여 나온다(A-2).
- `data_source-src_sbiz_market.json` — 06_governance.md §3 형식의 출처 등록.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.taxonomy_mapping.demand_signal import build_demand_signal, data_source_entry
from src.taxonomy_mapping.sbiz_mapping import coverage_report, leaf_mappings, load_taxonomy

DEFAULT_REGION_SOURCE = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sigungu_sample_fixture.geojson"
)


def _load_region_ids(geojson_path: Path) -> list[str]:
    with geojson_path.open("r", encoding="utf-8") as f:
        fc = json.load(f)
    return [feat["properties"]["region_id"] for feat in fc["features"]]


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build(
    output_root: Path,
    region_source: Path = DEFAULT_REGION_SOURCE,
    level: str = "sigungu",
    period: str = "2026-01",
    channel: str = "all",
) -> dict:
    taxonomy = load_taxonomy()
    report = coverage_report(taxonomy)

    mappings = leaf_mappings(taxonomy)
    mappable = [m for m in mappings if m.resolution in ("direct", "inherited")]

    region_ids = _load_region_ids(region_source)
    rows = build_demand_signal(region_ids, mappable, period=period, channel=channel)

    manifest_root = output_root / "manifest"
    _write_json(manifest_root / "taxonomy_sbiz_coverage.json", report)
    _write_json(
        manifest_root / f"demand_signal-{level}-{period}.json",
        [r.to_dict() for r in rows],
    )
    _write_json(manifest_root / "data_source-src_sbiz_market.json", data_source_entry())

    summary = {
        "leaf_nodes_total": report["total_leaf_nodes"],
        "leaf_nodes_mappable": report["mappable_count"],
        "leaf_nodes_unmappable": report["unmappable_count"],
        "regions": len(region_ids),
        "demand_signal_rows": len(rows),
        "rows_actual": sum(1 for r in rows if r.coverage_flag == "actual"),
        "rows_suppressed": sum(1 for r in rows if r.coverage_flag == "suppressed"),
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[2] / "output")
    parser.add_argument("--region-source", type=Path, default=DEFAULT_REGION_SOURCE)
    parser.add_argument("--level", default="sigungu")
    parser.add_argument("--period", default="2026-01")
    parser.add_argument("--channel", default="all")
    args = parser.parse_args()

    summary = build(
        output_root=args.output_root,
        region_source=args.region_source,
        level=args.level,
        period=args.period,
        channel=args.channel,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
