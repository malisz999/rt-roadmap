"""Adjacency graph over drawn bars (RS CO-1 to CO-3; ADS 6.4)."""

from __future__ import annotations

from collections.abc import Mapping

from rt.model.types import ResolvedModel
from rt.schedule.types import Schedule, Visibility


def lane_indices(m: ResolvedModel, lane_count: Mapping[str, int]) -> dict[tuple[str, int], tuple[str, int]]:
    """(team id, lane) → (subdomain id, 0-based row within the subdomain section), in render order (CO-2)."""
    out: dict[tuple[str, int], tuple[str, int]] = {}
    for sd in m.subdomains:
        row = 0
        for team in m.teams:
            if team.subdomain_id != sd.id:
                continue
            for lane in range(1, lane_count.get(team.id, team.slots) + 1):
                out[(team.id, lane)] = (sd.id, row)
                row += 1
    return out


def neighbours(
    m: ResolvedModel, s: Schedule, vis: Mapping[int, Visibility], gap_days: int
) -> dict[int, frozenset[int]]:
    """Visible bar seq → seqs of adjacent bars: same section, rows differing by at most 1, gap ≤ gap_days."""
    rows = lane_indices(m, s.lane_count)
    bars: list[tuple[int, str, int, int, int]] = []  # seq, subdomain, row, start ordinal, end ordinal
    for pl in s.placements:
        v = vis[pl.seq]
        if v.start is None or v.end is None:
            continue
        sd, row = rows[(pl.team_id, pl.lane)]
        bars.append((pl.seq, sd, row, v.start.toordinal(), v.end.toordinal()))
    found: dict[int, set[int]] = {b[0]: set() for b in bars}
    for i, (sa, da, ra, a0, a1) in enumerate(bars):
        for sb, db, rb, b0, b1 in bars[i + 1 :]:
            if da != db or abs(ra - rb) > 1:
                continue
            gap = max(a0, b0) - min(a1, b1)
            if gap <= gap_days:
                found[sa].add(sb)
                found[sb].add(sa)
    return {seq: frozenset(nb) for seq, nb in found.items()}
