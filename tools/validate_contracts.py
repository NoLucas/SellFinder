#!/usr/bin/env python3
"""
SellFinder 계약 준수 검증기.

에이전트가 자기 폴더 밖을 건드렸는지, 계약 파일을 무단 수정했는지,
택소노미 참조가 깨졌는지, 예측 응답이 스키마를 지키는지 검사한다.

사용:
    python tools/validate_contracts.py                       # 전체 정적 검사
    python tools/validate_contracts.py --base origin/master --agent A
    python tools/validate_contracts.py --check-response out.json
    python tools/validate_contracts.py --check-scores backend/samples/scores.json
    python tools/validate_contracts.py --check-manifest backend/samples/manifest.json

표준 라이브러리만 사용한다 (에이전트 환경마다 의존성이 다르므로).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "shared" / "contracts"

AGENT_FOLDERS = {
    "A": "data-platform",
    "B": "intelligence",
    "C": "backend",
    "D": "console",
}

PROTECTED_PREFIXES = ("shared/contracts/", "tools/")

# 05_scoring_spec.md 에서 확정된 8개 요인. 이 외의 키는 허용하지 않는다.
FACTOR_KEYS = {
    "addressable_demand",
    "category_penetration",
    "product_affinity",
    "price_acceptance",
    "competition",
    "channel_availability",
    "seasonality",
    "tenant_calibration",
}

OBJECTIVES = {"store_expansion", "distribution_push", "ad_targeting"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        err(f"계약 파일 없음: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as e:
        err(f"JSON 파싱 실패 {path.name}: {e}")
    return None


# ────────────────────────── 1. 폴더 경계 검사 ──────────────────────────
def check_boundaries(base: str, agent: str) -> None:
    """에이전트가 자기 폴더 밖을 수정했는지 git diff 로 검사."""
    own = AGENT_FOLDERS.get(agent.upper())
    if own is None:
        err(f"알 수 없는 에이전트: {agent} (A|B|C|D 중 하나)")
        return

    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        warn(f"git diff 실행 불가, 경계 검사 건너뜀 ({e})")
        return

    changed = [p for p in out.splitlines() if p.strip()]
    if not changed:
        warn("변경된 파일이 없습니다.")
        return

    for path in changed:
        if path.startswith(PROTECTED_PREFIXES):
            err(f"[경계 위반] 보호 경로를 수정했습니다: {path}\n"
                f"            → 직접 수정 대신 {own}/CONTRACT_CHANGE_REQUEST.md 로 제안하세요.")
        elif not path.startswith(f"{own}/"):
            other = next((f for f in AGENT_FOLDERS.values() if path.startswith(f + "/")), None)
            if other:
                err(f"[경계 위반] 다른 에이전트 폴더를 수정했습니다: {path} (소유: {other})")
            else:
                warn(f"[확인 필요] 공용 루트 파일 수정: {path} — 사람이 취합해야 합니다.")

    print(f"  경계 검사: {len(changed)}개 변경 파일 확인 (소유 폴더: {own}/)")


# ────────────────────────── 2. 택소노미 무결성 ──────────────────────────
def walk_taxonomy(nodes, acc, parent=None):
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("node_id")
        if nid:
            if nid in acc:
                err(f"[택소노미] node_id 중복: {nid}")
            acc[nid] = {"parent": n.get("parent_id", parent), "node": n}
        walk_taxonomy(n.get("children", []), acc, nid)


def check_taxonomy() -> None:
    data = load_json(CONTRACTS / "02_taxonomy.json")
    if not data:
        return

    nodes: dict = {}
    walk_taxonomy(data.get("taxonomy", []), nodes)

    for nid, meta in nodes.items():
        parent = meta["parent"]
        if parent and parent not in nodes:
            err(f"[택소노미] {nid} 의 parent_id '{parent}' 가 존재하지 않습니다.")
        if not re.match(r"^TX-[A-Z0-9-]+$", nid):
            err(f"[택소노미] node_id 형식 위반: {nid} (TX-대문자-하이픈 형식이어야 함)")

        prof = meta["node"].get("seasonality_profile")
        if prof is not None:
            if len(prof) != 12:
                err(f"[택소노미] {nid} seasonality_profile 은 12개월이어야 합니다 (현재 {len(prof)}).")
            elif not (0.85 <= sum(prof) / 12 <= 1.15):
                warn(f"[택소노미] {nid} seasonality_profile 평균이 1.0 에서 많이 벗어납니다 "
                     f"({sum(prof)/12:.3f}).")

    channels = {k: v for k, v in data.get("channels", {}).items() if not k.startswith("$")}
    for node in nodes.values():
        for ch in node["node"].get("default_channels", []):
            if ch not in channels:
                err(f"[택소노미] 정의되지 않은 채널 참조: {ch}")

    print(f"  택소노미: 노드 {len(nodes)}개, 채널 {len(channels)}개 검증 완료")


# ────────────────────────── 3. 피처 레지스트리 ──────────────────────────
def check_feature_registry() -> None:
    data = load_json(CONTRACTS / "03_region_features.json")
    if not data:
        return

    registry = data.get("feature_registry", {})
    keys: set[str] = set()
    for group, feats in registry.items():
        if not isinstance(feats, dict):
            continue
        for k in feats:
            if k.startswith("$"):
                continue
            if k in keys:
                err(f"[피처] feature_key 중복: {k}")
            keys.add(k)

    if not data.get("point_in_time_rule"):
        err("[피처] point_in_time_rule 이 정의되지 않았습니다. 미래 정보 누수를 막을 수 없습니다.")

    tenant_scoped = set(registry.get("tenant_scoped", {}).keys())
    print(f"  피처 레지스트리: {len(keys)}개 키 (테넌트 전용 {len(tenant_scoped)}개) 검증 완료")


# ────────────────────────── 4. 도메인 모델 ──────────────────────────
def check_domain_model() -> None:
    data = load_json(CONTRACTS / "01_domain_model.json")
    if not data:
        return

    entities = data.get("entities", {})
    tenant_owned = {"product", "tenant_sales", "own_store", "prediction_run", "scenario",
                    "import_job", "audit_log", "user"}

    for name in tenant_owned:
        ent = entities.get(name)
        if ent is None:
            err(f"[도메인] 엔티티 누락: {name}")
            continue
        if "tenant_id" not in ent.get("fields", {}):
            err(f"[도메인] {name} 에 tenant_id 가 없습니다. 테넌트 격리가 깨집니다.")

    rules = data.get("global_rules", {})
    iso = rules.get("tenant_isolation", "")
    if "토큰" not in iso:
        err("[도메인] global_rules.tenant_isolation 에 토큰 파생 규칙이 명시되어야 합니다.")

    # 금액 필드 명명 규칙
    for ename, ent in entities.items():
        for fname, f in (ent.get("fields") or {}).items():
            if isinstance(f, dict) and f.get("unit") == "원" and not fname.endswith("_krw"):
                warn(f"[도메인] {ename}.{fname} 는 금액이므로 _krw 접미사를 권장합니다.")

    print(f"  도메인 모델: 엔티티 {len(entities)}개 검증 완료")


# ────────────────────────── 5. 예측 응답 검증 ──────────────────────────
def check_prediction_response(path: pathlib.Path) -> None:
    """에이전트 B/C 가 만든 실제 응답 JSON 이 계약을 지키는지 검사."""
    data = load_json(path)
    if not data:
        return

    required = ["run_id", "product_id", "region_id", "opportunity_score", "confidence", "factors"]
    for k in required:
        if k not in data:
            err(f"[응답] 필수 필드 누락: {k}")

    score = data.get("opportunity_score")
    if isinstance(score, (int, float)) and not (0 <= score <= 100):
        err(f"[응답] opportunity_score 범위 위반: {score} (0~100)")

    conf = data.get("confidence") or {}
    if conf.get("level") not in CONFIDENCE_LEVELS:
        err(f"[응답] confidence.level 값 위반: {conf.get('level')}")
    cov = conf.get("data_coverage")
    if not isinstance(cov, (int, float)) or not (0 <= cov <= 1):
        err(f"[응답] confidence.data_coverage 는 0~1 이어야 합니다: {cov}")

    # T0 는 금액 추정 금지
    tier = data.get("data_tier")
    if tier == "T0" and data.get("expected_revenue_krw") is not None:
        err("[응답] data_tier=T0 인데 expected_revenue_krw 가 채워졌습니다. "
            "근거 없는 금액 추정은 금지입니다 (05_scoring_spec.md §2).")

    factors = data.get("factors") or []
    seen = set()
    log_sum = 0.0
    for f in factors:
        key = f.get("key")
        if key not in FACTOR_KEYS:
            err(f"[응답] 허용되지 않은 factor key: {key} (허용: {sorted(FACTOR_KEYS)})")
        if key in seen:
            err(f"[응답] factor key 중복: {key}")
        seen.add(key)

        if not f.get("evidence"):
            err(f"[응답] factor '{key}' 에 evidence 가 없습니다. 설명 없는 점수는 반환 금지입니다.")
        elif len(str(f["evidence"])) < 10:
            warn(f"[응답] factor '{key}' 의 evidence 가 너무 짧습니다. 실제 피처값을 인용하세요.")

        lc = f.get("log_contribution")
        if not isinstance(lc, (int, float)):
            err(f"[응답] factor '{key}' 의 log_contribution 이 숫자가 아닙니다.")
        else:
            log_sum += lc
            if key == "competition" and lc > 0:
                err(f"[응답] competition 요인은 항상 1 이하여야 합니다 "
                    f"(log_contribution ≤ 0). 현재 {lc}.")

    # 요인 합 일치 검사 (제공된 경우)
    total = data.get("total_log_multiplier")
    if isinstance(total, (int, float)) and abs(log_sum - total) > 1e-6:
        err(f"[응답] 요인 로그 기여도 합({log_sum:.9f})이 "
            f"total_log_multiplier({total:.9f})와 다릅니다. 설명이 거짓이 됩니다.")

    # 온라인 채널 피처 오용
    channel = data.get("channel")
    if channel in {"online_marketplace", "own_mall"}:
        for f in factors:
            ev = str(f.get("evidence", ""))
            if "유동인구" in ev or "foot_traffic" in ev:
                err(f"[응답] 온라인 채널({channel}) 예측에 유동인구 근거가 사용되었습니다.")

    print(f"  응답 검증: 요인 {len(factors)}개, 로그 기여도 합 {log_sum:+.6f}")


# ─────────────────── 6. /predictions/{run_id}/scores 검증 ───────────────────
SCORES_SCHEMA = ["region_id", "opportunity_score", "confidence_level"]

# 03_region_features.json region_hierarchy: 코드 자릿수로 레벨을 판별한다.
_LEVEL_ID_DIGITS = {"sido": (2, 2), "sigungu": (5, 5), "adm_dong": (8, 10)}


def _find_key_deep(node, target: str) -> bool:
    """중첩 구조 어디에든 target 키가 있는지 검사."""
    if isinstance(node, dict):
        if target in node:
            return True
        return any(_find_key_deep(v, target) for v in node.values())
    if isinstance(node, list):
        return any(_find_key_deep(v, target) for v in node)
    return False


def check_scores_response(path: pathlib.Path) -> None:
    """지도용 점수 응답(ADR-001) 검증. 튜플배열+schema 형식이 핵심이다."""
    data = load_json(path)
    if not data:
        return
    if not isinstance(data, dict):
        err("[점수] 최상위가 객체가 아닙니다.")
        return

    for k in ("run_id", "region_level", "boundary_vintage", "schema", "scores", "score_range"):
        if k not in data:
            err(f"[점수] 필수 필드 누락: {k}")

    # 튜플배열 강제 — 객체 배열이면 3,500행에서 키가 반복돼 페이로드가 약 2.5배가 된다.
    rows = data.get("scores")
    if not isinstance(rows, list):
        err("[점수] scores 는 배열이어야 합니다.")
        rows = []
    elif rows and isinstance(rows[0], dict):
        err("[점수] scores 가 객체 배열입니다. 계약은 튜플배열 + schema 형식입니다 "
            '({"schema":["region_id","opportunity_score","confidence_level"], '
            '"scores":[["1111051500",87.4,"high"]]}). '
            "3,500행에서 키 반복이 사라져 페이로드가 약 60% 줄어듭니다.")
        rows = []

    schema = data.get("schema")
    if schema != SCORES_SCHEMA:
        err(f"[점수] schema 가 계약과 다릅니다. 기대 {SCORES_SCHEMA}, 실제 {schema}")

    width = len(schema) if isinstance(schema, list) else len(SCORES_SCHEMA)
    level = data.get("region_level")
    digits = _LEVEL_ID_DIGITS.get(level)

    for i, row in enumerate(rows):
        if not isinstance(row, list):
            err(f"[점수] scores[{i}] 가 배열이 아닙니다: {row!r}")
            continue
        if len(row) != width:
            err(f"[점수] scores[{i}] 길이 {len(row)} != schema 길이 {width}")
            continue

        rid, score, conf = row[0], row[1], row[2]

        if not isinstance(score, (int, float)) or isinstance(score, bool):
            err(f"[점수] scores[{i}] opportunity_score 가 숫자가 아닙니다: {score!r}")
        elif not (0 <= score <= 100):
            err(f"[점수] scores[{i}] opportunity_score 범위 위반: {score} (0~100)")

        if conf not in CONFIDENCE_LEVELS:
            err(f"[점수] scores[{i}] confidence_level 값 위반: {conf!r} (low|medium|high)")

        # region_id 는 자기 레벨을 알 수 있어야 한다 (03_region_features.json rules).
        if digits and isinstance(rid, str) and rid.isdigit():
            lo, hi = digits
            if not (lo <= len(rid) <= hi):
                warn(f"[점수] scores[{i}] region_id '{rid}' 는 {len(rid)}자리인데 "
                     f"region_level={level} 은 {lo}~{hi}자리입니다. 레벨/코드 불일치.")

    # 색상 스케일 고정용. 없으면 필터를 바꿀 때마다 지도 색이 흔들린다.
    rng = data.get("score_range")
    if not isinstance(rng, dict):
        err("[점수] score_range 가 객체가 아닙니다.")
    else:
        for k in ("min", "max"):
            if not isinstance(rng.get(k), (int, float)):
                err(f"[점수] score_range.{k} 가 없습니다. 클라이언트가 색상 스케일을 "
                    "고정하지 못해 필터를 바꿀 때마다 색이 흔들립니다.")

    # 금액은 상세 조회 전용이다.
    if _find_key_deep(data, "expected_revenue_krw"):
        err("[점수] 응답에 expected_revenue_krw 가 있습니다. 지도용 점수 응답에 금액을 담지 "
            "않습니다 (상세 조회 전용, ADR-001).")

    geoms = data.get("custom_geometries")
    if level == "custom_catchment":
        if not geoms:
            err("[점수] region_level=custom_catchment 인데 custom_geometries 가 없습니다.")
    elif geoms is not None:
        err(f"[점수] region_level={level} 인데 custom_geometries 가 채워졌습니다. "
            "표준 행정경계는 전부 타일로 나갑니다 (null 이어야 함).")

    print(f"  점수 응답 검증: {len(rows)}행, level={level}")


# ────────────────── 7. /basemap/regions/manifest 검증 ──────────────────
def check_manifest_response(path: pathlib.Path) -> None:
    """경계 타일 매니페스트(ADR-001) 검증."""
    data = load_json(path)
    if not data:
        return
    if not isinstance(data, dict):
        err("[매니페스트] 최상위가 객체가 아닙니다.")
        return

    for k in ("level", "boundary_vintage", "tile_url", "source_layer",
              "feature_id_property", "minzoom", "maxzoom", "available_vintages"):
        if k not in data:
            err(f"[매니페스트] 필수 필드 누락: {k}")

    fid = data.get("feature_id_property")
    if fid != "region_id":
        err(f"[매니페스트] feature_id_property 는 반드시 'region_id' 여야 합니다. 현재 {fid!r}. "
            "D 가 이 값을 setFeatureState 키로 사용합니다.")

    vintages = data.get("available_vintages")
    if not isinstance(vintages, list) or not vintages:
        err("[매니페스트] available_vintages 가 비어 있습니다. "
            "빈티지를 고를 수 없으면 '최신' 추측이 들어가고 시계열이 어긋납니다.")
    elif data.get("boundary_vintage") not in vintages:
        err(f"[매니페스트] available_vintages 에 boundary_vintage"
            f"({data.get('boundary_vintage')!r}) 가 없습니다: {vintages}")

    url = data.get("tile_url")
    if not isinstance(url, str) or not re.match(r"^https?://", url):
        err(f"[매니페스트] tile_url 은 절대 URL 이어야 합니다: {url!r}")
    else:
        if "/predictions/" in url:
            err("[매니페스트] tile_url 이 /predictions/ 를 가리킵니다. 경계 타일은 예측과 "
                "무관한 정적·공용 아티팩트입니다 (ADR-001).")
        if ".mvt" in url:
            err("[매니페스트] tile_url 이 .mvt 를 가리킵니다. "
                "타일 엔드포인트는 폐기되었고 경계는 정적 .pmtiles 입니다 (ADR-001).")

    for k in ("minzoom", "maxzoom"):
        v = data.get(k)
        if not isinstance(v, int) or isinstance(v, bool):
            err(f"[매니페스트] {k} 가 정수가 아닙니다: {v!r}")
    lo, hi = data.get("minzoom"), data.get("maxzoom")
    if isinstance(lo, int) and isinstance(hi, int) and not isinstance(lo, bool) and lo > hi:
        err(f"[매니페스트] minzoom({lo}) 이 maxzoom({hi}) 보다 큽니다.")

    print(f"  매니페스트 검증: level={data.get('level')}, "
          f"vintage={data.get('boundary_vintage')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="비교 기준 브랜치 (예: origin/master)")
    ap.add_argument("--agent", help="에이전트 식별자 A|B|C|D")
    ap.add_argument("--check-response", type=pathlib.Path, help="예측 응답 JSON 파일 검증")
    ap.add_argument("--check-scores", type=pathlib.Path,
                    help="/predictions/{run_id}/scores 응답 JSON 검증")
    ap.add_argument("--check-manifest", type=pathlib.Path,
                    help="/basemap/regions/manifest 응답 JSON 검증")
    args = ap.parse_args()

    print("SellFinder 계약 검증\n" + "─" * 46)

    check_domain_model()
    check_taxonomy()
    check_feature_registry()

    if args.check_response:
        check_prediction_response(args.check_response)

    if args.check_scores:
        check_scores_response(args.check_scores)

    if args.check_manifest:
        check_manifest_response(args.check_manifest)

    if args.base and args.agent:
        check_boundaries(args.base, args.agent)
    elif args.base or args.agent:
        warn("--base 와 --agent 는 함께 지정해야 경계 검사가 동작합니다.")

    print("─" * 46)
    for w in warnings:
        print(f"경고  {w}")
    for e in errors:
        print(f"오류  {e}")

    if errors:
        print(f"\n실패: 오류 {len(errors)}건, 경고 {len(warnings)}건")
        return 1
    print(f"\n통과: 경고 {len(warnings)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
