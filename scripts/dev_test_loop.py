#!/usr/bin/env python3
"""Developer <-> tester loop for the rt project, driven by headless Claude Code (`claude -p`).

One milestone per run:
  1. tester writes the milestone's acceptance tests (they fail at first),
  2. developer implements / fixes until the tests pass,
  3. tester re-runs everything, reviews the HTML, files or verifies defects,
  4. repeat 2-3 until the tester says PASS and the gates are green, or a stop rule fires.

The script (not the agents) commits after every turn, enforces file ownership and runs the
quality gates, so the referee is the test suite, not an agent's opinion.

Usage:
  python scripts/dev_test_loop.py --milestone M3 [--max-rounds 5] [--budget 5] [--model opus]
Requires: git, uv, Claude Code CLI (`claude`) logged in, a clean working tree.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "work" / "loop-log.md"

# Milestones and acceptance tests, from the architecture spec, section 12.
MILESTONES: dict[str, tuple[str, list[int]]] = {
    "M1": ("Skeleton and streams: pyproject, CLI with all commands stubbed, IOPort with stdin/stdout, "
           "diagnostics, io.loader, timeutil, decimalutil; `rt schema`, `rt init`; E001 and E003 fixtures",
           [18, 21, 39, 40, 41]),
    "M2": ("Validation: model.build, model.references, partial models, every E0xx code, "
           "`validate --format json`", [14, 15, 16, 20, 32, 42]),
    "M3": ("Scheduling and plan JSON (colour fields masked in AT-01 for now), --plan incl. `--plan -`, "
           "differential test against docs/reference/reference_plan.py", [1, 7, 8, 9, 12, 26, 27, 28, 30, 31, 38]),
    "M4": ("Colouring: adjacency, DSATUR, palette, pinned colours", [1, 10, 11]),
    "M5": ("Core HTML: header, legend, scale with quarters, sections, teams, lanes, bars and states, "
           "Today line, warnings, print, dark mode; HTML to stdout",
           [2, 3, 4, 5, 6, 13, 17, 19, 22, 23, 24, 33, 37, 43, 44, 45, 46]),
    "M6": ("Dependency connectors and the ↤ glyph, --summary section, content_language", [29, 34, 35, 36]),
    "M7": ("CSV conversion `rt convert`: convert/*, RawDoc.source_of, convert options, E101-E107, W020, W021, "
           "differential test against docs/reference/reference_convert.py", [47, 48, 49, 50, 51, 52, 53, 54, 55]),
    "M8": ("Hardening: performance tests (NF-3, NF-11), cross-OS stream behaviour (NF-12), packaging, README",
           [25]),
}

OWNERSHIP = {
    "developer": ("src/", "tests/unit/", "tests/property/", "tools/", "pyproject.toml", "uv.lock",
                  "work/handoff/developer.md"),
    "tester": ("tests/acceptance/", "tests/golden/", "tests/html/", "tests/cli/", "tests/fixtures/",
               "tests/conftest.py", "work/defects/", "work/handoff/tester.md", "work/questions.md"),
}

ALLOWED_TOOLS = ",".join([
    "Read", "Edit", "Write", "Glob", "Grep",
    "Bash(uv run *)", "Bash(uv sync *)", "Bash(uv add *)",
    "Bash(git status *)", "Bash(git diff *)", "Bash(git log *)", "Bash(ls *)",
    "Bash(cat *)", "Bash(head *)", "Bash(printf *)", "Bash(diff *)",
])

GATES = [
    ("ruff", ["uv", "run", "ruff", "check", "."]),
    ("format", ["uv", "run", "ruff", "format", "--check", "."]),
    ("mypy", ["uv", "run", "mypy", "src"]),
    ("pytest", ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"]),
]


# ---------------------------------------------------------------- helpers
def sh(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=check)


def log(text: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text, flush=True)


def changed_files() -> list[tuple[str, str]]:
    """(status, path) for every change since the last commit, untracked files included."""
    out = sh(["git", "status", "--porcelain", "--untracked-files=all"]).stdout
    files = []
    for line in out.splitlines():
        status, path = line[:2], line[3:]
        if " -> " in path:                      # rename: keep the new path
            path = path.split(" -> ", 1)[1]
        files.append((status, path.strip('"')))
    return files


def enforce_ownership(role: str) -> list[str]:
    """Revert every change the role made outside its own paths; return what was reverted."""
    reverted = []
    for status, path in changed_files():
        if path.startswith("work/loop-log.md") or any(path.startswith(p) for p in OWNERSHIP[role]):
            continue
        if status == "??":
            (ROOT / path).unlink(missing_ok=True)
        else:
            sh(["git", "restore", "--source=HEAD", "--staged", "--worktree", "--", path])
        reverted.append(path)
    return reverted


def commit(message: str) -> None:
    sh(["git", "add", "-A"])
    if sh(["git", "diff", "--cached", "--quiet"], check=False).returncode != 0:
        sh(["git", "commit", "-m", message])


def run_gates() -> tuple[bool, str, int | None]:
    """Run all quality gates; return (all_green, summary_for_prompts, failed_test_count)."""
    lines, green, failed = [], True, None
    for name, cmd in GATES:
        res = sh(cmd, check=False)
        ok = res.returncode == 0
        green &= ok
        tail = "\n".join((res.stdout + res.stderr).strip().splitlines()[-25:])
        lines.append(f"### {name}: {'PASS' if ok else 'FAIL'}\n{tail if not ok or name == 'pytest' else ''}")
        if name == "pytest":
            m = re.search(r"(\d+) failed", res.stdout)
            failed = int(m.group(1)) if m else (0 if ok else None)
    return green, "\n".join(lines), failed


def call_agent(role: str, prompt: str, session: str | None, budget: float, model: str | None) -> tuple[str, str]:
    cmd = ["claude", "-p", prompt, "--agent", role, "--output-format", "json",
           "--permission-mode", "acceptEdits", "--allowedTools", ALLOWED_TOOLS,
           "--max-budget-usd", str(budget)]
    if model:
        cmd += ["--model", model]
    if session:
        cmd += ["--resume", session]           # each role keeps its own memory across rounds
    res = sh(cmd, check=False)
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"{role} run failed (exit {res.returncode}):\n{res.stdout}\n{res.stderr}")
    log(f"- {role}: cost ≈ ${data.get('total_cost_usd', 0):.2f}, session {data.get('session_id')}")
    return data.get("result", ""), data.get("session_id", session)


def first_line(text: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(\S+)", text, re.MULTILINE)
    return m.group(1) if m else "UNKNOWN"


# ---------------------------------------------------------------- prompts
def tester_kickoff(ms: str, scope: str, ats: list[int]) -> str:
    at_list = ", ".join(f"AT-{n:02d}" for n in ats)
    return (f"Milestone {ms}: {scope}.\n"
            f"Write the acceptance tests for {at_list} (requirements section 11) plus fixtures for the error and "
            f"warning codes this milestone covers. Keep all earlier milestones' tests. Tests for features not built "
            f"yet are expected to fail. Do not read src/. Finish with the VERDICT block from your instructions.")


def developer_turn(ms: str, scope: str, ats: list[int], gates: str, feedback: str) -> str:
    at_list = ", ".join(f"AT-{n:02d}" for n in ats)
    return (f"{feedback}Milestone {ms}: {scope}.\n"
            f"Make {at_list} and all earlier tests pass and fix open defects in work/defects/ for this milestone. "
            f"Current quality-gate results:\n{gates}\n"
            f"Write work/handoff/developer.md and finish with the STATUS block from your instructions.")


def tester_turn(ms: str, rnd: int, gates: str, feedback: str, dev_summary: str) -> str:
    return (f"{feedback}Milestone {ms}, review round {rnd}. The developer reports:\n{dev_summary}\n\n"
            f"Quality-gate results after the developer's turn:\n{gates}\n"
            f"Verify fixed defects, run exploratory checks on the rendered HTML, file new defects, answer disputed "
            f"tests in work/handoff/tester.md, and finish with the VERDICT block from your instructions.")


def violation_note(reverted: list[str]) -> str:
    if not reverted:
        return ""
    return ("NOTE FROM ORCHESTRATOR: your last turn changed files you do not own; they were reverted: "
            + ", ".join(reverted) + ". Ask the other role through your handoff file instead.\n\n")


# ---------------------------------------------------------------- main loop
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--milestone", required=True, choices=sorted(MILESTONES))
    ap.add_argument("--max-rounds", type=int, default=5)
    ap.add_argument("--budget", type=float, default=5.0, help="USD cap per agent turn")
    ap.add_argument("--model", default=None, help="e.g. opus or sonnet; default = your Claude Code default")
    args = ap.parse_args()

    if changed_files():
        print("Working tree not clean; commit or stash first.", file=sys.stderr)
        return 2
    ms = args.milestone
    scope, ats = MILESTONES[ms]
    log(f"\n## {ms} — started {datetime.now():%Y-%m-%d %H:%M}")

    sessions: dict[str, str | None] = {"developer": None, "tester": None}
    feedback = {"developer": "", "tester": ""}

    # 1. tester writes the milestone's tests first
    _, sessions["tester"] = call_agent("tester", tester_kickoff(ms, scope, ats), None, args.budget, args.model)
    feedback["tester"] = violation_note(enforce_ownership("tester"))
    commit(f"test({ms}): acceptance tests")

    history: list[int | None] = []
    for rnd in range(1, args.max_rounds + 1):
        log(f"### Round {rnd}")
        _, gates, _ = run_gates()

        # 2. developer implements / fixes
        dev_out, sessions["developer"] = call_agent(
            "developer", developer_turn(ms, scope, ats, gates, feedback["developer"]),
            sessions["developer"], args.budget, args.model)
        feedback["developer"] = violation_note(enforce_ownership("developer"))
        commit(f"feat({ms}): round {rnd}")
        status = first_line(dev_out, "STATUS")
        green, gates, failed = run_gates()
        history.append(failed)
        log(f"- developer STATUS: {status}; gates {'green' if green else 'red'}; failed tests: {failed}")

        if status == "BLOCKED":
            log("- stop: developer is BLOCKED — see work/handoff/developer.md")
            return 1

        # 3. tester reviews
        test_out, sessions["tester"] = call_agent(
            "tester", tester_turn(ms, rnd, gates, feedback["tester"], dev_out),
            sessions["tester"], args.budget, args.model)
        feedback["tester"] = violation_note(enforce_ownership("tester"))
        commit(f"test({ms}): review round {rnd}")
        verdict = first_line(test_out, "VERDICT")
        green, gates, failed = run_gates()
        log(f"- tester VERDICT: {verdict}; gates {'green' if green else 'red'}")

        if verdict == "PASS" and green:
            log(f"- {ms} DONE in {rnd} round(s). Human review: read work/defects, run `uv run rt render` "
                f"on docs/fixtures, then merge.")
            return 0

        # stop rule: no progress for two rounds in a row
        if len(history) >= 3 and history[-1] is not None and history[-3] is not None \
                and history[-1] >= history[-3]:
            log("- stop: failing-test count has not dropped for two rounds; human decision needed")
            return 1

    log(f"- stop: {args.max_rounds} rounds without PASS; see work/defects and both handoff files")
    return 1


if __name__ == "__main__":
    sys.exit(main())
