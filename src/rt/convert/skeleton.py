"""Skeleton mode: generated settings, subdomains and teams with slug ids (RS CV-14, CV-15; ADS 6.8 step 6)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from ruamel.yaml.comments import CommentedMap, CommentedSeq

DEFAULT_TITLE = "Roadmap"
DEFAULT_SUBDOMAIN = "Roadmap"
DEFAULT_TEAM = "Team"
DEFAULT_SLOTS = 1
DEFAULT_SIZES: tuple[tuple[str, int], ...] = (("XS", 1), ("S", 2), ("M", 4), ("L", 8), ("XL", 13), ("XXL", 26))
ID_MAX = 40

_NON_ID = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """`Płatności Łódź` → `platnosci-lodz`; may be empty (RS CV-15)."""
    t = text.replace("ł", "l").replace("Ł", "L")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = _NON_ID.sub("-", t).strip("-")
    return t[:ID_MAX].strip("-")


def unique_slug(text: str, taken: set[str], fallback: str) -> str:
    """slug() with `fallback` for an empty result and `-2`, `-3`… on collision, kept within 40 characters."""
    base = slug(text) or fallback
    candidate, n = base, 2
    while candidate in taken:
        suffix = f"-{n}"
        candidate = base[: ID_MAX - len(suffix)] + suffix
        n += 1
    taken.add(candidate)
    return candidate


@dataclass
class SkeletonTeam:
    name: str
    subdomain: str
    line: int  # CSV line of the team's first row
    node: CommentedMap = field(default_factory=CommentedMap)


@dataclass
class SkeletonSubdomain:
    name: str
    line: int
    teams: list[SkeletonTeam] = field(default_factory=list)
    node: CommentedMap = field(default_factory=CommentedMap)


@dataclass
class Skeleton:
    """Collects subdomains and teams in order of first appearance, then builds the YAML tree."""

    title: str = DEFAULT_TITLE
    sizes: Sequence[tuple[str, int]] = DEFAULT_SIZES
    slots: int = DEFAULT_SLOTS
    subdomains: dict[str, SkeletonSubdomain] = field(default_factory=dict)
    teams: dict[str, SkeletonTeam] = field(default_factory=dict)
    team_ids: dict[str, str] = field(default_factory=dict)

    @property
    def size_labels(self) -> list[str]:
        return [label for label, _ in self.sizes]

    def add(self, team: str, subdomain: str, line: int) -> SkeletonTeam:
        """Register a row's team and subdomain; returns the team as first seen (its subdomain may differ from
        `subdomain`, which the caller reports as E107)."""
        known = self.teams.get(team)
        if known is not None:
            return known
        sub = self.subdomains.get(subdomain)
        if sub is None:
            sub = self.subdomains[subdomain] = SkeletonSubdomain(subdomain, line)
        created = self.teams[team] = SkeletonTeam(team, subdomain, line)
        sub.teams.append(created)
        return created

    def build(self) -> CommentedMap:
        """The document without `projects`; fills `team_ids` (team name → generated id)."""
        taken_sd: set[str] = set()
        taken_tm: set[str] = set()
        sd_ids = {name: unique_slug(name, taken_sd, "subdomain") for name in self.subdomains}
        self.team_ids = {name: unique_slug(name, taken_tm, "team") for name in self.teams}
        doc = CommentedMap()
        doc["version"] = 1
        roadmap = CommentedMap()
        roadmap["title"] = self.title
        doc["roadmap"] = roadmap
        sizes = CommentedMap()
        for label, weeks in self.sizes:
            sizes[label] = weeks
        doc["sizes"] = sizes
        subs = CommentedSeq()
        for sub in self.subdomains.values():
            sd = sub.node
            sd["id"] = sd_ids[sub.name]
            sd["name"] = sub.name
            teams = CommentedSeq()
            for team in sub.teams:
                tm = team.node
                tm["id"] = self.team_ids[team.name]
                tm["name"] = team.name
                tm["parallel_projects"] = self.slots
                teams.append(tm)
            sd["teams"] = teams
            subs.append(sd)
        doc["subdomains"] = subs
        return doc
