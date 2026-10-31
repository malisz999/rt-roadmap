"""RawDoc → Model + diagnostics (structure): E002, E004, E010–E013, E032, E033, E040–E043 (ADS 4.2, 8.2).

Subdomains, teams, products and projects are built in that order; references between them are checked later.

Every position comes from RawDoc (value_pos, key_pos, item_pos, node_pos), so rows built by rt convert report
their CSV line and field number, and messages about a CSV cell end with ` [column "…"]` (RS CV-5, CV-17).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from fractions import Fraction
from types import MappingProxyType
from typing import Any, Final

from rt.diagnostics import Code, Collector, Pos, suggest
from rt.io.rawdoc import RawDoc
from rt.model import fields as F
from rt.model.types import (
    Band,
    Capacity,
    ColorSpec,
    DepRef,
    Mode,
    Model,
    Overrides,
    Product,
    Project,
    Settings,
    Size,
    Subdomain,
    Team,
    TeamNorms,
)
from rt.timeutil import Month, months_between, parse_date


class _Missing:
    """Marker for a key that is not in the mapping."""


MISSING: Final = _Missing()


@dataclass
class _Ent:
    """One mapping being validated: where it is named in messages, and what has been learnt about it."""

    node: Any
    where: str  # E002: `unknown key "x" in <where>`
    missing_where: str  # E010: `<missing_where> is missing required field "x"`
    field_pos: dict[str, Pos] = field(default_factory=dict)
    field_column: dict[str, str] = field(default_factory=dict)
    bad: bool = False


class _Builder:
    def __init__(self, raw: RawDoc, diags: Collector) -> None:
        self.raw = raw
        self.diags = diags

    # --- reporting ---------------------------------------------------------------------------------------------
    def fail(self, ent: _Ent, code: Code, key: str, **fields: Any) -> None:
        """Report a problem with ent.node[key]'s value and mark the entity incomplete."""
        self.diags.report(
            code, self.raw.value_pos(ent.node, key), column=self.raw.column_label(ent.node, key), **fields
        )
        ent.bad = True

    def unknown_keys(self, ent: _Ent, allowed: tuple[str, ...]) -> None:
        """E002 for every key not in `allowed`, with a did-you-mean hint (RS IN-3)."""
        for key in ent.node:
            if isinstance(key, str) and key in allowed:
                continue
            text = str(key)
            self.diags.report(
                Code.E002,
                self.raw.key_pos(ent.node, key),
                column=self.raw.column_label(ent.node, key),
                key=text,
                where=ent.where,
                hint=suggest(text, allowed),
            )

    # --- field access ------------------------------------------------------------------------------------------
    def get(self, ent: _Ent, key: str, *, required: bool = False) -> Any:
        """ent.node[key], recording its position and CSV column; MISSING (and E010 if required) when absent."""
        node = ent.node
        if key not in node:
            if required:
                self.diags.report(
                    Code.E010,
                    self.raw.value_pos(node, key),
                    column=self.raw.column_label(node, key),
                    where=ent.missing_where,
                    field=key,
                )
                ent.bad = True
            return MISSING
        ent.field_pos[key] = self.raw.value_pos(node, key)
        label = self.raw.column_label(node, key)
        if label is not None:
            ent.field_column[key] = label
        return node[key]

    def string(self, ent: _Ent, key: str, length: tuple[int, int], *, required: bool = False) -> str | None:
        value = self.get(ent, key, required=required)
        if value is MISSING:
            return None
        if not isinstance(value, str):
            self.fail(ent, Code.E011, key, detail=f'"{key}" must be a string, got {F.describe(value)}')
            return None
        low, high = length
        if not low <= len(value) <= high:
            rule = f"at most {high} characters" if low == 0 else f"{low}–{high} characters"
            self.fail(ent, Code.E012, key, detail=f'"{key}" must be {rule}, got {len(value)}')
            return None
        return value

    def integer(self, ent: _Ent, key: str, bounds: tuple[int, int], *, required: bool = False) -> int | None:
        value = self.get(ent, key, required=required)
        if value is MISSING:
            return None
        if not F.is_int(value):
            self.fail(ent, Code.E011, key, detail=f'"{key}" must be an integer, got {F.describe(value)}')
            return None
        low, high = bounds
        if not low <= value <= high:
            self.fail(ent, Code.E012, key, detail=f'"{key}" must be {low}–{high}, got {value}')
            return None
        return int(value)

    def ident(self, ent: _Ent, key: str, kind: str, *, required: bool = False) -> str | None:
        """An id: a string matching ID_RE. A string that breaks the pattern is reported (E012) but kept, so
        references to it still resolve and do not add follow-up errors."""
        value = self.get(ent, key, required=required)
        if value is MISSING:
            return None
        if not isinstance(value, str):
            self.fail(ent, Code.E011, key, detail=f'"{key}" must be a string, got {F.describe(value)}')
            return None
        if not F.ID_RE.match(value):
            self.fail(ent, Code.E012, key, detail=f'{kind} id "{value}" must be {F.ID_RULE}')
        return value

    def month(self, ent: _Ent, key: str) -> Month | None:
        value = self.get(ent, key)
        if value is MISSING:
            return None
        if isinstance(value, str):
            try:
                return Month.parse(value)
            except ValueError:
                pass
        elif not isinstance(value, date | int | float) or isinstance(value, bool):
            self.fail(ent, Code.E011, key, detail=f'"{key}" must be a month (YYYY-MM), got {F.describe(value)}')
            return None
        self.fail(ent, Code.E013, key, detail=f'invalid month "{F.as_text(value)}"; expected YYYY-MM')
        return None

    def day(self, ent: _Ent, key: str) -> date | None:
        value = self.get(ent, key)
        if value is MISSING:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):  # RS IN-2
            return date(value.year, value.month, value.day)
        if isinstance(value, str):
            try:
                return parse_date(value)
            except ValueError:
                pass
        elif not isinstance(value, date | int | float) or isinstance(value, bool):
            self.fail(ent, Code.E011, key, detail=f'"{key}" must be a date (YYYY-MM-DD), got {F.describe(value)}')
            return None
        self.fail(ent, Code.E013, key, detail=f'invalid date "{F.as_text(value)}"; expected YYYY-MM-DD')
        return None

    def mapping(self, ent: _Ent, key: str, *, required: bool = False) -> Any:
        """A nested mapping, or None (E011 when it is something else)."""
        value = self.get(ent, key, required=required)
        if value is MISSING:
            return None
        if not F.is_mapping(value):
            self.fail(ent, Code.E011, key, detail=f'"{key}" must be a mapping, got {F.describe(value)}')
            return None
        return value

    def sequence(self, ent: _Ent, key: str, *, required: bool = False) -> Any:
        value = self.get(ent, key, required=required)
        if value is MISSING:
            return None
        if not F.is_list(value):
            self.fail(ent, Code.E011, key, detail=f'"{key}" must be a list, got {F.describe(value)}')
            return None
        return value

    # --- document ----------------------------------------------------------------------------------------------
    def build(self, overrides: Overrides) -> Model | None:
        raw = self.raw
        root = raw.root
        if not F.is_mapping(root):
            self.diags.report(
                Code.E011,
                Pos(1, 1, raw.source),
                detail="the file must be a mapping with version, roadmap, sizes, subdomains and projects, "
                f"got {F.describe(root)}",
            )
            return None
        top = _Ent(root, where="the file", missing_where="the file")
        if not self.version(top):
            return None
        self.unknown_keys(top, F.TOP_KEYS)
        settings = self.settings(top, overrides)
        sizes = self.sizes(top)
        norms = self.team_norms(top)
        subdomains, teams = self.subdomains(top)
        products = self.products(top)
        projects = self.projects(top)
        return Model(
            settings=settings,
            sizes=sizes,
            subdomains=subdomains,
            teams=teams,
            projects=projects,
            source=raw.source,
            products=products,
            team_norms=norms,
        )

    def version(self, top: _Ent) -> bool:
        """E004 unless `version: 1` (RS 3.1)."""
        value = self.get(top, "version")
        if value is MISSING:
            self.diags.report(
                Code.E004,
                self.raw.node_pos(top.node),
                detail='missing "version"; add version: 1 at the top of the file (this rt supports version 1)',
            )
            return False
        if not (F.is_int(value) and value == 1):
            self.diags.report(
                Code.E004,
                self.raw.value_pos(top.node, "version"),
                detail=f"unsupported version {F.describe(value)}; this rt supports version 1",
            )
            return False
        return True

    def settings(self, top: _Ent, overrides: Overrides) -> Settings:
        raw = self.raw
        settings_pos = raw.key_pos(top.node, "roadmap") if "roadmap" in top.node else raw.node_pos(top.node)
        title: str | None = None
        subtitle: str | None = None
        start: Month | None = None
        end: Month | None = None
        today: date | None = None
        month_width: int | None = None
        language: str | None = None
        horizon_ent: _Ent | None = None

        node = self.mapping(top, "roadmap", required=True)
        if node is not None:
            ent = _Ent(node, where="roadmap", missing_where="roadmap")
            self.unknown_keys(ent, F.ROADMAP_KEYS)
            title = self.string(ent, "title", F.TITLE_LEN, required=True)
            subtitle = self.string(ent, "subtitle", F.SUBTITLE_LEN)
            horizon = self.mapping(ent, "horizon")
            if horizon is not None:
                horizon_ent = _Ent(horizon, where="roadmap.horizon", missing_where="roadmap.horizon")
                self.unknown_keys(horizon_ent, F.HORIZON_KEYS)
                start = self.month(horizon_ent, "start")
                end = self.month(horizon_ent, "end")
            today = self.day(ent, "today")
            month_width = self.integer(ent, "month_width", F.MONTH_WIDTH)
            language = self.string(ent, "content_language", (1, 35))
            if language is not None and not F.LANG_RE.match(language):
                self.fail(
                    ent,
                    Code.E012,
                    "content_language",
                    detail=f'"content_language" must be a language tag such as "pl" or "en-GB", got "{language}"',
                )
                language = None

        on_conflict: Mode | None = None
        gap: int | None = None
        node = self.mapping(top, "scheduling")
        if node is not None:
            ent = _Ent(node, where="scheduling", missing_where="scheduling")
            self.unknown_keys(ent, F.SCHEDULING_KEYS)
            value = self.get(ent, "on_conflict")
            if value is not MISSING:
                modes = [m.value for m in Mode]
                if isinstance(value, str) and value in modes:
                    on_conflict = Mode(value)
                else:
                    code = Code.E012 if isinstance(value, str) else Code.E011
                    hint = suggest(value, modes) if isinstance(value, str) else ""
                    self.fail(
                        ent,
                        code,
                        "on_conflict",
                        detail=f'"on_conflict" must be delay, overflow or error, got {F.describe(value)}{hint}',
                    )
            gap = self.integer(ent, "adjacency_gap_days", F.GAP_DAYS)

        # CLI-1: command-line values win over the file.
        eff_start = overrides.horizon_start or start
        eff_end = overrides.horizon_end or end
        if eff_start is not None and eff_end is not None:
            where = settings_pos
            if horizon_ent is not None:
                if overrides.horizon_end is None and "end" in horizon_ent.field_pos:
                    where = horizon_ent.field_pos["end"]
                elif overrides.horizon_start is None and "start" in horizon_ent.field_pos:
                    where = horizon_ent.field_pos["start"]
            if eff_end < eff_start:
                self.diags.report(Code.E040, where, end=str(eff_end), start=str(eff_start))
            elif months_between(eff_start, eff_end) > F.MAX_HORIZON_MONTHS:
                self.diags.report(Code.E041, where, months=months_between(eff_start, eff_end))

        return Settings(
            title=title if title is not None else "",
            subtitle=subtitle,
            horizon_start=eff_start,
            horizon_end=eff_end,
            today=overrides.today or today or overrides.default_today,
            month_width=month_width if month_width is not None else F.DEFAULT_MONTH_WIDTH,
            content_language=language,
            on_conflict=overrides.on_conflict or on_conflict or Mode.DELAY,
            adjacency_gap_days=gap if gap is not None else F.DEFAULT_GAP_DAYS,
            pos=settings_pos,
        )

    def team_norms(self, top: _Ent) -> TeamNorms:
        """The optional roadmap-wide `team_norms` block (RS 3.2, 7.13); invalid bounds are reported and dropped."""
        node = self.mapping(top, "team_norms")
        if node is None:
            return TeamNorms()
        ent = _Ent(node, where="team_norms", missing_where="team_norms")
        self.unknown_keys(ent, F.TEAM_NORMS_KEYS)
        bands: dict[str, Band] = {}
        for key in F.TEAM_NORMS_KEYS:
            band_node = self.mapping(ent, key)
            if band_node is None:
                continue
            where = f"team_norms.{key}"
            band = _Ent(band_node, where=where, missing_where=where)
            self.unknown_keys(band, F.BAND_KEYS)
            low, high = self.bound(band, "min"), self.bound(band, "max")
            if low is not None and high is not None and low > high:
                self.fail(
                    band, Code.E012, "max", detail=f'"{where}": max must not be below min ({F.describe_number(low)})'
                )
                high = None
            bands[key] = Band(low, high)
        return TeamNorms(**bands)

    def bound(self, ent: _Ent, key: str) -> Fraction | None:
        """A norm bound: an integer or decimal number in NORM_RANGE, kept exact as written."""
        value = self.get(ent, key)
        if value is MISSING:
            return None
        if isinstance(value, bool) or not isinstance(value, int | float):
            self.fail(ent, Code.E011, key, detail=f'"{key}" must be a number, got {F.describe(value)}')
            return None
        low, high = F.NORM_RANGE
        exact = Fraction(str(value)) if math.isfinite(value) else None  # .inf / .nan are out of range
        if exact is None or not low <= exact <= high:
            self.fail(ent, Code.E012, key, detail=f'"{key}" must be {low}–{high}, got {value}')
            return None
        return exact

    def sizes(self, top: _Ent) -> tuple[Size, ...]:
        """Every size label that was written, in order; labels or weeks that fail are reported but kept, so
        projects using them do not get a follow-up E031."""
        node = self.mapping(top, "sizes", required=True)
        if node is None:
            return ()
        if len(node) == 0:
            self.diags.report(Code.E042, top.field_pos["sizes"])
            return ()
        out: list[Size] = []
        for key, weeks in node.items():
            label = str(key) if isinstance(key, str) or F.is_int(key) else None
            key_pos = self.raw.key_pos(node, key)
            if label is None or not F.SIZE_LABEL_RE.match(label):
                shown = label if label is not None else F.describe(key)
                self.diags.report(Code.E012, key_pos, detail=f'size label "{shown}" must be {F.SIZE_LABEL_RULE}')
                if label is None:
                    continue
            value_pos = self.raw.value_pos(node, key)
            if not F.is_int(weeks):
                self.diags.report(
                    Code.E011,
                    value_pos,
                    detail=f'size "{label}" must be a whole number of weeks, got {F.describe(weeks)}',
                )
                weeks = 0
            elif not F.WEEKS[0] <= weeks <= F.WEEKS[1]:
                self.diags.report(
                    Code.E012, value_pos, detail=f'size "{label}" must be {F.WEEKS[0]}–{F.WEEKS[1]} weeks, got {weeks}'
                )
            out.append(Size(label=label, weeks=int(weeks), pos=key_pos))
        return tuple(out)

    def subdomains(self, top: _Ent) -> tuple[tuple[Subdomain, ...], tuple[Team, ...]]:
        items = self.sequence(top, "subdomains", required=True)
        if items is None:
            return (), ()
        if len(items) == 0:
            self.diags.report(Code.E043, top.field_pos["subdomains"])
            return (), ()
        subdomains: list[Subdomain] = []
        teams: list[Team] = []
        for index, node in enumerate(items, start=1):
            if not F.is_mapping(node):
                self.diags.report(
                    Code.E011,
                    self.raw.item_pos(items, index - 1),
                    detail=f"subdomain #{index} must be a mapping, got {F.describe(node)}",
                )
                continue
            ent = _Ent(node, where=f"subdomain #{index}", missing_where=f"subdomain #{index}")
            sid = self.ident(ent, "id", "subdomain", required=True)
            if sid is not None:
                ent.where = f'subdomain "{sid}"'
            self.unknown_keys(ent, F.SUBDOMAIN_KEYS)
            name = self.string(ent, "name", F.SUBDOMAIN_NAME_LEN, required=True)
            description = self.string(ent, "description", F.SUBDOMAIN_DESCRIPTION_LEN)
            team_ids: list[str] = []
            team_items = self.sequence(ent, "teams", required=True)
            for team_index, team_node in enumerate(team_items or (), start=1):
                team = self.team(team_items, team_index, team_node, sid, index)
                if team is not None:
                    teams.append(team)
                    team_ids.append(team.id)
            subdomains.append(
                Subdomain(
                    id=sid if sid is not None else "",
                    name=name if name is not None else (sid or ""),
                    description=description,
                    team_ids=tuple(team_ids),
                    pos=self.raw.node_pos(node),
                    field_pos=MappingProxyType(dict(ent.field_pos)),
                    incomplete=ent.bad,
                )
            )
        return tuple(subdomains), tuple(teams)

    def team(self, items: Any, index: int, node: Any, subdomain_id: str | None, subdomain_index: int) -> Team | None:
        owner = f'subdomain "{subdomain_id}"' if subdomain_id is not None else f"subdomain #{subdomain_index}"
        if not F.is_mapping(node):
            self.diags.report(
                Code.E011,
                self.raw.item_pos(items, index - 1),
                detail=f"team #{index} of {owner} must be a mapping, got {F.describe(node)}",
            )
            return None
        label = f"team #{index} of {owner}"
        ent = _Ent(node, where=label, missing_where=label)
        tid = self.ident(ent, "id", "team", required=True)
        if tid is not None:
            ent.where = f'team "{tid}"'
        self.unknown_keys(ent, F.TEAM_KEYS)
        name = self.string(ent, "name", F.TEAM_NAME_LEN, required=True)
        slots = self.integer(ent, "parallel_projects", F.SLOTS, required=True)
        capacity = Capacity()
        capacity_node = self.mapping(ent, "capacity")
        if capacity_node is not None:
            cap = _Ent(capacity_node, where=f"capacity of {ent.where}", missing_where=f"capacity of {ent.where}")
            self.unknown_keys(cap, F.CAPACITY_KEYS)
            counts = {key: self.integer(cap, key, F.CAPACITY) for key in F.CAPACITY_KEYS}
            capacity = Capacity(**{key: value or 0 for key, value in counts.items()})
            ent.bad = ent.bad or cap.bad
        if tid is None:
            return None  # nothing can refer to it; its problems are reported
        return Team(
            id=tid,
            name=name if name is not None else tid,
            subdomain_id=subdomain_id if subdomain_id is not None else "",
            slots=slots if slots is not None else 1,
            capacity=capacity,
            pos=self.raw.node_pos(node),
            capacity_given="capacity" in node,
            field_pos=MappingProxyType(dict(ent.field_pos)),
            incomplete=ent.bad,
        )

    def products(self, top: _Ent) -> tuple[Product, ...]:
        """The optional `products` list (absent = empty); items without a usable id are reported and dropped."""
        items = self.sequence(top, "products")
        if items is None:
            return ()
        out: list[Product] = []
        for index, node in enumerate(items, start=1):
            if not F.is_mapping(node):
                self.diags.report(
                    Code.E011,
                    self.raw.item_pos(items, index - 1),
                    detail=f"product #{index} must be a mapping, got {F.describe(node)}",
                )
                continue
            ent = _Ent(node, where=f"product #{index}", missing_where=f"product #{index}")
            pid = self.ident(ent, "id", "product", required=True)
            if pid is not None:
                ent.where = f'product "{pid}"'
            self.unknown_keys(ent, F.PRODUCT_KEYS)
            name = self.string(ent, "name", F.PRODUCT_NAME_LEN, required=True)
            domain = self.get(ent, "domain", required=True)
            domain_id: str | None = None
            if isinstance(domain, str):
                domain_id = domain
            elif domain is not MISSING:
                self.fail(ent, Code.E011, "domain", detail=f'"domain" must be a subdomain id, got {F.describe(domain)}')
            owner = self.string(ent, "owner", F.PRODUCT_OWNER_LEN)
            description = self.string(ent, "description", F.PRODUCT_DESCRIPTION_LEN)
            color = self.color(ent)
            if pid is None:
                continue  # nothing can refer to it; its problems are reported
            out.append(
                Product(
                    id=pid,
                    name=name if name is not None else pid,
                    domain_id=domain_id if domain_id is not None else "",
                    owner=owner or None,
                    description=description or None,
                    color=color,
                    pos=self.raw.node_pos(node),
                    field_pos=MappingProxyType(dict(ent.field_pos)),
                    incomplete=ent.bad,
                )
            )
        return tuple(out)

    def color(self, ent: _Ent) -> ColorSpec | None:
        """A palette name or `#RRGGBB` (E033), shared by projects and products."""
        value = self.get(ent, "color")
        if isinstance(value, str):
            if value in F.PALETTE_NAMES:
                return ColorSpec(palette_name=value, hex=None, text=value)
            if F.HEX_RE.match(value):
                return ColorSpec(palette_name=None, hex=value.upper(), text=value)
            self.fail(ent, Code.E033, "color", color=value)
        elif value is not MISSING:
            self.fail(ent, Code.E011, "color", detail=f'"color" must be a string, got {F.describe(value)}')
        return None

    def projects(self, top: _Ent) -> tuple[Project, ...]:
        items = self.sequence(top, "projects", required=True)
        if items is None:
            return ()
        out: list[Project] = []
        for seq, node in enumerate(items, start=1):
            if not F.is_mapping(node):
                pos = self.raw.item_pos(items, seq - 1)
                self.diags.report(Code.E011, pos, detail=f"project #{seq} must be a mapping, got {F.describe(node)}")
                out.append(_placeholder(seq, pos))
                continue
            out.append(self.project(seq, node))
        return tuple(out)

    def project(self, seq: int, node: Any) -> Project:
        raw = self.raw
        ent = _Ent(node, where=f"project #{seq}", missing_where=f"project #{seq}")
        name = self.string(ent, "name", F.PROJECT_NAME_LEN, required=True)
        if name is not None:
            ent.where = f'project "{name}"'
        self.unknown_keys(ent, F.PROJECT_KEYS)
        pid = self.ident(ent, "id", "project")

        team = self.get(ent, "team", required=True)
        team_id: str | None = None
        if isinstance(team, str):
            team_id = team
        elif team is not MISSING:
            self.fail(ent, Code.E011, "team", detail=f'"team" must be a team id, got {F.describe(team)}')

        product = self.get(ent, "product")
        product_id: str | None = None
        if isinstance(product, str):
            product_id = product
        elif product is not MISSING:
            self.fail(ent, Code.E011, "product", detail=f'"product" must be a product id, got {F.describe(product)}')

        start = self.month(ent, "start")
        if "start" in node and start is None:
            ent.bad = True

        size_value = self.get(ent, "size")
        size: str | None = None
        if isinstance(size_value, str):
            size = size_value
        elif F.is_int(size_value):
            size = str(size_value)
        elif size_value is not MISSING:
            self.fail(ent, Code.E011, "size", detail=f'"size" must be a size label, got {F.describe(size_value)}')

        ongoing_value = self.get(ent, "ongoing")
        ongoing = False
        ongoing_ok = True
        if isinstance(ongoing_value, bool):
            ongoing = ongoing_value
        elif ongoing_value is not MISSING:
            self.fail(
                ent, Code.E011, "ongoing", detail=f'"ongoing" must be true or false, got {F.describe(ongoing_value)}'
            )
            ongoing_ok = False

        size_given = size_value is not MISSING
        if ongoing_ok and size_given == ongoing:  # both, or neither (RS 3.2)
            self.fail(ent, Code.E032, "size", project=name if name is not None else f"#{seq}")

        refs = self.depends_on(ent)
        description = self.string(ent, "description", F.PROJECT_DESCRIPTION_LEN)

        color = self.color(ent)

        return Project(
            seq=seq,
            id=pid,
            name=name,
            team_id=team_id,
            start=start,
            size=size,
            ongoing=ongoing,
            depends_on_refs=refs,
            description=description,
            color=color,
            pos=raw.node_pos(node),
            product_id=product_id,
            field_pos=MappingProxyType(dict(ent.field_pos)),
            field_column=MappingProxyType(dict(ent.field_column)),
            incomplete=ent.bad,
        )

    def depends_on(self, ent: _Ent) -> tuple[DepRef, ...]:
        """A list of ids or names, or a single string (RS IN-9)."""
        value = self.get(ent, "depends_on")
        if value is MISSING:
            return ()
        if isinstance(value, str):
            return (DepRef(text=value, pos=ent.field_pos["depends_on"]),)
        if not F.is_list(value):
            self.fail(
                ent,
                Code.E011,
                "depends_on",
                detail=f'"depends_on" must be a list of project ids or names, got {F.describe(value)}',
            )
            return ()
        refs: list[DepRef] = []
        for index, item in enumerate(value):
            pos = self.raw.item_pos(value, index, ent.node, "depends_on")
            if isinstance(item, str):
                refs.append(DepRef(text=item, pos=pos))
            else:
                self.diags.report(
                    Code.E011,
                    pos,
                    column=self.raw.column_label(ent.node, "depends_on"),
                    detail=f'"depends_on" items must be project ids or names, got {F.describe(item)}',
                )
                ent.bad = True
        return tuple(refs)


def _placeholder(seq: int, pos: Pos) -> Project:
    """Stands in for a projects[] item that is not a mapping, so seq numbers keep matching file order."""
    return Project(
        seq=seq,
        id=None,
        name=None,
        team_id=None,
        start=None,
        size=None,
        ongoing=False,
        depends_on_refs=(),
        description=None,
        color=None,
        pos=pos,
        incomplete=True,
    )


def build_model(raw: RawDoc, diags: Collector, overrides: Overrides) -> Model | None:
    """Build the model with CLI overrides applied (RS CLI-1). Invalid fields become None and their entity is
    marked incomplete, so reference checks can still run (ADS 8.2). Returns None only when the document is too
    broken to describe a roadmap at all (e.g. not a mapping, or version missing or not 1)."""
    return _Builder(raw, diags).build(overrides)
