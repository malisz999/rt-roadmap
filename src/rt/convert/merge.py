"""Rows → project mappings, team resolution, base merge or skeleton, validation (RS CV-8 to CV-17; ADS 6.8 5-7)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from rt.convert.columns import Columns, clean, resolve_columns
from rt.convert.csv_source import CsvRecord, CsvTable
from rt.convert.emit import display_name, dump
from rt.convert.skeleton import DEFAULT_SIZES, DEFAULT_SLOTS, DEFAULT_SUBDOMAIN, DEFAULT_TEAM, DEFAULT_TITLE, Skeleton
from rt.convert.values import match_size, parse_ongoing, parse_start, split_depends
from rt.diagnostics import Code, Collector, Diagnostic, Pos, closest
from rt.io.rawdoc import CsvRow, RawDoc
from rt.model.types import Overrides
from rt.options import ConvertOptions

_ONGOING_WORDS = "true, yes, y, 1, x, tak, t or false, no, n, 0, nie"


@dataclass(frozen=True, slots=True)
class BaseTeam:
    id: str
    name: str | None


@dataclass
class _Row:
    record: CsvRecord
    node: CommentedMap
    team_name: str = ""  # skeleton mode: the team name, replaced by its id after build()


@dataclass
class _Context:
    table: CsvTable
    cols: Columns
    opts: ConvertOptions
    diags: Collector
    cells: dict[str, tuple[int, str]]  # field → (1-based field number, header), for RawDoc registration
    size_labels: list[str]
    base: RawDoc | None = None
    base_teams: list[BaseTeam] = field(default_factory=list)
    skeleton: Skeleton | None = None
    suppress: set[tuple[int, Code]] = field(default_factory=set)  # (CSV line, code) already reported here
    registrations: list[tuple[CommentedMap, CsvRow]] = field(default_factory=list)  # generated nodes → CSV cells

    def pos(self, line: int, column: str) -> Pos:
        index = self.cols.index(column)
        return Pos(line, index + 1 if index is not None else 1, self.table.source)


def base_size_labels(root: Any) -> list[str]:
    sizes = root.get("sizes") if isinstance(root, dict) else None
    return [str(k) for k in sizes] if isinstance(sizes, dict) else []


def base_teams(root: Any) -> list[BaseTeam]:
    """Teams of a base document in file order, read defensively (the validator reports malformed bases)."""
    found: list[BaseTeam] = []
    subs = root.get("subdomains") if isinstance(root, dict) else None
    for sd in subs if isinstance(subs, list) else []:
        teams = sd.get("teams") if isinstance(sd, dict) else None
        for tm in teams if isinstance(teams, list) else []:
            if isinstance(tm, dict) and isinstance(tm.get("id"), str):
                name = tm.get("name")
                found.append(BaseTeam(tm["id"], name if isinstance(name, str) else None))
    return found


def resolve_team(value: str, teams: Sequence[BaseTeam]) -> str | None:
    """Team id exactly, else team name exactly (strings are NFC on both sides) (RS CV-16)."""
    for t in teams:
        if t.id == value:
            return t.id
    for t in teams:
        if t.name == value:
            return t.id
    return None


def team_hint(value: str, teams: Sequence[BaseTeam]) -> str:
    """` (did you mean "app"?)`: closest team id or name, compared case-insensitively."""
    originals: dict[str, str] = {}
    for t in teams:
        for cand in (t.id, t.name):
            if cand is not None:
                originals.setdefault(cand.casefold(), cand)
    folded = value.casefold()
    hit = folded if folded in originals else closest(folded, originals)
    return "" if hit is None else f' (did you mean "{originals[hit]}"?)'


def _base_team(ctx: _Context, row: CsvRecord, team_raw: str, name: str) -> str | None:
    """Team id for a row in base mode, or a raw value / None after reporting E030 / E105."""
    teams = ctx.base_teams
    option = clean(ctx.opts.team or "")
    if team_raw or option:
        value = team_raw or option
        hit = resolve_team(value, teams)
        if hit is not None:
            return hit
        pos = ctx.pos(row.line, "team") if team_raw else Pos(row.line, 1, ctx.table.source)
        ctx.diags.error(
            Code.E030,
            pos,
            column=ctx.cols.header("team") if team_raw else None,
            project=name,
            team=value,
            hint=team_hint(value, teams),
        )
        ctx.suppress.add((row.line, Code.E030))
        return value
    if len(teams) == 1:
        return teams[0].id
    base_name = display_name(ctx.base.source) if ctx.base else "the base file"
    ctx.diags.error(
        Code.E105, ctx.pos(row.line, "team"), column=ctx.cols.header("team"), base=base_name, count=len(teams)
    )
    ctx.suppress.add((row.line, Code.E010))
    return None


def _skeleton_team(ctx: _Context, row: CsvRecord, team_raw: str) -> str:
    """Team name for a row in skeleton mode; E107 when the team was first seen in another subdomain."""
    assert ctx.skeleton is not None
    team = team_raw or clean(ctx.opts.team or "") or DEFAULT_TEAM
    subdomain = ctx.cols.cell(row.cells, "subdomain") or DEFAULT_SUBDOMAIN
    known = ctx.skeleton.add(team, subdomain, row.line)
    if known.subdomain != subdomain:
        ctx.diags.error(
            Code.E107,
            ctx.pos(row.line, "subdomain"),
            column=ctx.cols.header("subdomain"),
            team=team,
            first=known.subdomain,
            first_line=known.line,
            second=subdomain,
            second_line=row.line,
        )
    elif known.line == row.line:
        # Generated team and subdomain mappings point at the cells they came from.
        source = ctx.table.source
        if team_raw:
            cell = {"id": ctx.cells["team"], "name": ctx.cells["team"]}
            ctx.registrations.append((known.node, CsvRow(source, row.line, cell)))
        sub = ctx.skeleton.subdomains[subdomain]
        if sub.line == row.line and ctx.cols.cell(row.cells, "subdomain"):
            cell = {"id": ctx.cells["subdomain"], "name": ctx.cells["subdomain"]}
            ctx.registrations.append((sub.node, CsvRow(source, row.line, cell)))
    return team


def _project(ctx: _Context, row: CsvRecord) -> _Row:
    """One project mapping with keys in the order of RS CV-18."""
    cols, cells, diags = ctx.cols, row.cells, ctx.diags
    node = CommentedMap()
    result = _Row(row, node)
    ident = cols.cell(cells, "id")
    if ident:
        node["id"] = ident
    name = cols.cell(cells, "name")
    node["name"] = name
    team_raw = cols.cell(cells, "team")
    if ctx.skeleton is not None:
        result.team_name = _skeleton_team(ctx, row, team_raw)
        node["team"] = result.team_name
    else:
        team = _base_team(ctx, row, team_raw, name)
        if team is not None:
            node["team"] = team
    start_raw = cols.cell(cells, "start")
    if start_raw:
        start = parse_start(start_raw)
        column = cols.header("start")
        if start is None:
            detail = f'invalid start "{start_raw}"; expected YYYY-MM, YYYY-MM-DD or DD.MM.YYYY'
            diags.error(Code.E013, ctx.pos(row.line, "start"), column=column, detail=detail)
        else:
            if start.day_dropped:
                diags.warning(Code.W021, ctx.pos(row.line, "start"), column=column, value=start_raw, month=start.month)
            node["start"] = start.month
    size_raw = cols.cell(cells, "size")
    if size_raw:
        node["size"] = match_size(size_raw, ctx.size_labels) or size_raw
    ongoing_raw = cols.cell(cells, "ongoing")
    ongoing = parse_ongoing(ongoing_raw)
    if ongoing is None:
        detail = f'"ongoing" must be one of {_ONGOING_WORDS}, got "{ongoing_raw}"'
        diags.error(Code.E011, ctx.pos(row.line, "ongoing"), column=cols.header("ongoing"), detail=detail)
        ctx.suppress.add((row.line, Code.E032))
    elif ongoing:
        node["ongoing"] = True
    deps = split_depends(cols.cell(cells, "depends_on"))
    if deps:
        seq = CommentedSeq(deps)
        seq.fa.set_flow_style()
        node["depends_on"] = seq
    for key in ("description", "color"):
        value = cols.cell(cells, key)
        if value:
            node[key] = value
    return result


def _validate(raw: RawDoc, ctx: _Context) -> None:
    """The normal validator on the converted tree, without scheduling (RS CV-17). Diagnostics already reported
    by convert for the same CSV row (E030, E105, E011) suppress the validator's follow-up ones."""
    # Imported here so the pure conversion steps stay importable while the model package evolves.
    from rt.model.build import build_model
    from rt.model.references import check_references

    found = Collector(raw.source)
    model = build_model(raw, found, Overrides(default_today=ctx.opts.default_today))
    if model is not None:
        check_references(model, found)
    for d in found.items:
        if d.source == ctx.table.source and d.line is not None and (d.line, d.code) in ctx.suppress:
            continue
        ctx.diags.add(d)


def _column_cells(cols: Columns) -> dict[str, tuple[int, str]]:
    return {name: (index + 1, head) for name, (index, head) in cols.fields.items()}


def convert_csv(table: CsvTable, base: RawDoc | None, opts: ConvertOptions, diags: Collector) -> str | None:
    """CsvTable (+ base) → YAML text, or None when any error was collected (RS CV-6 to CV-20)."""
    cols = resolve_columns(table, opts.column_map, base is not None, diags)
    if cols is None:
        return None
    if base is not None:
        root = base.root
        ctx = _Context(table, cols, opts, diags, _column_cells(cols), base_size_labels(root), base=base)
        ctx.base_teams = base_teams(root)
    else:
        skeleton = Skeleton(
            title=opts.title if opts.title is not None else DEFAULT_TITLE,
            sizes=opts.sizes if opts.sizes is not None else DEFAULT_SIZES,
            slots=opts.slots if opts.slots is not None else DEFAULT_SLOTS,
        )
        ctx = _Context(table, cols, opts, diags, _column_cells(cols), skeleton.size_labels, skeleton=skeleton)
    rows = [_project(ctx, record) for record in table.rows]
    if ctx.skeleton is not None:
        if not ctx.skeleton.teams:  # no data rows: keep the skeleton valid with the default team
            ctx.skeleton.add(clean(opts.team or "") or DEFAULT_TEAM, DEFAULT_SUBDOMAIN, table.header.line)
        doc = ctx.skeleton.build()
        for r in rows:
            r.node["team"] = ctx.skeleton.team_ids[r.team_name]
        raw = RawDoc(doc, table.source)
    else:
        assert base is not None
        doc = base.root
        raw = base
        if not isinstance(doc, CommentedMap):
            _validate(raw, ctx)
            if not diags.has_errors():
                diags.add(Diagnostic(Code.E011, "the base file must be a mapping", base.source, 1, 1))
            return None
    _place_projects(doc, [r.node for r in rows], opts.append and base is not None)
    for r in rows:
        raw.register_csv_row(r.node, CsvRow(table.source, r.record.line, ctx.cells))
    for node, csv_row in ctx.registrations:
        raw.register_csv_row(node, csv_row)
    _validate(raw, ctx)
    if diags.has_errors():
        return None
    return dump(doc, table.source)


def _place_projects(doc: CommentedMap, projects: list[CommentedMap], append: bool) -> None:
    """Replace `projects`, or with --append add the rows after the base's own projects (RS CV-13)."""
    existing = doc.get("projects")
    if append and isinstance(existing, CommentedSeq) and len(existing) > 0 and not existing.fa.flow_style():
        existing.extend(projects)
        return
    keep = list(existing) if append and isinstance(existing, list) else []
    doc["projects"] = CommentedSeq(keep + projects)


__all__ = ["BaseTeam", "base_size_labels", "base_teams", "convert_csv", "resolve_team", "team_hint"]
