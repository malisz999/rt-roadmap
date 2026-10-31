"""Summarise an rt plan JSON for a human: horizon, delays, team utilisation, peak monthly load, products, warnings.

Usage:  rt validate roadmap.yaml --plan - -q | python plan_summary.py
        python plan_summary.py plan.json
Standard library only.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def pct(x: float) -> str:
    return f"{round(x * 100)} %"


FLAG_TEXT = {
    "devs_per_slot_high": "DEV per slot high (worse, red)",
    "devs_per_slot_low": "DEV per slot low (better, green)",
    "devs_per_qa_high": "DEV per QA high (worse, red)",
    "devs_per_qa_low": "DEV per QA low (better, green)",
    "no_qa": "no QA (worse, red)",
    "no_capacity": "no capacity given",
}


def num(x: float | None) -> str:
    return "-" if x is None else f"{x:.1f}"


def composition(plan: dict[str, Any]) -> list[str]:
    """Team indicators (rt 1.2+): DEV per slot, DEV per QA, the band they were compared with, and the marks."""
    ind = plan.get("team_indicators")
    if ind is None:
        return []
    out = ["Team composition (DEV per slot · DEV per QA):"]
    for kind, label in (("devs_per_slot", "DEV per slot"), ("devs_per_qa", "DEV per QA")):
        s = ind[kind]
        if s["source"] == "norm":
            band = f"norm {num(s['low'])}–{num(s['high'])}"
        elif s["source"] == "median":
            band = f"median {num(s['median'])}, normal {num(s['low'])}–{num(s['high'])}"
        else:
            band = "not compared (fewer than 3 teams with capacity)"
        out.append(f"  {label}: all teams {num(s['all'])}; {band}")
    for t in plan["teams"]:
        notes = ", ".join(FLAG_TEXT.get(f, f) for f in t.get("indicator_flags", []))
        out.append(
            f"  {t['id']:<16} {num(t.get('devs_per_slot')):>5} · {num(t.get('devs_per_qa')):>5}"
            + (f"  <- {notes}" if notes else "")
        )
    return out


def summarise(plan: dict[str, Any]) -> str:
    h = plan["horizon"]
    projects = plan["projects"]
    out = [f"{plan['title']} — {h['start']} to {h['end']} ({plan['on_conflict']} mode, today {plan['today']})"]
    finite = [p for p in projects if p["end"]]
    last = max((p["last_day"] for p in finite), default="-")
    out.append(f"{len(projects)} projects ({len(projects) - len(finite)} ongoing); last finite day {last}")

    delayed = sorted((p for p in projects if p["delay_days"] > 0), key=lambda p: -p["delay_days"])
    if delayed:
        out.append(f"Delayed ({len(delayed)}, {sum(p['delay_days'] for p in delayed)} days in total):")
        out += [f"  +{p['delay_days']:>3} d  {p['name']} [{p['team']}] — {p['delay_reason']}" for p in delayed]
    else:
        out.append("No project starts later than requested.")
    over = [p["name"] for p in projects if "over_capacity" in p["flags"]]
    if over:
        out.append(f"Over capacity: {', '.join(over)}")
    hidden = [p["name"] for p in projects if "hidden" in p["flags"]]
    if hidden:
        out.append(f"Outside the horizon (not drawn): {', '.join(hidden)}")

    count: dict[str, int] = defaultdict(int)
    for p in projects:
        count[p["team"]] += 1
    loads = {t["team"]: t["load"] for t in plan["monthly_load"]["teams"]}
    months = plan["monthly_load"]["months"]
    out.append("Teams (utilisation over the horizon · busiest month · projects):")
    for t in plan["teams"]:
        load = loads.get(t["id"], [])
        peak = max(range(len(load)), key=lambda i: load[i]) if load else None
        busiest = f"{months[peak]} {pct(load[peak])}" if peak is not None else "-"
        out.append(
            f"  {t['id']:<16} {pct(t['utilization']):>6} · {busiest:<14} · {count[t['id']]} projects"
            f" · {t['slots']} slots" + (f" + {t['overflow_lanes']} overflow" if t["overflow_lanes"] else "")
        )
    out += composition(plan)
    idle = [t["id"] for t in plan["teams"] if t["utilization"] < 0.3]
    busy = [t["id"] for t in plan["teams"] if t["utilization"] > 0.85]
    if idle and busy:
        out.append(f"Imbalance: {', '.join(busy)} near full while {', '.join(idle)} under 30 %")

    if plan.get("products"):
        by_seq = {p["seq"]: p for p in projects}
        out.append("Products:")
        for pr in plan["products"]:
            teams = sorted({by_seq[s]["team"] for s in pr["projects"]})
            ends = [by_seq[s]["last_day"] for s in pr["projects"] if by_seq[s]["last_day"]]
            out.append(
                f"  {pr['name']} (domain {pr['domain']}, {pr['color_name'] or pr['color_fill']}): "
                f"{len(pr['projects'])} projects in {', '.join(teams) or '-'}; done by {max(ends, default='-')}"
            )
    if plan["warnings"]:
        out.append(f"Warnings ({len(plan['warnings'])}):")
        out += [f"  {w['code']} line {w['line']}: {w['message']}" for w in plan["warnings"]]
    return "\n".join(out)


def main() -> int:
    text = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else sys.stdin.read()
    if not text.strip():
        print("plan_summary: empty input (did rt fail?)", file=sys.stderr)
        return 1
    print(summarise(json.loads(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
