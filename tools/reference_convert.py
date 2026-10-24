"""rt reference CSV -> YAML converter — TEST TOOLING ONLY, never import from src/.

Produced projects.minimal.expected.yaml and projects.pl.expected.yaml
(requirements spec section 3.4 and 6.6). Implements the conversion rules:
decoding, delimiter detection, header mapping, value parsing, team resolution,
skeleton generation, base merge and YAML emission.
Does NOT run the rt validator on the result (rt convert does) and reports
diagnostics only as plain tuples.

Usage:
  python reference_convert.py INPUT.csv [--base FILE] [--map A=b,C=d] [--team T]
         [--title T] [--sizes S=2,M=4] [--slots N] [--append] [--encoding ENC] [--delimiter D]
Requires: ruamel.yaml 0.19.x
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import unicodedata
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

CANONICAL = ["name", "size", "team", "subdomain", "start", "ongoing", "depends_on", "id", "description", "color"]
DEFAULT_SIZES = [("XS", 1), ("S", 2), ("M", 4), ("L", 8), ("XL", 13), ("XXL", 26)]
TRUE = {"true", "yes", "y", "1", "x", "tak", "t"}
FALSE = {"false", "no", "n", "0", "nie", ""}
OUT_KEYS = ["id", "name", "team", "start", "size", "ongoing", "depends_on", "description", "color"]


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())


def slug(text: str) -> str:
    t = text.replace("ł", "l").replace("Ł", "L")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40].strip("-")
    return t or "x"


def unique_slug(text: str, taken: set[str], fallback: str) -> str:
    base = slug(text) if slug(text) != "x" else fallback
    cand, n = base, 2
    while cand in taken:
        suffix = f"-{n}"
        cand = base[: 40 - len(suffix)] + suffix
        n += 1
    taken.add(cand)
    return cand


def detect_delimiter(header_line: str) -> str:
    counts = {",": 0, ";": 0, "\t": 0}
    inside = False
    for ch in header_line:
        if ch == '"':
            inside = not inside
        elif not inside and ch in counts:
            counts[ch] += 1
    best = max(counts.values())
    if best == 0:
        return ","
    return next(d for d in (",", ";", "\t") if counts[d] == best)


def parse_month(raw: str) -> tuple[str | None, bool]:
    """Return (YYYY-MM, day_dropped) or (None, False) if invalid."""
    if m := re.fullmatch(r"(\d{4})-(\d{2})", raw):
        y, mo, d = m.group(1), m.group(2), "01"
    elif m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw):
        y, mo, d = m.groups()
    elif m := re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", raw):
        d, mo, y = m.groups()
    else:
        return None, False
    if not 1 <= int(mo) <= 12 or not 1 <= int(d) <= 31:
        return None, False
    return f"{y}-{mo}", d != "01"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--base")
    ap.add_argument("--map", default="")
    ap.add_argument("--team")
    ap.add_argument("--title")
    ap.add_argument("--sizes")
    ap.add_argument("--slots", type=int, default=1)
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--encoding", default="utf-8")
    ap.add_argument("--delimiter")
    a = ap.parse_args()

    diags: list[tuple[str, int, int, str]] = []
    data = sys.stdin.buffer.read() if a.input == "-" else Path(a.input).read_bytes()
    source = "<stdin>" if a.input == "-" else Path(a.input).name
    enc = "utf-8-sig" if a.encoding.lower().replace("_", "-") in ("utf-8", "utf8") else a.encoding
    text = data.decode(enc)  # E102 on failure in rt
    first = text.splitlines()[0] if text else ""
    delim = {"comma": ",", "semicolon": ";", "tab": "\t"}.get(a.delimiter or "", a.delimiter) or detect_delimiter(first)

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim, quotechar='"', doublequote=True, strict=True)
    records: list[tuple[int, list[str]]] = []
    prev_end = 0
    for rec in reader:
        start_line = prev_end + 1
        prev_end = reader.line_num
        records.append((start_line, rec))
    header_line, header = records[0]
    body = records[1:]

    mapping = {}
    for pair in filter(None, (p.strip() for p in a.map.split(","))):
        src, dst = pair.split("=", 1)
        mapping[nfc(src).casefold()] = nfc(dst).lower()
    cols: dict[str, int] = {}
    for i, h in enumerate(header):
        key = nfc(h)
        canon = mapping.get(key.casefold(), key.lower())
        if canon not in CANONICAL:
            diags.append(("W020", header_line, i + 1, f'column "{key}" is not used and was ignored'))
            continue
        if canon == "subdomain" and a.base:
            diags.append(("W020", header_line, i + 1, f'column "{key}" is ignored with --base'))
            continue
        cols[canon] = i

    def cell(rec: list[str], name: str) -> str:
        i = cols.get(name)
        return nfc(rec[i]) if i is not None and i < len(rec) else ""

    yaml = YAML()  # round-trip
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    yaml.allow_unicode = True

    if a.base:
        doc = yaml.load(Path(a.base).read_text(encoding="utf-8-sig"))
        size_labels = [str(k) for k in doc["sizes"]]
        teams = [(t["id"], t["name"]) for sd in doc["subdomains"] for t in sd["teams"]]
    else:
        sizes = DEFAULT_SIZES
        if a.sizes:
            sizes = [(k.strip(), int(v)) for k, v in (p.split("=") for p in a.sizes.split(","))]
        size_labels = [k for k, _ in sizes]
        teams = []

    def match_size(v: str) -> str | None:
        if v in size_labels:
            return v
        ci = [s for s in size_labels if s.casefold() == v.casefold()]
        return ci[0] if len(ci) == 1 else None

    # skeleton structures
    sub_order: list[str] = []
    team_order: list[tuple[str, str]] = []  # (team name, subdomain name)
    projects = []
    for line, rec in body:
        if all(not c.strip() for c in rec):
            continue
        p = CommentedMap()
        name = cell(rec, "name")
        ongoing_raw = cell(rec, "ongoing").casefold()
        ongoing = ongoing_raw in TRUE
        size_raw = cell(rec, "size")
        team_raw = cell(rec, "team")
        if a.base:
            if team_raw:
                hit = [i for i, n in teams if i == team_raw] or [i for i, n in teams if n == team_raw]
                team = hit[0] if hit else team_raw
            elif a.team:
                hit = [i for i, n in teams if a.team in (i, n)]
                team = hit[0] if hit else a.team
            elif len(teams) == 1:
                team = teams[0][0]
            else:
                diags.append(("E105", line, 1, "no team")); team = ""
        else:
            tname = team_raw or a.team or "Team"
            sname = cell(rec, "subdomain") or "Roadmap"
            if sname not in sub_order:
                sub_order.append(sname)
            if tname not in [t for t, _ in team_order]:
                team_order.append((tname, sname))
            team = tname  # replaced by id below
        start, dropped = parse_month(cell(rec, "start")) if cell(rec, "start") else (None, False)
        if dropped:
            diags.append(("W021", line, cols["start"] + 1, f'day of "{cell(rec, "start")}" ignored; using {start}'))
        if cell(rec, "id"):
            p["id"] = cell(rec, "id")
        p["name"] = name
        p["team"] = team
        if start:
            p["start"] = start
        if size_raw:
            p["size"] = match_size(size_raw) or size_raw
        if ongoing:
            p["ongoing"] = True
        deps = [nfc(d) for d in re.split(r"[|\n]", cell(rec, "depends_on")) if nfc(d)]
        if deps:
            seq = CommentedSeq(deps)
            seq.fa.set_flow_style()
            p["depends_on"] = seq
        for k in ("description", "color"):
            if cell(rec, k):
                p[k] = cell(rec, k)
        projects.append(p)

    if not a.base:
        taken_sd: set[str] = set()
        taken_tm: set[str] = set()
        sd_ids = {s: unique_slug(s, taken_sd, "subdomain") for s in sub_order}
        tm_ids = {t: unique_slug(t, taken_tm, "team") for t, _ in team_order}
        for p in projects:
            p["team"] = tm_ids[p["team"]]
        doc = CommentedMap()
        doc["version"] = 1
        doc["roadmap"] = CommentedMap(title=a.title or "Roadmap")
        doc["sizes"] = CommentedMap(sizes)
        subs = CommentedSeq()
        for s in sub_order:
            sd = CommentedMap()
            sd["id"] = sd_ids[s]
            sd["name"] = s
            tl = CommentedSeq()
            for t, owner in team_order:
                if owner == s:
                    tm = CommentedMap()
                    tm["id"] = tm_ids[t]
                    tm["name"] = t
                    tm["parallel_projects"] = a.slots
                    tl.append(tm)
            sd["teams"] = tl
            subs.append(sd)
        doc["subdomains"] = subs

    plist = CommentedSeq(projects)
    if a.base and a.append and isinstance(doc.get("projects"), list):
        plist = CommentedSeq(list(doc["projects"]) + projects)
    doc["projects"] = plist

    buf = io.StringIO()
    yaml.dump(doc, buf)
    out = f"# Generated by rt convert from {source}. Edit freely.\n" + buf.getvalue()
    sys.stdout.buffer.write(out.encode("utf-8"))
    for d in diags:
        print(f"{source}:{d[1]}:{d[2]}: {'warning' if d[0][0] == 'W' else 'error'} {d[0]}: {d[3]}", file=sys.stderr)
    return 1 if any(d[0][0] == "E" for d in diags) else 0


if __name__ == "__main__":
    sys.exit(main())
