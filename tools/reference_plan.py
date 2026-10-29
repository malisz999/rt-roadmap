"""rt reference plan oracle — TEST TOOLING ONLY, never import from src/.

Produced the expected plan files scheduling-worked-example.expected.json,
dependencies-example.expected.json and products-example.expected.json
(requirements spec sections 4, 5, 7.12, 8).

Implements: scheduling in delay and overflow modes, auto-start anchor,
finish-to-start dependencies, automatic horizon, visibility and flags,
adjacency, product colours and DSATUR colouring (palette names only),
utilisation and monthly load with half-up rounding,
W001-W005/W007/W009/W011/W013/W014 warnings.
Does NOT implement: input validation (assumes a valid file), error mode,
custom hex colours, W006/W008-W010/W012, horizon cap.

Usage: python reference_plan.py INPUT.yaml [on_conflict=overflow] [hfrom=YYYY-MM] [hto=YYYY-MM]
Requires: ruamel.yaml
"""
import sys, json, calendar, datetime as dt
from fractions import Fraction
from decimal import Decimal, ROUND_HALF_UP
def r4(n, d):
    f = Fraction(n, d)
    return float((Decimal(f.numerator) / Decimal(f.denominator)).quantize(Decimal("0.0001"), ROUND_HALF_UP))
from ruamel.yaml import YAML

D = dt.date
PALETTE = [("indigo", "#C7D2FE"), ("green", "#BBF7D0"), ("orange", "#FED7AA"), ("pink", "#FBCFE8"),
           ("sky", "#BAE6FD"), ("amber", "#FDE68A"), ("violet", "#DDD6FE"), ("teal", "#99F6E4"),
           ("lime", "#D9F99D"), ("sand", "#EADBC8"),
           ("blue", "#BFDBFE"), ("cyan", "#A5F3FC"), ("emerald", "#A7F3D0"), ("yellow", "#FEF08A"),
           ("fuchsia", "#F5D0FE"), ("purple", "#E9D5FF"), ("stone", "#E7E5E4"), ("sand-deep", "#D6C3A5"),
           ("indigo-deep", "#A5B4FC"), ("green-deep", "#86EFAC"), ("orange-deep", "#FDBA74"),
           ("pink-deep", "#F9A8D4"), ("sky-deep", "#7DD3FC"), ("amber-deep", "#FCD34D"),
           ("violet-deep", "#C4B5FD"), ("teal-deep", "#5EEAD4"), ("lime-deep", "#BEF264"),
           ("blue-deep", "#93C5FD"), ("cyan-deep", "#67E8F9"), ("emerald-deep", "#6EE7B7"),
           ("fuchsia-deep", "#F0ABFC"), ("purple-deep", "#D8B4FE")]
BASE = list(range(10))                               # standalone bars (DSATUR)
PRODUCT_ORDER = list(range(10, len(PALETTE))) + BASE  # automatic product colours
INF = D(9999, 12, 31)


def month(s):
    s = str(s)
    return D(int(s[:4]), int(s[5:7]), 1)


def add_months(d, n):
    m = d.month - 1 + n
    return D(d.year + m // 12, m % 12 + 1, 1)


def mstr(d):
    return f"{d.year:04d}-{d.month:02d}"


def months_between(a, b):  # inclusive count from month a to month b
    return (b.year - a.year) * 12 + b.month - a.month + 1


def run(path, on_conflict=None, hfrom=None, hto=None):
    y = YAML()  # round-trip loader, YAML 1.2
    doc = y.load(open(path, encoding="utf-8"))
    sizes = dict(doc["sizes"])
    sched = doc.get("scheduling") or {}
    mode = on_conflict or sched.get("on_conflict", "delay")
    gapd = sched.get("adjacency_gap_days", 14)
    teams, lane_order = [], []
    for sd in doc["subdomains"]:
        for t in sd["teams"]:
            teams.append(dict(id=t["id"], subdomain=sd["id"], slots=t["parallel_projects"]))
    tmap = {t["id"]: t for t in teams}
    lanes = {t["id"]: [[] for _ in range(t["slots"])] for t in teams}
    warnings, plan = [], []
    hz0 = doc["roadmap"].get("horizon") or {}
    today0 = doc["roadmap"].get("today")
    anchor = month(hfrom) if hfrom else (month(hz0["start"]) if "start" in hz0 else D(int(str(today0)[:4]), int(str(today0)[5:7]), 1))
    ids = {}
    for seq, p in enumerate(doc["projects"], 1):
        ids[p.get("id", None) or ("#" + str(seq))] = seq
    names = {}
    for seq, p in enumerate(doc["projects"], 1):
        names.setdefault(p["name"], []).append(seq)
    def resolve(ref):
        if ref in ids: return ids[ref]
        assert len(names[ref]) == 1, ref
        return names[ref][0]
    for seq, p in enumerate(doc["projects"], 1):
        line, col = p.lc.line + 1, p.lc.col + 1
        ongoing = bool(p.get("ongoing", False))
        size = None if ongoing else p["size"]
        weeks = None if ongoing else sizes[size]
        auto = "start" not in p
        req = anchor if auto else month(p["start"])
        dl = p.get("depends_on") or []
        dl = [dl] if isinstance(dl, str) else dl
        deps = sorted(resolve(r) for r in dl)
        for dq in deps: assert dq < seq
        dep_ready = max([plan[dq - 1]["end"] for dq in deps], default=req)
        earliest = max(req, dep_ready)
        dur = None if ongoing else dt.timedelta(days=weeks * 7)
        L = lanes[p["team"]]
        nslots = tmap[p["team"]]["slots"]

        def free(lane, s, e):
            return all(not (s < b and a < e) for a, b, _ in lane)

        placed = None
        if mode == "delay" or auto:
            cands = sorted({earliest} | {b for lane in L[:nslots] for _, b, _ in lane if b != INF and b > earliest})
            for t in cands:
                e = INF if ongoing else t + dur
                for i in range(nslots):
                    if free(L[i], t, e):
                        placed = (i, t, e); break
                if placed: break
            if not placed:
                raise SystemExit(f"E060 {p['name']}")
        else:
            e = INF if ongoing else earliest + dur
            for i in range(len(L)):
                if free(L[i], earliest, e):
                    placed = (i, earliest, e); break
            if not placed:
                L.append([]); placed = (len(L) - 1, earliest, e)
        i, s, e = placed
        L[i].append((s, e, seq))
        dep_days = 0 if auto else (earliest - req).days
        cap_days = (s - earliest).days
        reason = None
        if not auto and (dep_days or cap_days):
            reason = "dependency+capacity" if dep_days and cap_days else ("dependency" if dep_days else "capacity")
        plan.append(dict(seq=seq, pid=p.get("id"), name=p["name"], team=p["team"], product=p.get("product"),
                         size=size, weeks=weeks, ongoing=ongoing,
                         req=None if auto else req, earliest=earliest, deps=deps, auto=auto, reason=reason,
                         start=s, end=e, lane=i + 1, overflow=i >= nslots, delay=0 if auto else (s - req).days,
                         color=p.get("color"), line=line, col=col))
    # horizon
    hz = doc["roadmap"].get("horizon") or {}
    today = doc["roadmap"].get("today")
    hs = month(hfrom) if hfrom else (month(hz["start"]) if "start" in hz else min((x["req"] or D(x["start"].year, x["start"].month, 1)) for x in plan))
    if hto:
        he = month(hto)
    elif "end" in hz:
        he = month(hz["end"])
    else:
        cand = [D((x["end"] - dt.timedelta(days=1)).year, (x["end"] - dt.timedelta(days=1)).month, 1)
                for x in plan if not x["ongoing"]]
        cand += [D(x["start"].year, x["start"].month, 1) for x in plan if x["ongoing"]]
        he = max(cand)
        if months_between(hs, he) < 6:
            he = add_months(hs, 5)
    H0, H1 = hs, add_months(he, 1)
    hdays = (H1 - H0).days
    for x in plan:
        vs, ve = max(x["start"], H0), min(x["end"], H1)
        flags = []
        if x["delay"] > 0: flags.append("delayed")
        if x["auto"]: flags.append("auto_start")
        if x["overflow"]: flags.append("over_capacity")
        if vs >= ve:
            x["vis"] = None; flags.append("hidden")
            warnings.append(("W004", x, f'project "{x["name"]}" is outside the horizon and not shown'))
        else:
            x["vis"] = (vs, ve)
            if x["start"] < H0:
                flags.append("clipped_left")
            if x["ongoing"]:
                flags.append("continues")
            elif x["end"] > H1:
                flags.append("clipped_right")
        x["flags"] = sorted(flags)
        if x["delay"] > 0:
            why = {"capacity": f'no free slot in team "{x["team"]}"', "dependency": "waiting for dependencies", "dependency+capacity": f'waiting for dependencies, then no free slot in team "{x["team"]}"'}[x["reason"]]
            warnings.append(("W001", x, f'project "{x["name"]}" delayed {x["delay"]} days (requested {x["req"]}, starts {x["start"]}): {why}'))
        if x["overflow"]:
            warnings.append(("W011", x, f'project "{x["name"]}" exceeds team "{x["team"]}" capacity; placed in overflow lane +{x["lane"] - tmap[x["team"]]["slots"]}'))
        if "clipped_left" in flags:
            warnings.append(("W002", x, f'project "{x["name"]}" starts before the horizon; left part not shown'))
        if "clipped_right" in flags:
            warnings.append(("W003", x, f'project "{x["name"]}" ends after the horizon; right part not shown'))
    # lane index within subdomain
    lane_idx, sd_cur, idx = {}, None, 0
    for t in teams:
        if t["subdomain"] != sd_cur:
            sd_cur, idx = t["subdomain"], 0
        for li in range(len(lanes[t["id"]])):
            lane_idx[(t["id"], li + 1)] = (t["subdomain"], idx); idx += 1
    vis = [x for x in plan if x["vis"]]
    nb = {x["seq"]: set() for x in vis}
    for a in vis:
        for b in vis:
            if a["seq"] >= b["seq"]: continue
            gap = (max(a["vis"][0], b["vis"][0]) - min(a["vis"][1], b["vis"][1])).days
            sa, la = lane_idx[(a["team"], a["lane"])]
            sb, lb = lane_idx[(b["team"], b["lane"])]
            if sa == sb and abs(la - lb) <= 1 and gap <= gapd:
                nb[a["seq"]].add(b["seq"]); nb[b["seq"]].add(a["seq"])
    names = [n for n, _ in PALETTE]  # palette names
    # product colours: pins, then the first entry no product has taken (10-31, then 0-9), then the least taken
    prods = [dict(id=q["id"], name=q["name"], domain=q["domain"], owner=q.get("owner"), color=q.get("color"),
                  line=q.lc.line + 1, col=q.lc.col + 1) for q in (doc.get("products") or [])]
    pcol, taken = {}, [0] * len(PALETTE)
    for q in prods:
        if q["color"]:
            c = names.index(q["color"]); pcol[q["id"]] = c; taken[c] += 1
    for q in prods:
        if q["id"] in pcol: continue
        free = [c for c in PRODUCT_ORDER if not taken[c]]
        if free:
            c = free[0]
        else:
            c = min(range(len(PALETTE)), key=lambda c: (taken[c], c))
            first = next(o["name"] for o in prods if pcol.get(o["id"]) == c)
            warnings.append(("W014", q, f'products "{first}" and "{q["name"]}" share colour "{names[c]}" (more than {len(PALETTE)} products)'))
        pcol[q["id"]] = c; taken[c] += 1
    # pre-coloured bars: project pins, then product colours
    col, use, pinned = {}, [0] * len(PALETTE), set()
    for x in vis:
        if x["color"]:
            c = names.index(x["color"]); pinned.add(x["seq"])
        elif x["product"]:
            c = pcol[x["product"]]
        else:
            continue
        col[x["seq"]] = c; use[c] += 1
    for x in vis:
        if x["seq"] not in col: continue
        for o in sorted(nb[x["seq"]]):
            if o < x["seq"] and o in col and col[o] == col[x["seq"]]:
                y = plan[o - 1]
                if x["product"] and x["product"] == y["product"]: continue
                how = "pinned to" if {x["seq"], o} <= pinned else "coloured"
                warnings.append(("W009", x, f'projects "{y["name"]}" and "{x["name"]}" are adjacent and both {how} "{names[col[o]]}"'))
    while len(col) < len(vis):
        unc = [x["seq"] for x in vis if x["seq"] not in col]
        s = min(unc, key=lambda s: (-len({col[n] for n in nb[s] if n in col}), -len(nb[s]), s))
        used = {col[n] for n in nb[s] if n in col}
        allowed = [c for c in BASE if c not in used]
        if allowed:
            c = min(allowed, key=lambda c: (use[c], c))
        else:
            c = min(BASE, key=lambda c: (sum(1 for n in nb[s] if col.get(n) == c), use[c], c))
            warnings.append(("W007", next(v for v in vis if v["seq"] == s), "palette exhausted"))
        col[s] = c; use[c] += 1
    # utilisation
    tout = []
    for t in teams:
        occ = sum((x["vis"][1] - x["vis"][0]).days for x in plan
                  if x["team"] == t["id"] and x["vis"] and not x["overflow"])
        tout.append(dict(id=t["id"], subdomain=t["subdomain"], slots=t["slots"],
                         overflow_lanes=len(lanes[t["id"]]) - t["slots"],
                         utilization=r4(occ, t["slots"] * hdays)))
        if not any(x["team"] == t["id"] for x in plan):
            warnings.append(("W005", None, f'team "{t["id"]}" has no projects'))
    for q in prods:
        if not any(x["product"] == q["id"] for x in plan):
            warnings.append(("W013", q, f'product "{q["name"]}" has no projects'))
    ds = lambda d: d.isoformat()
    mlist = []
    m0 = H0
    while m0 < H1:
        mlist.append(m0); m0 = add_months(m0, 1)
    def occ(team, a, b):
        return sum(max(0, (min(x["end"], b) - max(x["start"], a)).days) for x in plan if x["team"] == team)
    load_teams = []
    for t in teams:
        vals = []
        for mm in mlist:
            nx = add_months(mm, 1)
            vals.append(r4(occ(t["id"], mm, nx), t["slots"] * (nx - mm).days))
        load_teams.append({"team": t["id"], "load": vals})
    sds = []
    for sd in dict.fromkeys(t["subdomain"] for t in teams):
        ts = [t for t in teams if t["subdomain"] == sd]
        vals = []
        for mm in mlist:
            nx = add_months(mm, 1); dd = (nx - mm).days
            vals.append(r4(sum(occ(t["id"], mm, nx) for t in ts), sum(t["slots"] for t in ts) * dd))
        sds.append({"subdomain": sd, "load": vals})
    tot = []
    for mm in mlist:
        nx = add_months(mm, 1); dd = (nx - mm).days
        tot.append(r4(sum(occ(t["id"], mm, nx) for t in teams), sum(t["slots"] for t in teams) * dd))
    monthly = {"months": [mstr(m) for m in mlist], "teams": load_teams, "subdomains": sds, "total": tot}
    projects = []
    for x in plan:
        c = col.get(x["seq"])
        projects.append({
            "seq": x["seq"], "id": x["pid"], "name": x["name"], "team": x["team"], "product": x["product"],
            "size": x["size"], "weeks": x["weeks"],
            "ongoing": x["ongoing"], "requested_start": None if x["auto"] else ds(x["req"]),
            "depends_on": x["deps"], "earliest_start": ds(x["earliest"]), "start": ds(x["start"]),
            "end": None if x["ongoing"] else ds(x["end"]),
            "last_day": None if x["ongoing"] else ds(x["end"] - dt.timedelta(days=1)),
            "lane": x["lane"], "overflow": x["overflow"], "delay_days": x["delay"], "delay_reason": x["reason"],
            "visible": None if not x["vis"] else {"start": ds(x["vis"][0]), "end": ds(x["vis"][1])},
            "color_index": c, "color_name": None if c is None else PALETTE[c][0],
            "color_fill": None if c is None else PALETTE[c][1],
            "flags": x["flags"], "neighbors": sorted(nb.get(x["seq"], [])),
        })
    wl = []
    for code, x, msg in warnings:
        wl.append({"code": code, "line": x["line"] if x else None, "column": x["col"] if x else None, "message": msg})
    wl.sort(key=lambda w: (w["line"] or 0, w["column"] or 0, w["code"]))
    out = {
        "rt_version": "1.0.0", "format": 1, "title": doc["roadmap"]["title"],
        "today": str(today) if today else None,
        "horizon": {"start": mstr(H0), "end": mstr(he), "start_date": ds(H0), "end_exclusive": ds(H1), "days": hdays},
        "on_conflict": mode, "teams": tout,
        "products": [{"id": q["id"], "name": q["name"], "domain": q["domain"], "owner": q["owner"],
                      "color_index": pcol[q["id"]], "color_name": names[pcol[q["id"]]],
                      "color_fill": PALETTE[pcol[q["id"]]][1],
                      "projects": [x["seq"] for x in plan if x["product"] == q["id"]]} for q in prods],
        "projects": projects, "monthly_load": monthly, "warnings": wl,
    }
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    kw = {}
    path = args[0]
    for a in args[1:]:
        k, v = a.split("=")
        kw[k] = v
    res = run(path, **kw)
    print(json.dumps(res, indent=2, ensure_ascii=False))
