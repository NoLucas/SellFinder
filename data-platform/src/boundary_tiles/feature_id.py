"""region_id(string) <-> MVT feature id(uint) 변환.

**ADR-005/D-20 이후: 조인 키는 이 변환이 아니다.** 유일한 조인 키는
properties 에 원문 문자열로 실리는 `region_id`(`feature_id_property`)다.
D 는 `promoteId` 로 그 속성을 읽는다. 이 모듈의 정수 feature id는 MVT
스펙(feature id는 uint)을 만족시키기 위한 것과 툴 호환·디버깅용으로만
계속 싣는다 — 어떤 소비자도 여기 의존하지 않는다.

- 행정표준코드류(전부 숫자)는 int(region_id)를 그대로 쓴다.
- h3_/cst_ 접두사 같은 비숫자 region_id는 sha256 해시 앞 48비트를 쓴다
  (JS `Number.MAX_SAFE_INTEGER` 안에 들어오게).

역방향 매핑은 빌드 시점의 내부 산출물(`*.id_map.json`)에만 남는다 — 계약
매니페스트의 `id_map_path` 필드는 제거됐다(ADR-005 결정 4). 이 파일은
디버깅용 내부 아티팩트일 뿐, 조인에 필요하지 않다(properties 에 원문이 있다).
"""
from __future__ import annotations

import hashlib

_HASH_BYTES = 6  # 48 bits — JS Number.MAX_SAFE_INTEGER(2**53-1) 안에 여유있게 들어감


class FeatureIdCollisionError(ValueError):
    pass


def region_id_to_feature_id(region_id: str) -> int:
    if not region_id:
        raise ValueError("region_id must be non-empty")
    if region_id.isdigit():
        return int(region_id)
    digest = hashlib.sha256(region_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:_HASH_BYTES], "big")


def build_id_map(region_ids: list[str]) -> dict[str, int]:
    """region_id -> feature_id 매핑을 만들고, 충돌이 있으면 즉시 실패한다."""
    id_map: dict[str, int] = {}
    seen_feature_ids: dict[int, str] = {}
    for region_id in region_ids:
        feature_id = region_id_to_feature_id(region_id)
        if feature_id in seen_feature_ids and seen_feature_ids[feature_id] != region_id:
            raise FeatureIdCollisionError(
                f"feature_id {feature_id} collides between region_id "
                f"{seen_feature_ids[feature_id]!r} and {region_id!r}"
            )
        id_map[region_id] = feature_id
        seen_feature_ids[feature_id] = region_id
    return id_map
