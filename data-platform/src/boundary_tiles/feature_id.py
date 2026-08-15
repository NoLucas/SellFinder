"""region_id(string) <-> MVT feature id(uint) 변환.

MVT/PMTiles의 feature id는 음이 아닌 정수(protobuf uint64)여야 한다. 콘솔의
`setFeatureState`는 이 id를 키로 쓰므로, region_id를 속성(properties)이 아니라
이 id 자체로 실어야 한다(브리프 지시사항). region_id는 문자열이라 직접 쓸 수
없으므로 여기서 결정론적으로 변환한다.

- 행정표준코드류(전부 숫자)는 int(region_id)를 그대로 쓴다. 사람이 읽어도
  원래 코드를 바로 알아볼 수 있고, 값 자체가 작아 충돌 위험이 없다.
- h3_/cst_ 접두사 같은 비숫자 region_id는 sha256 해시 앞 48비트를 쓴다.
  48비트로 제한하는 이유: JS `Number`의 안전 정수 범위(2**53-1) 안에 여유
  있게 들어와야 콘솔(JS/MapLibre) 쪽에서 정밀도 손실 없이 다룰 수 있다.

역방향 매핑(어떤 numeric id가 어떤 region_id였는지)은 여기서 복원하지 않는다
— 해시는 일방향이므로, 빌드 시점에 만든 id_map.json이 유일한 역방향 소스다.
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
