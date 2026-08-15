"""Synthetic region hierarchy generator.

Produces a small sido -> sigungu -> adm_dong tree. Region IDs use sido
codes 91/92/93, which are not used by any real Korean administrative
code (real codes are 11, 26-31, 36, 41-52) - so these can never collide
with real region_ids later, and anyone can tell at a glance they're
synthetic. ID lengths (2 / 5 / 8 digits) match the real convention in
01_domain_model.json / 03_region_features.json (sido=2, sigungu=5,
adm_dong=8-10).

Region *names* are invented (no real Korean place names) so nobody
mistakes this for real geodata.

feature_gen.py and demand_gen.py only attach region_feature /
demand_signal rows to the adm_dong-level leaves - sido/sigungu records
exist purely to give the hierarchy referential integrity (region.parent_id
resolves to a real record in this same output).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

# region_type is generator-only metadata, not a contract field. It drives
# how features/demand are generated (pop scale, density, etc.) and is
# exported under "_synthetic_region_type" so it's obviously non-contract.
SIDO_DEFS = [
    {
        "name": "한빛특별시",
        "code": "91",
        "sigungu": [
            {"name": "빛여울구", "region_type": "metro", "dong_count": 6},
            {"name": "은강구", "region_type": "metro", "dong_count": 5},
            {"name": "다솔구", "region_type": "metro", "dong_count": 5},
        ],
    },
    {
        "name": "다온광역시",
        "code": "92",
        "sigungu": [
            {"name": "새터구", "region_type": "major_city", "dong_count": 5},
            {"name": "푸른구", "region_type": "major_city", "dong_count": 5},
            {"name": "별내구", "region_type": "mid_city", "dong_count": 4},
        ],
    },
    {
        "name": "노을도",
        "code": "93",
        "sigungu": [
            {"name": "강마을시", "region_type": "mid_city", "dong_count": 5},
            {"name": "온샘시", "region_type": "mid_city", "dong_count": 5},
            {"name": "달빛군", "region_type": "rural", "dong_count": 5},
            {"name": "메아리군", "region_type": "rural", "dong_count": 5},
        ],
    },
]

# (pop_total_range, area_km2_range) per synthetic region_type. Ranges are
# deliberately extreme end-to-end (1,800 -> 520,000) per the brief:
# "지역 규모를 실제처럼 극단적으로 분포시켜라". rural's upper bound is kept
# under 30,000 on purpose so the "pop<30,000 adm_dong" confidence-downgrade
# rule (05_scoring_spec.md §4) always has real rows to trigger on.
REGION_TYPE_RANGES = {
    "metro": {"pop": (140_000, 520_000), "area_km2": (3.0, 14.0)},
    "major_city": {"pop": (55_000, 300_000), "area_km2": (5.0, 22.0)},
    "mid_city": {"pop": (14_000, 92_000), "area_km2": (18.0, 70.0)},
    "rural": {"pop": (1_800, 29_500), "area_km2": (70.0, 420.0)},
}

_DONG_SYLLABLES = [
    "늘봄", "해솔", "은빛", "청람", "다래", "보름", "노을", "샛별",
    "푸른", "여울", "가온", "달맞", "솔바람", "물결", "하늘", "봄내",
    "가람", "수련", "온새", "빛고을", "구름", "메아리", "산들", "별밭",
]

# South Korea bounding box (rough), used only to place fake centroids.
_LAT_RANGE = (33.1, 38.6)
_LNG_RANGE = (125.0, 129.6)


@dataclass
class RegionRecord:
    region_id: str
    level: str
    parent_id: str | None
    name: str
    full_name: str
    center_lat: float
    center_lng: float
    area_km2: float
    tenant_id: None
    valid_from: str
    synthetic_region_type: str | None = field(default=None)

    def to_contract_dict(self) -> dict:
        d = {
            "region_id": self.region_id,
            "level": self.level,
            "parent_id": self.parent_id,
            "name": self.name,
            "full_name": self.full_name,
            "center_lat": round(self.center_lat, 5),
            "center_lng": round(self.center_lng, 5),
            "area_km2": round(self.area_km2, 2),
            "tenant_id": self.tenant_id,
            "valid_from": self.valid_from,
            "valid_to": None,
        }
        if self.synthetic_region_type:
            d["_synthetic_region_type"] = self.synthetic_region_type
        return d


def _unique_dong_name(rng: random.Random, used: set[str]) -> str:
    while True:
        name = rng.choice(_DONG_SYLLABLES) + rng.choice(_DONG_SYLLABLES) + "동"
        if name not in used:
            used.add(name)
            return name


def generate_region_hierarchy(seed: int = 42, valid_from: str = "2024-01-01") -> dict:
    """Returns {"regions": [...], "adm_dong_ids_by_type": {type: [region_id,...]}}.

    "regions" includes sido + sigungu + adm_dong levels. Only adm_dong
    entries carry a _synthetic_region_type / population large enough to
    drive feature generation - feature_gen.py reads adm_dong_ids_by_type
    plus the per-region pop_total stashed in `_pop_by_region` to build
    correlated features.
    """
    rng = random.Random(seed)
    regions: list[RegionRecord] = []
    adm_dong_ids_by_type: dict[str, list[str]] = {t: [] for t in REGION_TYPE_RANGES}
    pop_by_region: dict[str, int] = {}
    used_dong_names: set[str] = set()

    for sido in SIDO_DEFS:
        sido_id = sido["code"]
        sido_lat = rng.uniform(*_LAT_RANGE)
        sido_lng = rng.uniform(*_LNG_RANGE)
        regions.append(
            RegionRecord(
                region_id=sido_id,
                level="sido",
                parent_id=None,
                name=sido["name"],
                full_name=sido["name"],
                center_lat=sido_lat,
                center_lng=sido_lng,
                area_km2=0.0,  # filled in below once children are known
                tenant_id=None,
                valid_from=valid_from,
            )
        )
        sido_area = 0.0

        for sg_idx, sigungu in enumerate(sido["sigungu"], start=1):
            sigungu_id = f"{sido_id}{sg_idx:03d}"
            sg_lat = sido_lat + rng.uniform(-0.15, 0.15)
            sg_lng = sido_lng + rng.uniform(-0.15, 0.15)
            region_type = sigungu["region_type"]
            pop_lo, pop_hi = REGION_TYPE_RANGES[region_type]["pop"]
            area_lo, area_hi = REGION_TYPE_RANGES[region_type]["area_km2"]

            regions.append(
                RegionRecord(
                    region_id=sigungu_id,
                    level="sigungu",
                    parent_id=sido_id,
                    name=sigungu["name"],
                    full_name=f"{sido['name']} {sigungu['name']}",
                    center_lat=sg_lat,
                    center_lng=sg_lng,
                    area_km2=0.0,
                    tenant_id=None,
                    valid_from=valid_from,
                )
            )
            sigungu_area = 0.0

            for dong_idx in range(1, sigungu["dong_count"] + 1):
                dong_id = f"{sigungu_id}{dong_idx:03d}"
                dong_name = _unique_dong_name(rng, used_dong_names)
                pop_total = rng.randint(pop_lo, pop_hi)
                area_km2 = rng.uniform(area_lo, area_hi)
                dong_lat = sg_lat + rng.uniform(-0.05, 0.05)
                dong_lng = sg_lng + rng.uniform(-0.05, 0.05)

                regions.append(
                    RegionRecord(
                        region_id=dong_id,
                        level="adm_dong",
                        parent_id=sigungu_id,
                        name=dong_name,
                        full_name=f"{sido['name']} {sigungu['name']} {dong_name}",
                        center_lat=dong_lat,
                        center_lng=dong_lng,
                        area_km2=area_km2,
                        tenant_id=None,
                        valid_from=valid_from,
                        synthetic_region_type=region_type,
                    )
                )
                adm_dong_ids_by_type[region_type].append(dong_id)
                pop_by_region[dong_id] = pop_total
                sigungu_area += area_km2

            sigungu_area = round(sigungu_area, 2)
            sido_area += sigungu_area

        sido_area = round(sido_area, 2)

    # backfill aggregated area_km2 for sigungu/sido now that children are known
    area_by_id: dict[str, float] = {}
    for r in regions:
        if r.level == "adm_dong":
            area_by_id[r.region_id] = r.area_km2
    for r in regions:
        if r.level == "sigungu":
            children_area = sum(
                area_by_id[rid]
                for rid, parent in ((rr.region_id, rr.parent_id) for rr in regions if rr.level == "adm_dong")
                if parent == r.region_id
            )
            r.area_km2 = round(children_area, 2)
            area_by_id[r.region_id] = r.area_km2
    for r in regions:
        if r.level == "sido":
            children_area = sum(
                area_by_id[rr.region_id] for rr in regions if rr.level == "sigungu" and rr.parent_id == r.region_id
            )
            r.area_km2 = round(children_area, 2)

    return {
        "regions": regions,
        "adm_dong_ids_by_type": adm_dong_ids_by_type,
        "pop_by_region": pop_by_region,
    }
