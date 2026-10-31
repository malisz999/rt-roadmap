"""Choose a team for each flexible project so the rt schedule is as good as possible.

rt itself is the scoring function: every candidate assignment is written to a temporary file and scheduled with
`rt validate --plan -`, so the optimiser sees exactly the delays, slots and dependencies rt will draw.

Usage:
  python allocate.py ROADMAP.yaml CANDIDATES.yaml [-o OUT.yaml] [--rt "CMD"] [--max-evals N]
                     [--w-delay 1] [--w-flow 0.2] [--w-makespan 0.5] [--w-affinity 10] [--w-move 0]

ROADMAP.yaml   a valid rt input file; its `team` values are the starting assignment.
CANDIDATES.yaml maps a project id or name to the team ids it may go to, best first; "*" = any team:
                  blik-recurring: [blik, app]
                  "Widżety Android": "*"
               Projects not listed keep their team.

Writes the improved file to OUT.yaml or stdout, and a report to stderr. Only the `team` values change; every
other byte of the file (comments, quoting, layout) stays as it was.
Needs ruamel.yaml (`uv run --with ruamel.yaml python allocate.py …` works anywhere uv is installed).
Exit codes: 0 done, 1 the input is invalid for rt, 2 usage error.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

INFEASIBLE = float("inf")
SCALAR = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^']|'')*'|[^\s#,}\]]+")


# --------------------------------------------------------------------------- finding rt


def rt_command(explicit: str | None) -> list[str]:
    """--rt, then $RT_CMD, then `rt` on PATH, then `python -m rt`, then the repository this skill lives in."""
    if explicit:
        return shlex.split(explicit)
    if os.environ.get("RT_CMD"):
        return shlex.split(os.environ["RT_CMD"])
    if shutil.which("rt"):
        return ["rt"]
    if importlib.util.find_spec("rt") is not None:  # installed for this interpreter, scripts dir not on PATH
        return [sys.executable, "-m", "rt"]
    for root in Path(__file__).resolve().parents:
        if (root / "pyproject.toml").exists() and 'name = "rt-roadmap"' in (root / "pyproject.toml").read_text():
            venv = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if venv.exists():
                return [str(venv), "-m", "rt"]
            return ["uv", "run", "--project", str(root), "rt"]
    sys.exit("allocate: rt not found; install it, put it on PATH, or pass --rt / set RT_CMD")


# --------------------------------------------------------------------------- model


@dataclass
class Flexible:
    index: int  # position in projects[]
    label: str
    teams: list[str]  # allowed team ids, best first
    original: str


@dataclass
class Score:
    total: float
    delay: int = 0
    flow: int = 0
    makespan: int = 0
    overflow: int = 0
    off_domain: int = 0
    moved: int = 0
    error: str = ""


def load_yaml(path: Path) -> Any:
    yaml = YAML()
    yaml.preserve_quotes = True
    return yaml.load(path.read_text(encoding="utf-8-sig"))


class Source:
    """The roadmap text with the position of every project's `team` value, so assignments are written by
    replacing just those scalars."""

    def __init__(self, text: str, doc: Any) -> None:
        self.lines = text.splitlines(keepends=True)
        self.spots: list[tuple[int, int, int]] = []  # (line, start col, end col) per project, 0-based
        for p in doc.get("projects") or []:
            line, col = p.lc.value("team")
            m = SCALAR.match(self.lines[line], col)
            if m is None:
                sys.exit(f"allocate: cannot locate the team of project at line {line + 1}")
            self.spots.append((line, col, m.end()))

    def render(self, teams: list[str] | tuple[str, ...]) -> str:
        lines = list(self.lines)
        # right to left within a line, so earlier columns stay valid
        for (line, start, end), team in sorted(zip(self.spots, teams, strict=True), key=lambda x: -x[0][1]):
            lines[line] = lines[line][:start] + team + lines[line][end:]
        return "".join(lines)


def team_subdomains(doc: Any) -> dict[str, str]:
    return {t["id"]: sd["id"] for sd in doc.get("subdomains") or [] for t in sd.get("teams") or []}


def product_domains(doc: Any) -> dict[str, str]:
    return {p["id"]: p["domain"] for p in doc.get("products") or []}


def flexible_projects(doc: Any, candidates: Any) -> list[Flexible]:
    teams = list(team_subdomains(doc))
    projects = doc.get("projects") or []
    keys: dict[str, int] = {}
    for i, p in enumerate(projects):
        if p.get("id"):
            keys[str(p["id"])] = i
        keys.setdefault(str(p["name"]), i)
    out: list[Flexible] = []
    for key, allowed in (candidates or {}).items():
        if str(key) not in keys:
            sys.exit(f'allocate: candidates name unknown project "{key}"')
        i = keys[str(key)]
        allowed_list = teams if allowed in ("*", ["*"]) else [str(a) for a in allowed]
        unknown = [t for t in allowed_list if t not in teams]
        if unknown:
            sys.exit(f'allocate: project "{key}": unknown team(s) {", ".join(unknown)}; teams are {", ".join(teams)}')
        original = str(projects[i]["team"])
        out.append(Flexible(i, str(projects[i]["name"]), allowed_list, original))
    return sorted(out, key=lambda f: f.index)  # file order = rt priority


# --------------------------------------------------------------------------- scoring with rt


class Evaluator:
    def __init__(
        self, doc: Any, text: Source, rt: list[str], weights: argparse.Namespace, workdir: Path, source: Path
    ) -> None:
        self.doc = doc
        self.text = text
        self.rt = rt
        self.w = weights
        self.path = workdir / source.name
        self.source = source  # rt messages name the user's file, not the temporary copy
        self.cache: dict[tuple[str, ...], Score] = {}
        self.evals = 0
        self.sub_of_team = team_subdomains(doc)
        self.domain_of_product = product_domains(doc)
        self.original = [str(p["team"]) for p in doc.get("projects") or []]
        self.ref: int | None = None  # finish times are counted in days from the first plan's horizon start

    def plan(self, assignment: tuple[str, ...]) -> tuple[int, dict[str, Any] | None, str]:
        self.path.write_text(self.text.render(assignment), encoding="utf-8")
        proc = subprocess.run(
            [*self.rt, "validate", str(self.path), "--plan", "-", "-q"], capture_output=True, check=False
        )
        self.evals += 1
        stderr = proc.stderr.decode("utf-8", "replace").replace(str(self.path), str(self.source))
        if proc.returncode != 0:
            return proc.returncode, None, stderr
        return 0, json.loads(proc.stdout.decode("utf-8")), stderr

    def score(self, assignment: tuple[str, ...]) -> Score:
        if assignment in self.cache:
            return self.cache[assignment]
        code, plan, stderr = self.plan(assignment)
        if code == 3:  # E060/E061: this assignment cannot be scheduled
            result = Score(INFEASIBLE, error=stderr.strip())
        elif code != 0 or plan is None:
            sys.stderr.write(stderr)
            sys.exit("allocate: rt rejected the input; fix the errors above first")
        else:
            result = self.metrics(plan, assignment)
        self.cache[assignment] = result
        return result

    def metrics(self, plan: dict[str, Any], assignment: tuple[str, ...]) -> Score:
        projects = plan["projects"]
        delay = sum(p["delay_days"] for p in projects)
        if self.ref is None:
            self.ref = date.fromisoformat(plan["horizon"]["start_date"]).toordinal()
        ends = [date.fromisoformat(p["end"]).toordinal() - self.ref for p in projects if p["end"]]
        flow = sum(ends)  # sum of finish days: lower = work done sooner
        makespan = max(ends, default=0)
        overflow = sum(1 for p in projects if "over_capacity" in p["flags"])
        off_domain = 0
        for p, team in zip(projects, assignment, strict=True):
            product = p.get("product")
            if product and self.domain_of_product.get(product) != self.sub_of_team.get(team):
                off_domain += 1
        moved = sum(1 for a, b in zip(assignment, self.original, strict=True) if a != b)
        w = self.w
        total = (
            w.w_delay * delay
            + w.w_flow * flow
            + w.w_makespan * makespan
            + 1000 * overflow
            + w.w_affinity * off_domain
            + w.w_move * moved
        )
        return Score(total, delay, flow, makespan, overflow, off_domain, moved)


# --------------------------------------------------------------------------- search


def optimise(ev: Evaluator, flex: list[Flexible], start: list[str], max_evals: int) -> list[str]:
    """Greedy in file order (each flexible project takes its best team given the ones before it), then
    first-improvement local search with single moves and pairwise swaps until nothing improves."""
    current = list(start)
    best = ev.score(tuple(current))
    for f in flex:  # greedy pass
        for team in f.teams:
            if ev.evals >= max_evals:
                return current
            trial = list(current)
            trial[f.index] = team
            s = ev.score(tuple(trial))
            if s.total < best.total:
                current, best = trial, s
    improved = True
    while improved and ev.evals < max_evals:
        improved = False
        for f in flex:  # single moves
            for team in f.teams:
                if team == current[f.index] or ev.evals >= max_evals:
                    continue
                trial = list(current)
                trial[f.index] = team
                s = ev.score(tuple(trial))
                if s.total < best.total:
                    current, best, improved = trial, s, True
        for i, a in enumerate(flex):  # swaps: two projects exchange teams
            for b in flex[i + 1 :]:
                ta, tb = current[a.index], current[b.index]
                if ta == tb or ta not in b.teams or tb not in a.teams or ev.evals >= max_evals:
                    continue
                trial = list(current)
                trial[a.index], trial[b.index] = tb, ta
                s = ev.score(tuple(trial))
                if s.total < best.total:
                    current, best, improved = trial, s, True
    return current


def describe(s: Score) -> str:
    if s.total == INFEASIBLE:
        return "infeasible (rt could not schedule it)"
    return (
        f"score {s.total:.1f} · delay {s.delay} d · total finish {s.flow} d · last finish day {s.makespan}"
        f" · overflow {s.overflow} · off-domain {s.off_domain} · moved {s.moved}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("roadmap", type=Path)
    ap.add_argument("candidates", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--rt", help='command that runs rt, e.g. "uv run rt" (default: auto-detect)')
    ap.add_argument("--max-evals", type=int, default=600, help="rt runs at most (default 600)")
    ap.add_argument("--w-delay", type=float, default=1.0, help="per day of delay past a requested start")
    ap.add_argument("--w-flow", type=float, default=0.2, help="per day of each project's finish date")
    ap.add_argument("--w-makespan", type=float, default=0.5, help="per day of the last finish date")
    ap.add_argument("--w-affinity", type=float, default=10.0, help="per product project outside its domain")
    ap.add_argument("--w-move", type=float, default=0.0, help="per project moved away from its current team")
    args = ap.parse_args()

    raw = args.roadmap.read_text(encoding="utf-8-sig")
    doc = load_yaml(args.roadmap)
    text = Source(raw, doc)
    flex = flexible_projects(doc, load_yaml(args.candidates))
    if not flex:
        print("allocate: no flexible projects in the candidates file", file=sys.stderr)
        return 2
    rt = rt_command(args.rt)
    with tempfile.TemporaryDirectory() as tmp:
        ev = Evaluator(doc, text, rt, args, Path(tmp), args.roadmap)
        start = list(ev.original)
        for f in flex:  # a project whose current team is not allowed starts on its first candidate
            if start[f.index] not in f.teams:
                start[f.index] = f.teams[0]
        before = ev.score(tuple(ev.original))
        result = optimise(ev, flex, start, args.max_evals)
        after = ev.score(tuple(result))
        if after.total > before.total:  # never hand back something worse than the input
            result, after = list(ev.original), before

    out = text.render(result)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)

    print(f"allocate: {ev.evals} rt runs, {len(flex)} flexible projects", file=sys.stderr)
    print(f"  before: {describe(before)}", file=sys.stderr)
    print(f"  after:  {describe(after)}", file=sys.stderr)
    for f in flex:
        if result[f.index] != f.original:
            print(f'  moved "{f.label}": {f.original} -> {result[f.index]}', file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
