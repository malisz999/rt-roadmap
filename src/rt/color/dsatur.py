"""Deterministic colouring over the fixed palette (RS CO-4 to CO-6, 5.2; ADS 6.5).

Order: project pins, then product colours (pinned, else automatic from entries 10–31, then 0–9), then DSATUR over
entries 0–9 for standalone bars, with every bar coloured so far as a pre-coloured neighbour.
"""

from __future__ import annotations

from collections.abc import Mapping

from rt.color.palette import BASE, PALETTE_SIZE, PRODUCT_ORDER, ColorKey, key_label, key_ref, spec_key
from rt.color.types import ColorRef
from rt.diagnostics import Code, Collector
from rt.model.types import ResolvedModel
from rt.schedule.types import Visibility


def product_keys(m: ResolvedModel, diags: Collector) -> dict[str, ColorKey]:
    """Colour key per product id: pins first, then automatic in file order (RS 5.2 step 2); W014 when the
    palette runs out and a product has to share."""
    keys: dict[str, ColorKey] = {}
    taken = [0] * PALETTE_SIZE  # products per palette entry
    for pr in m.products:
        if pr.color is not None:
            key = spec_key(pr.color)
            keys[pr.id] = key
            if isinstance(key, int):
                taken[key] += 1
    for pr in m.products:
        if pr.id in keys:
            continue
        free = [c for c in PRODUCT_ORDER if taken[c] == 0]
        if free:
            choice = free[0]
        else:
            choice = min(range(PALETTE_SIZE), key=lambda c: (taken[c], c))
            first = next(other.name for other in m.products if keys.get(other.id) == choice)
            diags.warning(Code.W014, pr.pos, first=first, second=pr.name, color=key_label(choice), size=PALETTE_SIZE)
        keys[pr.id] = choice
        taken[choice] += 1
    return keys


def assign_keys(
    m: ResolvedModel,
    vis: Mapping[int, Visibility],
    nb: Mapping[int, frozenset[int]],
    diags: Collector,
    products: Mapping[str, ColorKey] | None = None,
) -> dict[int, ColorKey]:
    """Colour key per visible bar: project pins and product colours first (W009), then DSATUR over entries 0–9
    with least-used choice (W007). `products` is the result of product_keys(); computed here when not given."""
    if products is None:
        products = product_keys(m, diags) if m.products else {}
    visible = [p for p in m.projects if (v := vis.get(p.seq)) is not None and v.visible]
    product_of = {p.seq: p.product_id for p in visible}
    keys: dict[int, ColorKey] = {}
    use = [0] * PALETTE_SIZE
    pinned: set[int] = set()
    preset: list[int] = []
    for p in visible:
        if p.color is not None:
            key = spec_key(p.color)
            pinned.add(p.seq)
        elif p.product_id is not None and p.product_id in products:
            key = products[p.product_id]
        else:
            continue
        keys[p.seq] = key
        preset.append(p.seq)
        if isinstance(key, int):
            use[key] += 1
    # W009: two adjacent pre-coloured bars with the same colour, reported once at the later one. Bars of the same
    # product share a colour by design.
    for seq in preset:
        for other in sorted(nb.get(seq, frozenset())):
            if other >= seq or other not in keys or keys[other] != keys[seq]:  # only preset bars have keys yet
                continue
            if product_of[seq] is not None and product_of[seq] == product_of[other]:
                continue
            diags.warning(
                Code.W009,
                m.model.project(seq).pos,
                first=m.model.project(other).name,
                second=m.model.project(seq).name,
                how="pinned to" if seq in pinned and other in pinned else "coloured",
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
        allowed = [c for c in BASE if c not in saturation[seq]]
        if allowed:
            choice = min(allowed, key=lambda c: (use[c], c))
        else:
            choice = min(BASE, key=lambda c: (neighbour_keys.count(c), use[c], c))
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
    m: ResolvedModel,
    vis: Mapping[int, Visibility],
    nb: Mapping[int, frozenset[int]],
    diags: Collector,
    products: Mapping[str, ColorKey] | None = None,
) -> dict[int, ColorRef]:
    """Visible bar seq → its colours; hidden bars are absent (null colour in the plan)."""
    return {seq: key_ref(key) for seq, key in assign_keys(m, vis, nb, diags, products).items()}
