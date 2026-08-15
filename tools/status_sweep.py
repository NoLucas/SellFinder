#!/usr/bin/env python3
"""
SellFinder 상태 스윕 — 저장소에서 '사실'만 읽어 리포트를 만든다.

총괄자(orchestrator)의 1차 도구. 에이전트의 자기 보고는 검증할 주장일 뿐이므로,
이 스크립트는 대화나 기억을 참조하지 않고 git 이력·파일 존재·스크립트 종료코드만 본다.

사용:
    python tools/status_sweep.py
    python tools/status_sweep.py --out orchestrator/STATUS.md

표준 라이브러리만 사용한다. Windows(cp949 콘솔) 에서도 깨지지 않도록
서브프로세스와 표준출력을 모두 utf-8/errors=replace 로 고정한다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACTS_DIR = "shared/contracts"
VALIDATOR = ROOT / "tools" / "validate_contracts.py"

AGENTS = {
    "A": "data-platform",
    "B": "intelligence",
    "C": "backend",
    "D": "console",
}

# 에이전트 간 인수인계 산출물: (경로 패턴, 생산자, 소비자들, 설명)
# 소비자가 생산자보다 이른 커밋에 머물러 있으면 '낡음' 후보다.
HANDOFFS = [
    ("intelligence/synthetic/*", "B", ["A", "C", "D"], "공용 합성 픽스처"),
    ("backend/samples/manifest.json", "C", ["D"], "지도 매니페스트 mock"),
    ("backend/samples/scores.json", "C", ["D"], "점수 응답 mock"),
    ("data-platform/**/manifest.json", "A", ["C", "D"], "타일 매니페스트"),
    ("data-platform/**/*.pmtiles", "A", ["D"], "경계 타일 아티팩트"),
]

# 에이전트가 막혔다고 보고할 수 있는 검증기 플래그. 소스에 없으면 미지원이다.
EXPECTED_VALIDATOR_FLAGS = ["--check-response", "--check-scores", "--check-manifest"]

# 검증 에이전트(6번째). A~D 와 지표가 다르므로 §2 표에 넣지 않고 별도 절로 다룬다.
# 산출물이 코드가 아니라 findings 이기 때문이다.
VERIFICATION_DIR = "verification"
FINDINGS_PATH = "verification/FINDINGS.md"
SEVERITIES = ["S1", "S2", "S3", "S4"]
SEVERITY_LABEL = {"S1": "치명", "S2": "심각", "S3": "보통", "S4": "낮음"}


# ────────────────────────────── git 헬퍼 ──────────────────────────────
def git(*args: str) -> str:
    """git 명령 실행. 실패해도 예외를 던지지 않고 빈 문자열을 준다."""
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, ValueError):
        return ""
    if p.returncode != 0:
        return ""
    return (p.stdout or "").strip()


def last_commit(*pathspecs: str) -> dict | None:
    """해당 경로들을 마지막으로 건드린 커밋. 없으면 None.

    git pathspec 은 기본 모드에서 `**` 를 우리가 기대하는 재귀 glob 으로 다루지 않는다.
    호출자가 실제 파일 경로를 풀어서 넘기면 그대로 쓰고, 아니면 :(glob) 매직을 붙인다.
    """
    specs = [f":(glob){p}" if "**" in p else p for p in pathspecs]
    out = git("log", "-1", "--format=%h\x1f%cI\x1f%an\x1f%s", "--", *specs)
    if not out:
        return None
    parts = out.split("\x1f")
    if len(parts) < 4:
        return None
    sha, iso, author, subject = parts[0], parts[1], parts[2], parts[3]
    return {"sha": sha, "iso": iso, "ts": parse_iso(iso), "author": author, "subject": subject}


def commit_count(pathspec: str) -> int:
    out = git("rev-list", "--count", "HEAD", "--", pathspec)
    try:
        return int(out)
    except ValueError:
        return 0


def parse_iso(iso: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(iso)
    except ValueError:
        return None


def short(iso: str) -> str:
    """리포트에 쓸 짧은 시각 표기."""
    d = parse_iso(iso)
    return d.strftime("%m-%d %H:%M") if d else iso


def hours_between(a: dt.datetime | None, b: dt.datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 3600.0


def exists_any(pattern: str) -> list[pathlib.Path]:
    """glob 패턴에 걸리는 실제 파일 목록 (git 추적 여부와 무관하게 디스크 기준)."""
    if "*" in pattern:
        return sorted(p for p in ROOT.glob(pattern) if p.is_file())
    p = ROOT / pattern
    return [p] if p.is_file() else []


# ───────────────────────────── 1. 계약 상태 ─────────────────────────────
def section_contracts(out: list[str]) -> dict:
    out.append("## 1. 계약 상태\n")

    api = ROOT / CONTRACTS_DIR / "04_api_contract.yaml"
    version = "(읽기 실패)"
    if api.is_file():
        text = api.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^\s{2}version:\s*(\S+)", text, re.M)
        if m:
            version = m.group(1)
    out.append(f"- **API 계약 버전**: `{version}` (`{CONTRACTS_DIR}/04_api_contract.yaml`)")

    lc = last_commit(CONTRACTS_DIR)
    if lc:
        out.append(
            f"- **계약 최종 변경**: `{lc['sha']}` {short(lc['iso'])} — {lc['subject']}"
        )
    else:
        out.append("- **계약 최종 변경**: (이력 없음)")

    # 검증기 실행 — 종료코드가 사실이다.
    rc, tail = run_validator()
    status = "통과" if rc == 0 else f"실패 (exit {rc})"
    out.append(f"- **`validate_contracts.py`**: {status}")
    if rc != 0 and tail:
        out.append("")
        out.append("```")
        out.extend(tail)
        out.append("```")

    # 지원 플래그 — 에이전트가 '막혔다'고 말하는 지점
    src = VALIDATOR.read_text(encoding="utf-8", errors="replace") if VALIDATOR.is_file() else ""
    missing = [f for f in EXPECTED_VALIDATOR_FLAGS if f'"{f}"' not in src and f"'{f}'" not in src]
    if missing:
        out.append(f"- **미지원 검증기 플래그**: {', '.join(f'`{f}`' for f in missing)} ← 요청은 있으나 미구현")
    else:
        out.append(f"- **검증기 플래그**: {', '.join(f'`{f}`' for f in EXPECTED_VALIDATOR_FLAGS)} 모두 지원")

    out.append("\n### 계약 변경 이력 (경계 위반 감시)\n")
    hist = git("log", "--format=%h\x1f%cI\x1f%an\x1f%s", "--", CONTRACTS_DIR)
    if not hist:
        out.append("(없음)")
    else:
        out.append("| 커밋 | 시각 | 작성자 | 메시지 |")
        out.append("|---|---|---|---|")
        for line in hist.splitlines():
            parts = line.split("\x1f")
            if len(parts) < 4:
                continue
            sha, iso, author, subject = parts[:4]
            out.append(f"| `{sha}` | {short(iso)} | {author} | {subject} |")
        out.append("")
        out.append("> `shared/contracts/` 는 jin 전용이다. 위 목록에 에이전트 커밋이 있으면 경계 위반이다.")
    out.append("")
    return {"version": version, "contract_commit": lc, "validator_rc": rc, "missing_flags": missing}


def run_validator() -> tuple[int, list[str]]:
    if not VALIDATOR.is_file():
        return (127, ["validate_contracts.py 가 없습니다."])
    try:
        p = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as e:
        return (127, [str(e)])
    combined = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
    return (p.returncode, combined[-15:])


# ─────────────────────────── 2. 에이전트 진행 ───────────────────────────
def section_agents(out: list[str]) -> dict:
    out.append("## 2. 에이전트 진행\n")
    out.append("| 에이전트 | 폴더 | 커밋수 | 마지막 커밋 | 시각 | 메시지 | RECONCILIATION | CCR |")
    out.append("|---|---|---|---|---|---|---|---|")

    info = {}
    for agent, folder in AGENTS.items():
        lc = last_commit(folder)
        n = commit_count(folder)
        recon = (ROOT / folder / "RECONCILIATION.md").is_file()
        ccr = (ROOT / folder / "CONTRACT_CHANGE_REQUEST.md").is_file()
        info[agent] = {"folder": folder, "last": lc, "count": n, "recon": recon, "ccr": ccr}
        out.append(
            f"| **{agent}** | `{folder}` | {n} | "
            f"{'`' + lc['sha'] + '`' if lc else '—'} | "
            f"{short(lc['iso']) if lc else '—'} | "
            f"{lc['subject'] if lc else '(커밋 없음)'} | "
            f"{'있음' if recon else '**없음**'} | "
            f"{'**있음**' if ccr else '없음'} |"
        )
    out.append("")
    return info


# ────────────────────────── 3. 계약 반영 여부 ──────────────────────────
def section_contract_lag(out: list[str], contract_lc: dict | None, agents: dict) -> list[str]:
    out.append("## 3. 계약 반영 여부\n")
    if not contract_lc:
        out.append("계약 커밋 이력이 없어 판정 불가.\n")
        return []

    out.append(
        f"기준: 계약 최종 커밋 `{contract_lc['sha']}` ({short(contract_lc['iso'])}).\n"
    )
    stale = []
    out.append("| 에이전트 | 마지막 커밋 | 계약 이후? | 판정 |")
    out.append("|---|---|---|---|")
    for agent, d in agents.items():
        lc = d["last"]
        if not lc:
            out.append(f"| **{agent}** | — | — | 커밋 없음 |")
            continue
        delta = hours_between(contract_lc["ts"], lc["ts"])
        after = delta is not None and delta >= 0
        if after:
            verdict = f"OK (계약보다 {delta:.1f}h 뒤)"
        else:
            verdict = f"**경고 — 최신 계약 미반영 가능** ({abs(delta):.1f}h 이름)" if delta is not None else "판정 불가"
            stale.append(agent)
        out.append(
            f"| **{agent}** | `{lc['sha']}` {short(lc['iso'])} | {'예' if after else '아니오'} | {verdict} |"
        )
    out.append("")
    if stale:
        out.append(
            f"> 경고 대상: {', '.join(stale)} — 마지막 커밋이 최신 계약보다 이르다. "
            "계약을 읽고 커밋했는지는 이 스윕으로 알 수 없다. 브리프에서 확인을 요구할 것.\n"
        )
    return stale


# ──────────────────────── 4. 인수인계 산출물 ────────────────────────
def tracked_files(rels: list[str]) -> set[str]:
    """git 이 실제로 추적 중인 파일만 추린다. 디스크 존재 != 인수인계 가능."""
    if not rels:
        return set()
    out = git("ls-files", "--", *rels)
    return set(out.splitlines()) if out else set()


def section_handoffs(out: list[str]) -> dict:
    out.append("## 4. 에이전트 간 인수인계 산출물\n")
    out.append(
        "**디스크에 있는 것과 소비자가 가져갈 수 있는 것은 다르다.** "
        "gitignore 된 산출물은 생산자 로컬에만 존재하므로 다른 에이전트에게 도달하지 않는다.\n"
    )
    out.append("| 산출물 | 생산자 | 소비자 | 디스크 | git 추적 | 마지막 갱신 커밋 |")
    out.append("|---|---|---|---|---|---|")

    result = {}
    for pattern, producer, consumers, desc in HANDOFFS:
        files = exists_any(pattern)
        # 실제로 존재하는 파일 경로를 직접 넘긴다 (glob 해석을 git 에 맡기지 않는다).
        rels = [f.relative_to(ROOT).as_posix() for f in files]
        tracked = tracked_files(rels)
        lc = last_commit(*sorted(tracked)) if tracked else None
        untracked = [r for r in rels if r not in tracked]
        result[pattern] = {
            "files": files, "producer": producer, "consumers": consumers,
            "last": lc, "tracked": tracked, "untracked": untracked, "desc": desc,
        }
        if not files:
            track_cell = "—"
        elif not tracked:
            track_cell = f"**0 / {len(rels)} — 전부 미추적**"
        elif untracked:
            track_cell = f"**{len(tracked)} / {len(rels)} — 일부 미추적**"
        else:
            track_cell = f"{len(tracked)} / {len(rels)}"
        out.append(
            f"| `{pattern}`<br/><sub>{desc}</sub> | {producer} | {', '.join(consumers)} | "
            f"{str(len(files)) + '개' if files else '**없음**'} | {track_cell} | "
            f"{('`' + lc['sha'] + '` ' + short(lc['iso'])) if lc else '**—**'} |"
        )
    out.append("")

    blocked = [(p, d) for p, d in result.items() if d["files"] and not d["tracked"]]
    for pattern, d in blocked:
        why = git("check-ignore", "-v", d["untracked"][0]) if d["untracked"] else ""
        out.append(
            f"> **`{pattern}` 은 생산자({d['producer']}) 디스크에만 있고 저장소에 없다.** "
            f"소비자({', '.join(d['consumers'])})는 이 산출물을 가져갈 수 없다."
            + (f"  \n>   무시 규칙: `{why.splitlines()[0]}`" if why else "")
        )
    if blocked:
        out.append("")
    return result


# ───────────────────────── 5. 교차 신선도 ─────────────────────────
def section_cross_freshness(out: list[str], handoffs: dict, agents: dict) -> list[str]:
    out.append("## 5. 교차 신선도 (가장 중요)\n")
    out.append(
        "소비자의 마지막 커밋이 생산자의 산출물보다 이르면, 그 소비자는 최신 산출물을 "
        "보지 못한 상태에서 판단했을 수 있다. 소비자가 제기한 이슈가 이미 해소됐을 가능성이 여기서 나온다.\n"
    )

    flags = []
    for pattern, d in handoffs.items():
        lc = d["last"]
        if not lc:
            continue
        for consumer in d["consumers"]:
            c = agents.get(consumer, {}).get("last")
            if not c:
                continue
            delta = hours_between(c["ts"], lc["ts"])  # 양수면 소비자가 이르다
            if delta is not None and delta > 0:
                flags.append(
                    f"- **{consumer} 는 `{pattern}` 보다 {delta:.1f}시간 이르다.** "
                    f"(생산자 {d['producer']}: `{lc['sha']}` {short(lc['iso'])} / "
                    f"소비자 {consumer}: `{c['sha']}` {short(c['iso'])})  \n"
                    f"  → {consumer} 가 {d['producer']} 의 최신 산출물을 못 봤을 수 있다. "
                    f"{consumer} 가 제기한 {d['producer']} 관련 이슈는 이미 해소됐을 가능성이 있다."
                )

    # 검증 에이전트도 소비자다. 검증자가 A~D 보다 이르면 그 변경은 아직 검증되지 않았다.
    v = last_commit(VERIFICATION_DIR)
    unverified = []
    if v:
        for agent, d in agents.items():
            c = d.get("last")
            if not c:
                continue
            delta = hours_between(v["ts"], c["ts"])  # 양수면 에이전트가 검증자보다 뒤
            if delta is not None and delta > 0:
                unverified.append(
                    f"- **{agent} 의 최신 변경은 아직 검증되지 않았다** "
                    f"({agent}: `{c['sha']}` {short(c['iso'])} / 검증자: `{v['sha']}` {short(v['iso'])} "
                    f"— {delta:.1f}시간 뒤처짐)  \n"
                    f"  → 검증 회차가 {agent} 의 최신 커밋을 아직 보지 않았다. §7 참조."
                )

    if flags:
        out.extend(flags)
    if unverified:
        out.append("")
        out.append("### 검증 신선도\n")
        out.extend(unverified)
    if not flags and not unverified:
        out.append("플래그 없음 — 모든 소비자가 생산자 산출물 이후에 커밋했다.")
    out.append("")
    return flags + unverified


# ────────────────────────── 7. 검증 현황 ──────────────────────────
def parse_findings() -> dict:
    """verification/FINDINGS.md 를 읽어 심각도별 미해결 건수를 센다.

    형식은 verification/CHARTER.md §8 기준:
      `## S1 — 즉시 조치` 아래 `### VF-012 · 제목 (담당)`
      `### VF-018? · ...` 처럼 `?` 가 붙으면 추정이므로 확정 건수에서 제외한다.
      `## 해결 확인됨` 아래는 불릿(`- VF-007 ...`)이다.
    """
    path = ROOT / FINDINGS_PATH
    result = {
        "exists": path.is_file(),
        "open": {s: [] for s in SEVERITIES},
        "tentative": [],
        "resolved": [],
        "unknown": [],
        "round_header": None,
    }
    if not result["exists"]:
        return result

    text = path.read_text(encoding="utf-8", errors="replace")
    section = None
    for raw in text.splitlines():
        line = raw.strip()

        m = re.match(r"^#\s*검증 결과\s*[—-]\s*(.+)$", line)
        if m:
            result["round_header"] = m.group(1).strip()
            continue
        m = re.match(r"^##\s*회차:\s*(.+)$", line)
        if m:
            result["round_header"] = m.group(1).strip()
            continue

        if line.startswith("## "):
            head = line[3:].strip()
            sev = re.match(r"^(S[1-4])\b", head)
            if sev:
                section = sev.group(1)
            elif head.startswith("추정"):
                section = "tentative"
            elif head.startswith("해결"):
                section = "resolved"
            elif head.startswith("확인 불가"):
                section = "unknown"
            else:
                section = None
            continue

        vf = re.search(r"\b(VF-\d+)(\?)?", line)
        if not vf or section is None:
            continue
        vid, uncertain = vf.group(1), bool(vf.group(2))

        if section in SEVERITIES and line.startswith("### "):
            (result["tentative"] if uncertain else result["open"][section]).append(vid)
        elif section == "tentative" and line.startswith("### "):
            result["tentative"].append(vid)
        elif section == "resolved" and line.startswith("- "):
            result["resolved"].append(vid)
        elif section == "unknown" and line.startswith(("- ", "### ")):
            result["unknown"].append(vid)

    return result


def finding_first_seen(vf_id: str) -> dt.datetime | None:
    """해당 VF 번호가 FINDINGS.md 에 처음 등장한 커밋 시각. 미커밋이면 None."""
    out = git("log", "--reverse", "--format=%cI", "-S", vf_id, "--", FINDINGS_PATH)
    if not out:
        return None
    return parse_iso(out.splitlines()[0].strip())


def section_verification(out: list[str], verif: dict, agents: dict) -> None:
    out.append("## 7. 검증 현황\n")
    out.append(
        "검증 에이전트는 산출물이 코드가 아니라 findings 라서 §2 의 에이전트 표와 지표가 다르다. "
        "여기서는 '무엇을 커밋했는가'가 아니라 '무엇이 아직 열려 있는가'를 본다.\n"
    )

    if not verif["exists"]:
        out.append(f"`{FINDINGS_PATH}` 없음 — 검증 에이전트가 아직 회차를 시작하지 않았다.\n")
        return

    lc = last_commit(VERIFICATION_DIR)
    out.append(
        f"- **마지막 `{VERIFICATION_DIR}/` 커밋**: "
        + (f"`{lc['sha']}` {short(lc['iso'])} — {lc['subject']}" if lc else "없음")
    )
    out.append(f"- **FINDINGS.md 회차 표기**: {verif['round_header'] or '(표기 없음)'}")

    total_open = sum(len(v) for v in verif["open"].values())
    out.append("")
    out.append("| S1 치명 | S2 심각 | S3 보통 | S4 낮음 | 미해결 합계 | 추정 | 해결됨 | 확인 불가 |")
    out.append("|---|---|---|---|---|---|---|---|")
    out.append(
        "| "
        + " | ".join(str(len(verif["open"][s])) for s in SEVERITIES)
        + f" | **{total_open}** | {len(verif['tentative'])} | "
        f"{len(verif['resolved'])} | {len(verif['unknown'])} |"
    )
    out.append("")

    # 가장 오래된 미해결 findings 의 나이
    now = dt.datetime.now().astimezone()
    aged = []
    for sev in SEVERITIES:
        for vid in verif["open"][sev]:
            seen = finding_first_seen(vid)
            if seen is not None:
                aged.append((vid, sev, (now - seen).total_seconds() / 86400.0))
    if aged:
        aged.sort(key=lambda t: -t[2])
        vid, sev, age = aged[0]
        out.append(
            f"- **가장 오래된 미해결**: `{vid}` ({sev} {SEVERITY_LABEL[sev]}) — **{age:.1f}일**"
        )
        old = [a for a in aged if a[2] >= 7.0]
        if old:
            out.append(
                f"  - 7일 이상 방치된 항목 {len(old)}건: "
                + ", ".join(f"`{v}`({s})" for v, s, _ in old[:8])
            )
    elif total_open:
        out.append("- **가장 오래된 미해결**: 나이 산출 불가 (아직 커밋되지 않은 findings)")
    else:
        out.append("- **가장 오래된 미해결**: 없음")

    # 마지막 회차 이후 A~D 변경량 → 다음 검증 필요 여부
    folders = [d["folder"] for d in agents.values()]
    if lc:
        changed = git("diff", "--name-only", f"{lc['sha']}..HEAD", "--", *folders)
        files = [f for f in changed.splitlines() if f.strip()] if changed else []
        by_agent: dict[str, int] = {}
        for f in files:
            top = f.split("/", 1)[0]
            by_agent[top] = by_agent.get(top, 0) + 1
        detail = ", ".join(f"{k} {v}개" for k, v in sorted(by_agent.items())) or "없음"
        out.append(f"- **마지막 검증 이후 A~D 변경 파일**: **{len(files)}개** ({detail})")
        if len(files) == 0:
            out.append("  - → 새로 검증할 변경분이 없다. 미해결 항목 재확인만 하면 된다.")
        elif len(files) >= 10:
            out.append("  - → **다음 검증 회차가 필요하다.** 변경분이 쌓였다.")
        else:
            out.append("  - → 변경분이 소량이다. 미해결 항목과 함께 묶어서 보면 된다.")
    else:
        out.append("- **마지막 검증 이후 A~D 변경 파일**: 검증 커밋이 없어 산출 불가")

    if verif["open"]["S1"]:
        out.append("")
        out.append(
            "> **S1 미해결 "
            + str(len(verif["open"]["S1"]))
            + "건: "
            + ", ".join(f"`{v}`" for v in verif["open"]["S1"])
            + "** — 다른 작업보다 우선한다."
        )
    out.append("")


# ────────────────────── 6. jin 결정이 필요한 항목 ──────────────────────
def section_decisions(out: list[str], meta: dict, agents: dict, stale: list[str], flags: list[str], handoffs: dict, verif: dict) -> None:
    out.append("## 6. jin 결정이 필요한 항목\n")
    items = []

    for agent, d in agents.items():
        if d["ccr"]:
            items.append(
                f"**{agent} 의 CONTRACT_CHANGE_REQUEST.md** (`{d['folder']}/CONTRACT_CHANGE_REQUEST.md`) — "
                "계약 변경 요청이 열려 있다. 승인·병합은 jin 만 가능하다."
            )
        if not d["recon"]:
            items.append(f"**{agent} 의 RECONCILIATION.md 없음** — STEP 1 리컨실을 아직 제출하지 않았다.")

    if meta["validator_rc"] != 0:
        items.append(
            f"**계약 검증기 실패 (exit {meta['validator_rc']})** — 계약 자체 또는 참조 무결성이 깨졌다. "
            "에이전트 작업보다 먼저 해소해야 한다."
        )

    if meta["missing_flags"]:
        items.append(
            "**검증기 미지원 플래그**: "
            + ", ".join(f"`{f}`" for f in meta["missing_flags"])
            + " — 에이전트가 자동 검증을 못 돌린다. 도구 확장이 필요하다."
        )

    if stale:
        items.append(
            f"**최신 계약 미반영 가능 에이전트**: {', '.join(stale)} — 계약 커밋 이후 커밋이 없다."
        )

    if flags:
        items.append(
            f"**교차 신선도 플래그 {len(flags)}건** — §5 참조. 낡은 정보에 근거한 이슈 제기 가능성."
        )

    for pattern, d in handoffs.items():
        if d["files"] and not d["tracked"]:
            items.append(
                f"**`{pattern}` 인수인계 경로 미정** — 생산자 {d['producer']} 가 만들었으나 "
                f"gitignore 되어 저장소에 없다. 소비자({', '.join(d['consumers'])})가 가져갈 방법이 "
                "정해져 있지 않다. 아티팩트 저장소/CDN 업로드 경로를 확정해야 한다."
            )
        elif not d["files"]:
            items.append(
                f"**`{pattern}` 부재** — 생산자 {d['producer']} 의 산출물이 없어 "
                f"소비자({', '.join(d['consumers'])})가 차단될 수 있다."
            )

    if verif.get("exists") and verif["open"]["S1"]:
        items.insert(0, (
            "**검증자 S1(치명) 미해결 "
            + str(len(verif["open"]["S1"]))
            + "건** — "
            + ", ".join(f"`{v}`" for v in verif["open"]["S1"])
            + ". §7 참조. 다른 모든 항목보다 우선한다."
        ))

    if not items:
        out.append("없음.\n")
        return
    for it in items:
        out.append(f"- {it}")
    out.append("")


# ──────────────────────────────── main ────────────────────────────────
def build_report() -> str:
    head = git("rev-parse", "--short", "HEAD") or "(unknown)"
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "(unknown)"
    dirty = git("status", "--porcelain")
    now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")

    out: list[str] = []
    out.append("# SellFinder — 상태 스윕 (STATUS)\n")
    out.append(
        f"생성: `tools/status_sweep.py` · {now} · 브랜치 `{branch}` · HEAD `{head}`"
        + (" · **워킹트리 변경 있음**" if dirty else " · 워킹트리 깨끗함")
        + "\n"
    )
    out.append(
        "> 이 문서는 저장소에서 기계적으로 읽은 **사실**만 담는다. "
        "에이전트의 자기 보고는 포함하지 않는다. 둘이 다르면 불일치 자체가 보고 대상이다.\n"
    )
    out.append("---\n")

    meta = section_contracts(out)
    out.append("---\n")
    agents = section_agents(out)
    out.append("---\n")
    stale = section_contract_lag(out, meta["contract_commit"], agents)
    out.append("---\n")
    handoffs = section_handoffs(out)
    out.append("---\n")
    flags = section_cross_freshness(out, handoffs, agents)
    out.append("---\n")
    verif = parse_findings()
    section_decisions(out, meta, agents, stale, flags, handoffs, verif)
    out.append("---\n")
    section_verification(out, verif, agents)

    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="SellFinder 상태 스윕")
    ap.add_argument("--out", type=pathlib.Path, help="리포트를 저장할 경로 (예: orchestrator/STATUS.md)")
    args = ap.parse_args()

    report = build_report()

    if args.out:
        dest = args.out if args.out.is_absolute() else (ROOT / args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(report, encoding="utf-8")
        print(f"스윕 완료 → {dest.relative_to(ROOT)}")
    else:
        stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        stream.write(report)
        stream.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
