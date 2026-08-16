"""region_feature 행을 계약 스키마로 쓰는 공용 라이터.

`01_domain_model.json` region_feature 엔티티(`region_id`, `feature_key`,
`value_num`, `value_json`, `valid_from`, `valid_to`, `source_id`, `ingested_at`)
그대로다. `intelligence/scoring/feature_store.py::RegionFeatureFileStore` 가
`data-platform/output/region_features/*.json` 에서 이 정확한 형태를 기대한다
(각 파일이 행의 JSON 배열). 이 라이터를 거치면 그 리더와 바로 호환된다.

**as_of 규율(`03_region_features.json` point_in_time_rule)이 이 모듈의 존재
이유다.** "최신값" 헬퍼를 여기 만들지 않는다 — 이 모듈은 쓰기 전용이고, 조회는
전적으로 B 의 `get_features(region_ids, feature_keys, as_of)` 쪽 책임이다.
대신 이 라이터가 강제하는 것:

1. `feature_key` 는 `03_region_features.json` registry 에 등록된 공개(비
   tenant_scoped) 키만 허용한다 — 없는 키를 조용히 받지 않는다.
2. 선언된 타입(number/json/string/boolean)과 실제로 채운 컬럼
   (`value_num`/`value_json`)이 일치해야 한다.
3. **동일 (region_id, feature_key) 의 유효 구간이 겹치면 거부한다**
   (도메인 모델 제약 그대로). 겹치면 `as_of` 조회가 둘 이상의 행을 만나
   어느 게 "진짜"인지 모호해지고, 그게 바로 "최신값 헬퍼"가 필요해지는
   상황을 만든다 — 애초에 그 상황 자체를 안 만든다.
4. 결측은 `value_num=None, value_json=None` 인 행으로 명시적으로 남긴다
   (0 으로 채우지 않는다, `feature_quality_rules`). 행 자체를 생략하는 것과
   다르다 — 생략은 "확인 안 함", null 행은 "확인했는데 없음"이다.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

CONTRACTS_ROOT = Path(__file__).resolve().parents[3] / "shared" / "contracts"
REGION_FEATURES_CONTRACT_PATH = CONTRACTS_ROOT / "03_region_features.json"


class RegionFeatureValidationError(ValueError):
    pass


def load_feature_registry(path: Path = REGION_FEATURES_CONTRACT_PATH) -> dict[str, dict]:
    """공개(비 tenant_scoped) feature_key -> spec 만 반환한다.

    A 는 공개 데이터 파이프라인이다. `tenant_scoped` 4개는 테넌트가 업로드한
    `tenant_sales` 에서 파생되는 것으로, 별도 인제스트 경로(backend 소유)를
    거친다 — A 가 여기서 만들어 내보낼 대상이 아니다.
    """
    with path.open("r", encoding="utf-8") as f:
        contract = json.load(f)
    registry = contract["feature_registry"]
    out: dict[str, dict] = {}
    for category, keys in registry.items():
        if category.startswith("$") or category == "tenant_scoped":
            continue
        for key, spec in keys.items():
            out[key] = {**spec, "_category": category}
    return out


@dataclass(frozen=True)
class RegionFeatureRow:
    region_id: str
    feature_key: str
    valid_from: str
    valid_to: str | None
    source_id: str
    ingested_at: str
    value_num: float | None = None
    value_json: dict | object | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _validate_iso_date(value: str, field_name: str) -> None:
    try:
        date.fromisoformat(value)
    except (ValueError, TypeError) as e:
        raise RegionFeatureValidationError(f"{field_name} must be an ISO date (YYYY-MM-DD), got {value!r}") from e


def _validate_row(row: RegionFeatureRow, registry: dict[str, dict]) -> None:
    if row.feature_key not in registry:
        raise RegionFeatureValidationError(
            f"feature_key={row.feature_key!r} 는 03_region_features.json registry 에 없다. "
            "등록되지 않은 키는 region_feature 에 들어갈 수 없다(계약 그대로)."
        )
    if not row.source_id:
        raise RegionFeatureValidationError("source_id 는 필수다 (06_governance.md: 출처 없는 숫자는 인제스트하지 않는다)")
    if not row.ingested_at:
        raise RegionFeatureValidationError("ingested_at 은 필수다")
    _validate_iso_date(row.valid_from, "valid_from")
    if row.valid_to is not None:
        _validate_iso_date(row.valid_to, "valid_to")
        if row.valid_to <= row.valid_from:
            raise RegionFeatureValidationError(
                f"valid_to({row.valid_to}) 는 valid_from({row.valid_from}) 보다 뒤여야 한다"
            )

    declared_type = registry[row.feature_key].get("type")
    has_num = row.value_num is not None
    has_json = row.value_json is not None
    if has_num and has_json:
        raise RegionFeatureValidationError(
            f"{row.region_id}/{row.feature_key}: value_num 과 value_json 을 동시에 채울 수 없다"
        )
    if declared_type == "number" and has_json:
        raise RegionFeatureValidationError(
            f"{row.feature_key} 는 type=number 인데 value_json 이 채워졌다 — value_num 을 써야 한다"
        )
    if declared_type in ("json", "string", "boolean") and has_num:
        raise RegionFeatureValidationError(
            f"{row.feature_key} 는 type={declared_type} 인데 value_num 이 채워졌다 — "
            "도메인 모델에 value_str/value_bool 컬럼이 따로 없으므로 value_json 에 "
            '{"value": ...} 형태로 실어야 한다'
        )


def _overlaps(a_from: str, a_to: str | None, b_from: str, b_to: str | None) -> bool:
    a_end = a_to or "9999-12-31"
    b_end = b_to or "9999-12-31"
    return a_from < b_end and b_from < a_end


def _check_no_overlap(rows: list[RegionFeatureRow]) -> None:
    """01_domain_model.json 제약: 동일 (region_id, feature_key) 의 valid 구간은 겹칠 수 없다."""
    by_key: dict[tuple[str, str], list[RegionFeatureRow]] = {}
    for row in rows:
        by_key.setdefault((row.region_id, row.feature_key), []).append(row)
    for (region_id, feature_key), group in by_key.items():
        ordered = sorted(group, key=lambda r: r.valid_from)
        for prev, curr in zip(ordered, ordered[1:]):
            if _overlaps(prev.valid_from, prev.valid_to, curr.valid_from, curr.valid_to):
                raise RegionFeatureValidationError(
                    f"{region_id}/{feature_key}: 겹치는 유효 구간 "
                    f"[{prev.valid_from}, {prev.valid_to}) 와 [{curr.valid_from}, {curr.valid_to}) "
                    "— as_of 조회가 어느 쪽이 진짜인지 모호해진다"
                )


def write_region_features(
    rows: list[RegionFeatureRow],
    output_dir: Path,
    registry: dict[str, dict] | None = None,
) -> dict[str, Path]:
    """feature_key 별로 `{output_dir}/{feature_key}.json` 에 쓴다.

    `RegionFeatureFileStore.from_directory(output_dir)` 가 바로 읽을 수 있는
    형태다 — 파일마다 행의 JSON 배열.
    """
    registry = registry or load_feature_registry()
    for row in rows:
        _validate_row(row, registry)
    _check_no_overlap(rows)

    by_feature: dict[str, list[RegionFeatureRow]] = {}
    for row in rows:
        by_feature.setdefault(row.feature_key, []).append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for feature_key, group in by_feature.items():
        path = output_dir / f"{feature_key}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in group], f, ensure_ascii=False, indent=2)
            f.write("\n")
        written[feature_key] = path
    return written
