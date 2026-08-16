"""통계청 SGIS(통계지리정보서비스) 실 경계 데이터 연동 — 착수 단계 (DISPATCH-2 A-3).

**지금 이 모듈은 실제로 SGIS 를 호출하지 않는다.** 이유는 자격증명이 없어서다
(아래 `SgisCredentialsMissingError` 참조). `03_region_features.json`
`recommended_public_sources` 가 명시한 URL(`https://sgis.kostat.go.kr`)만 계약에서
확인했고, OpenAPI 인증 흐름·요청/응답 스키마의 정확한 형태는 이 세션에서 실제
API 문서를 열람해 검증하지 못했다 — 지어내지 않는다. 그래서 이 모듈이 하는 일은:

1. 기존 `build_vintage()` 가 "GeoJSON FeatureCollection 파일 경로"만 받던 것을
   `BoundarySource` 라는 명시적 경계로 뽑아, 어디를 갈아끼우면 실 데이터가
   들어오는지 코드 상에서 분명히 한다.
2. 자격증명이 없는 지금 상태에서 호출하면 **조용히 합성 데이터로 대체하지 않고**
   명확한 예외로 실패한다 — "모르면 503/예외지 추측이 아니다" (DISPATCH-2 §9).

## 다음 사람이 할 일 (자격증명 확보 후)
1. SGIS Open API 계정 신청(`https://sgis.kostat.go.kr` 회원가입 + OpenAPI 사용 승인 —
   보통 영업일 기준 심사가 있다. **사람이 해야 하는 외부 절차이고, 에이전트 세션이
   대신 할 수 없다.**) 후 `consumer_key`/`consumer_secret` 발급.
2. `SGIS_CONSUMER_KEY` / `SGIS_CONSUMER_SECRET` 환경변수로 주입 (자격증명을 코드에
   하드코딩하지 않는다 — `06_governance.md` "비밀 관리" 규칙).
3. 인증 토큰 발급 → 행정경계(`boundary`) API 호출 → 응답(형식 확인 필요:
   SGIS 는 전통적으로 GeoJSON 이 아니라 자체 좌표 포맷/EPSG:5179 를 쓰는 것으로
   알려져 있다 — **이 가정도 실제 API 응답으로 검증 전까지는 확정이 아니다**) →
   EPSG:4326 GeoJSON FeatureCollection 변환 → `properties.region_id` 를 행정표준코드로
   채운 뒤 **기존 `tiler.build_tiles`/`build.build_vintage` 파이프라인에 그대로
   투입**(변환 계층만 새로 짜면 되고, 타일링·조인 키·매니페스트 로직은 이미 있다).
4. `data_source` 레지스트리에 `src_sgis_boundary` 항목을 등록하고
   (형식은 `taxonomy_mapping/demand_signal.py::data_source_entry` 참고),
   이 빈티지의 매니페스트 `attribution` 에서 `is_synthetic_placeholder` 문구를 뗀다 —
   그 순간부터가 "합성 표본이 아닌 빈티지"다.
5. 인구·가구 통계(`population.pop_total` 등)도 SGIS 가 같이 준다
   (`recommended_public_sources`: "행정동/집계구 경계, 인구·가구 통계") — 경계
   연동과 같은 인증 계층을 재사용할 수 있으므로 §5 "region_feature 스토어" 착수
   시점에 이 모듈을 확장하는 편이 새로 만드는 것보다 낫다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SGIS_BASE_URL = "https://sgis.kostat.go.kr"  # 03_region_features.json recommended_public_sources 에서 확인
CONSUMER_KEY_ENV = "SGIS_CONSUMER_KEY"
CONSUMER_SECRET_ENV = "SGIS_CONSUMER_SECRET"


class SgisCredentialsMissingError(RuntimeError):
    """자격증명이 없다. 합성 데이터로 조용히 대체하지 않고 여기서 멈춘다."""


@dataclass(frozen=True)
class SgisCredentials:
    consumer_key: str
    consumer_secret: str

    @classmethod
    def from_env(cls) -> "SgisCredentials":
        key = os.environ.get(CONSUMER_KEY_ENV)
        secret = os.environ.get(CONSUMER_SECRET_ENV)
        if not key or not secret:
            raise SgisCredentialsMissingError(
                f"{CONSUMER_KEY_ENV}/{CONSUMER_SECRET_ENV} 환경변수가 없다. "
                f"SGIS Open API 계정 신청·승인은 사람이 해야 하는 외부 절차다 "
                f"({SGIS_BASE_URL} 회원가입 + OpenAPI 사용 신청). "
                "발급 전까지 이 소스는 사용할 수 없다 — 합성 데이터로 대체하지 않는다."
            )
        return cls(consumer_key=key, consumer_secret=secret)


def fetch_boundary_geojson(level: str, vintage: str, output_path: Path) -> Path:
    """실 SGIS 경계를 받아 GeoJSON 으로 저장한다.

    **아직 구현되지 않았다.** 자격증명 확인까지만 이번 착수 단계의 범위다 —
    실제 HTTP 호출·좌표계 변환·응답 스키마 매핑은 자격증명을 손에 넣은 뒤,
    실제 API 응답을 보고 구현해야 한다(모듈 독스트링 "다음 사람이 할 일" 참고).
    지금 구현하면 검증되지 않은 가정을 코드로 굳히는 것이라 하지 않는다.
    """
    SgisCredentials.from_env()  # 자격증명부터 확인 — 없으면 여기서 멈춘다.
    raise NotImplementedError(
        "SGIS 자격증명 확인까지만 이번 단계의 범위다. HTTP 호출·좌표 변환은 "
        "자격증명 확보 후 실제 API 응답을 보고 구현한다 (모듈 독스트링 참고)."
    )
