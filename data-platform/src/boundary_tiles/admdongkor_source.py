"""SGIS 파생 실 경계 소스 — vuski/admdongkor (GitHub, CC BY 4.0) 어댑터.

`sgis_source.py` 는 SGIS Open API 직접 연동 계획이고 자격증명이 없어 아직 멈춰 있다
(A-3 착수 단계). **이 모듈은 그것과 다르다** — SGIS 통계지리정보서비스가 원 출처인
행정동 경계 데이터를 CC BY 4.0(원출처 통계청 SGIS, 공공누리 제1유형)로 재배포하는
제3자 저장소(`https://github.com/vuski/admdongkor`)에서 **지금 바로 실제 데이터를
받아온다.** 라이선스가 상업적 이용을 포함해 자유 이용·변형·재배포를 허용하므로
(`06_governance.md` §3 "commercial_use_allowed=false 소스는 프로덕션 투입 금지"에
저촉되지 않는다), SGIS Open API 계정 승인을 기다리지 않고도 지금 실 데이터로
빌드할 수 있다.

**정직성 노트**: 이건 SGIS 를 직접 호출하는 게 아니라, SGIS 데이터를 라이선스대로
재배포하는 제3자 미러다. `data_source` 등록(`admdongkor_data_source_entry`)에
그 사실을 그대로 적는다 — "SGIS 를 직접 연동했다"고 부풀리지 않는다.
jin 이 공식 SGIS Open API 경로만 원한다면 `sgis_source.py` 쪽 자격증명이 있어야
하고, 이 모듈은 그 전까지의 실용적 대안이다.

원본 파일(`ver{YYYYMMDD}/HangJeongDong_ver{YYYYMMDD}.geojson`)의 properties:
`adm_nm`(전체명), `adm_cd2`(10자리 행정동 코드), `sgg`(5자리 시군구 코드),
`sido`(2자리 시도 코드), `sidonm`, `sggnm`, `adm_cd`(8자리 구코드).
`03_region_features.json` 이 요구하는 행정표준코드(8~10자리)와 `adm_cd2` 가
그대로 맞아 region_id 로 쓴다. 좌표계는 CRS84(=WGS84, 우리 tiler 의 입력 가정과 동일).
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

REPO = "vuski/admdongkor"
LICENSE = "CC BY 4.0 (원출처: 통계청 SGIS, 공공누리 제1유형)"


def raw_url(vintage_compact: str) -> str:
    """vintage_compact 는 저장소 폴더명 그대로(YYYYMMDD), 예: '20260701'."""
    return (
        f"https://raw.githubusercontent.com/{REPO}/master/"
        f"ver{vintage_compact}/HangJeongDong_ver{vintage_compact}.geojson"
    )


def download(vintage_compact: str, dest: Path, timeout: int = 120) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = raw_url(vintage_compact)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        dest.write_bytes(resp.read())
    return dest


def convert_to_pipeline_geojson(source_path: Path, level: str = "adm_dong") -> dict:
    """admdongkor 원본을 우리 tiler 가 기대하는 형식으로 변환한다.

    변환 규칙: `properties.region_id` = `adm_cd2`(행정동), `properties.name` =
    `adm_nm`, `is_synthetic_placeholder: False`(합성이 아니라 실측이라는 뜻을
    명시적으로 남긴다). `sido`/`sgg` 원본 코드는 상위 레벨(dissolve) 생성에
    쓸 수 있게 그대로 보존한다.
    """
    with source_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    out_features = []
    seen_ids: set[str] = set()
    for feat in raw["features"]:
        props = feat["properties"]
        region_id = props["adm_cd2"]
        if region_id in seen_ids:
            # 원본에 중복 adm_cd2 가 있으면 조용히 넘어가지 않는다 — id_map 충돌로 이어진다.
            raise ValueError(f"중복 region_id(adm_cd2) 발견: {region_id!r} — 원본 데이터 확인 필요")
        seen_ids.add(region_id)
        out_features.append(
            {
                "type": "Feature",
                "properties": {
                    "region_id": region_id,
                    "name": props["adm_nm"],
                    "level": level,
                    "is_synthetic_placeholder": False,
                    "sido": props["sido"],
                    "sgg": props["sgg"],
                },
                "geometry": feat["geometry"],
            }
        )
    return {"type": "FeatureCollection", "features": out_features}


def admdongkor_data_source_entry(vintage: str, built_at: str) -> dict:
    """06_governance.md §3 등록 예시 형식. 실 데이터 출처임을 명시(합성 아님)."""
    return {
        "source_id": "src_admdongkor_sgis",
        "name": "행정동 경계 (SGIS 파생, admdongkor 미러)",
        "provider": f"{REPO} (GitHub) — 원 출처 통계청 SGIS",
        "url": f"https://github.com/{REPO}",
        "license": LICENSE,
        "commercial_use_allowed": True,
        "refresh_cadence": "quarterly",
        "granularity": "adm_dong / quarterly",
        "known_limitations": [
            "SGIS Open API 직접 연동이 아니라 제3자 CC BY 4.0 재배포본이다 — 출처 표시 의무 유지",
            "행정구역 개편 반영 시차가 있을 수 있다(저장소 커밋 주기에 종속)",
            "집계구·격자 등 세분화 경계는 포함하지 않는다(행정동 레벨만)",
        ],
        "boundary_vintage": vintage,
        "last_ingested_at": built_at,
        "is_synthetic_placeholder": False,
    }
