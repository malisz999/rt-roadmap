"""Plan → JSON text (RS PL-1 to PL-6)."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from rt.plan.types import Plan
from rt.timeutil import Month


def to_jsonable(value: Any) -> Any:
    """Dataclasses → dicts in field order (skipping `{"json": False}` fields); dates `YYYY-MM-DD`; months
    `YYYY-MM`; Decimal → float; enums → their value; tuples → lists."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value) if f.metadata.get("json", True)}
    if isinstance(value, Month):  # a NamedTuple: check before tuple
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if isinstance(value, (tuple, list)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float)):
        return value
    raise TypeError(f"cannot serialise {type(value).__name__} in the plan")


def to_json(plan: Plan) -> str:
    """UTF-8 text, 2-space indent, keys in dataclass field order, non-ASCII unescaped, trailing newline."""
    return json.dumps(to_jsonable(plan), indent=2, ensure_ascii=False) + "\n"
