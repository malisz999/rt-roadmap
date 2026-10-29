"""Field specs of the input format (RS 3.2): allowed keys, patterns, ranges and value descriptions."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
SIZE_LABEL_RE = re.compile(r"^[A-Za-z0-9+]{1,8}$")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
LANG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")

ID_RULE = 'lower-case letters, digits, "-" or "_", starting with a letter or digit, at most 40 characters'
SIZE_LABEL_RULE = 'letters, digits or "+", 1–8 characters'

# Palette names in palette order (RS 5.3); colour values live in rt.color.
PALETTE_NAMES: tuple[str, ...] = (
    "indigo",
    "green",
    "orange",
    "pink",
    "sky",
    "amber",
    "violet",
    "teal",
    "lime",
    "sand",
    "blue",
    "cyan",
    "emerald",
    "yellow",
    "fuchsia",
    "purple",
    "stone",
    "sand-deep",
    "indigo-deep",
    "green-deep",
    "orange-deep",
    "pink-deep",
    "sky-deep",
    "amber-deep",
    "violet-deep",
    "teal-deep",
    "lime-deep",
    "blue-deep",
    "cyan-deep",
    "emerald-deep",
    "fuchsia-deep",
    "purple-deep",
)

TOP_KEYS: tuple[str, ...] = ("version", "roadmap", "sizes", "scheduling", "subdomains", "products", "projects")
ROADMAP_KEYS: tuple[str, ...] = ("title", "subtitle", "horizon", "today", "month_width", "content_language")
HORIZON_KEYS: tuple[str, ...] = ("start", "end")
SCHEDULING_KEYS: tuple[str, ...] = ("on_conflict", "adjacency_gap_days")
SUBDOMAIN_KEYS: tuple[str, ...] = ("id", "name", "description", "teams")
TEAM_KEYS: tuple[str, ...] = ("id", "name", "parallel_projects", "capacity")
CAPACITY_KEYS: tuple[str, ...] = ("developers", "product_managers", "analysts", "testers")
PRODUCT_KEYS: tuple[str, ...] = ("id", "name", "domain", "owner", "description", "color")
PROJECT_KEYS: tuple[str, ...] = (
    "id",
    "name",
    "team",
    "product",
    "start",
    "size",
    "ongoing",
    "depends_on",
    "description",
    "color",
)

# Lengths and ranges (RS 3.2)
TITLE_LEN = (1, 120)
SUBTITLE_LEN = (0, 200)
SUBDOMAIN_NAME_LEN = (1, 80)
SUBDOMAIN_DESCRIPTION_LEN = (0, 300)
TEAM_NAME_LEN = (1, 60)
PROJECT_NAME_LEN = (1, 100)
PROJECT_DESCRIPTION_LEN = (0, 500)
PRODUCT_NAME_LEN = (1, 100)
PRODUCT_OWNER_LEN = (0, 100)
PRODUCT_DESCRIPTION_LEN = (0, 500)
MONTH_WIDTH = (60, 400)
DEFAULT_MONTH_WIDTH = 120
SLOTS = (1, 12)
CAPACITY = (0, 999)
WEEKS = (1, 520)
GAP_DAYS = (0, 90)
DEFAULT_GAP_DAYS = 14
MAX_HORIZON_MONTHS = 120


def is_int(value: Any) -> bool:
    """A YAML integer; booleans are not integers (RS 3.2, E011)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_mapping(value: Any) -> bool:
    return isinstance(value, dict)


def is_list(value: Any) -> bool:
    return isinstance(value, list)


def describe(value: Any) -> str:
    """How a wrong value is shown after `got` in messages."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int | float):
        return str(value)
    if is_mapping(value):
        return "a mapping"
    if is_list(value):
        return "a list"
    return type(value).__name__


def as_text(value: Any) -> str:
    """A scalar as the user wrote it, for messages that quote the value (E013)."""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
