"""Deterministic DSATUR colouring over the fixed palette (RS CO-4 to CO-6; ADS 6.5)."""

from __future__ import annotations

from collections.abc import Mapping

from rt.color.palette import PALETTE_SIZE, ColorKey, key_label, key_ref, spec_key
from rt.color.types import ColorRef
from rt.diagnostics import Code, Collector
from rt.model.types import ResolvedModel
from rt.schedule.types import Visibility


def assign_keys(
    m: ResolvedModel, vis: Mapping[int, Visibility], nb: Mapping[int, frozenset[int]], diags: Collector
) -> dict[int, ColorKey]:
    """Colour key per visible bar: pinned colours first (W009), then DSATUR with least-used choice (W007)."""
    visible = [p for p in m.projects if (v := vis.get(p.seq)) is not None and v.visible]
    keys: dict[int, ColorKey] = {}
    use = [0] * PALETTE_SIZE
    pinned: list[int] = []
    for p in visible:
        if p.color is None:
            continue
        key = spec_key(p.color)
        keys[p.seq] = key
        pinned.append(p.seq)
        if isinstance(key, int):
            use[key] += 1
    for seq in pinned:  # W009: two adjacent bars pinned to the same colour, reported once at the later one
        for other in sorted(nb.get(seq, frozenset())):
            if other < seq and other in keys and keys[other] == keys[seq]:  # only pinned bars have keys yet
                diags.warning(
                    Code.W009,
                    m.model.project(seq).pos,
                    first=m.model.project(other).name,
                    second=m.model.project(seq).name,
                    color=key_label(keys[seq]),
                )
    saturation: dict[int, set[ColorKey]] = {p.seq: set() for p in visible}
    for seq, key in keys.items():
        for n in nb.get(seq, frozenset()):
            if n in saturation:
                saturation[n].add(key)
    uncoloured = {p.seq for p in visible if p.seq not in keys}
    degree = {seq: len(nb.get(seq, frozenset())) for seq in uncoloured}
    while uncoloured:
        seq = min(uncoloured, key=lambda s: (-len(saturation[s]), -degree[s], s))
        neighbour_keys = [keys[n] for n in nb.get(seq, frozenset()) if n in keys]
        allowed = [c for c in range(PALETTE_SIZE) if c not in saturation[seq]]
        if allowed:
            choice = min(allowed, key=lambda c: (use[c], c))
        else:
            choice = min(range(PALETTE_SIZE), key=lambda c: (neighbour_keys.count(c), use[c], c))
            diags.warning(
                Code.W007, m.model.project(seq).pos, project=m.model.project(seq).name, color=key_label(choice)
            )
        keys[seq] = choice
        use[choice] += 1
        uncoloured.discard(seq)
        for n in nb.get(seq, frozenset()):
            if n in saturation:
                saturation[n].add(choice)
    return keys


def assign_colors(
    m: ResolvedModel, vis: Mapping[int, Visibility], nb: Mapping[int, frozenset[int]], diags: Collector
) -> dict[int, ColorRef]:
    """Visible bar seq → its colours; hidden bars are absent (null colour in the plan)."""
    return {seq: key_ref(key) for seq, key in assign_keys(m, vis, nb, diags).items()}
