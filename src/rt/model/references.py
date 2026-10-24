"""Cross-reference checks: E020–E023, E030, E031, E034–E037; resolves depends_on to seq numbers (ADS 4.2).

Names and ids are compared with `==`: the loader (or rt convert) has already NFC-normalised every string
(RS IN-8, ADR-8). Checks that need a field which failed validation are skipped (ADS 8.2).
"""

from __future__ import annotations

from types import MappingProxyType

from rt.diagnostics import Code, Collector, Pos, suggest
from rt.model.types import Model, Project, ResolvedModel


def _label(p: Project) -> str:
    return p.name if p.name is not None else f"#{p.seq}"


def _pos(p: Project, key: str) -> Pos:
    return p.field_pos.get(key, p.pos)


def _check_unique(model: Model, diags: Collector) -> None:
    first_sub: dict[str, Pos] = {}
    for s in model.subdomains:
        if not s.id:
            continue
        pos = s.field_pos.get("id", s.pos)
        if s.id in first_sub:
            diags.report(Code.E020, pos, id=s.id, line=first_sub[s.id].line)
        else:
            first_sub[s.id] = pos

    first_team: dict[str, Pos] = {}
    for t in model.teams:
        pos = t.field_pos.get("id", t.pos)
        if t.id in first_team:
            diags.report(Code.E021, pos, id=t.id, line=first_team[t.id].line)
        else:
            first_team[t.id] = pos

    first_id: dict[str, Pos] = {}
    first_name: dict[tuple[str, str], Project] = {}
    for p in model.projects:
        if p.id is not None:
            pos = _pos(p, "id")
            if p.id in first_id:
                diags.report(Code.E023, pos, column=p.field_column.get("id"), id=p.id, line=first_id[p.id].line)
            else:
                first_id[p.id] = pos
        if p.name is not None and p.team_id is not None:
            key = (p.team_id, p.name)
            if key in first_name:
                diags.report(
                    Code.E022,
                    _pos(p, "name"),
                    column=p.field_column.get("name"),
                    name=p.name,
                    team=p.team_id,
                    line=first_name[key].pos.line,
                )
            else:
                first_name[key] = p


def _check_team_and_size(model: Model, diags: Collector) -> None:
    team_ids = [t.id for t in model.teams]
    known_teams = set(team_ids)
    labels = [s.label for s in model.sizes]
    known_sizes = set(labels)
    for p in model.projects:
        if p.team_id is not None and p.team_id not in known_teams:
            diags.report(
                Code.E030,
                _pos(p, "team"),
                column=p.field_column.get("team"),
                project=_label(p),
                team=p.team_id,
                hint=suggest(p.team_id, team_ids),
            )
        if p.size is not None and p.size not in known_sizes:
            diags.report(
                Code.E031,
                _pos(p, "size"),
                column=p.field_column.get("size"),
                project=_label(p),
                size=p.size,
                sizes=", ".join(labels) or "none",
            )


def _resolve_dependencies(model: Model, diags: Collector) -> dict[int, tuple[int, ...]]:
    """Each item is a project id, else a name unique in the whole file (RS 3.2); it must be earlier, not
    ongoing and not the project itself."""
    by_id: dict[str, Project] = {}
    by_name: dict[str, list[Project]] = {}
    candidates: list[str] = []
    for p in model.projects:
        if p.id is not None and p.id not in by_id:
            by_id[p.id] = p
            candidates.append(p.id)
        if p.name is not None:
            by_name.setdefault(p.name, []).append(p)
            candidates.append(p.name)

    deps: dict[int, tuple[int, ...]] = {}
    for p in model.projects:
        column = p.field_column.get("depends_on")
        resolved: set[int] = set()
        for ref in p.depends_on_refs:
            target = by_id.get(ref.text)
            if target is None:
                matches = by_name.get(ref.text, [])
                if len(matches) > 1:
                    lines = ", ".join(str(m.pos.line) for m in matches)
                    diags.report(Code.E035, ref.pos, column=column, ref=ref.text, count=len(matches), lines=lines)
                    continue
                if not matches:
                    diags.report(
                        Code.E034,
                        ref.pos,
                        column=column,
                        project=_label(p),
                        ref=ref.text,
                        hint=suggest(ref.text, candidates),
                    )
                    continue
                target = matches[0]
            if target.seq == p.seq:
                diags.report(Code.E037, ref.pos, column=column, detail=f'project "{_label(p)}" depends on itself')
                continue
            if target.seq > p.seq:
                diags.report(
                    Code.E037,
                    ref.pos,
                    column=column,
                    detail=f'project "{_label(p)}" depends on "{ref.text}", which appears later '
                    f'(line {target.pos.line}); move "{ref.text}" above it',
                )
                continue
            if target.ongoing:
                diags.report(Code.E036, ref.pos, column=column, project=_label(p), dep=_label(target))
                continue
            resolved.add(target.seq)
        deps[p.seq] = tuple(sorted(resolved))
    return deps


def check_references(model: Model, diags: Collector) -> ResolvedModel | None:
    """Run every check that the usable fields allow; return None if the collector holds any error afterwards."""
    _check_unique(model, diags)
    _check_team_and_size(model, diags)
    deps = _resolve_dependencies(model, diags)
    if diags.has_errors() or any(p.incomplete for p in model.projects):
        return None
    weeks: dict[int, int | None] = {}
    for p in model.projects:
        weeks[p.seq] = None if p.ongoing or p.size is None else model.size_weeks(p.size)
    return ResolvedModel(model=model, deps=MappingProxyType(deps), weeks=MappingProxyType(weeks))
