"""Helpers for the io, model and cli/app unit tests (developer A)."""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

from rt.cli import main
from rt.diagnostics import Collector
from rt.io.loader import load
from rt.io.rawdoc import RawDoc
from rt.io.streams import FakeIO
from rt.model.build import build_model
from rt.model.references import check_references
from rt.model.types import Model, Overrides, ResolvedModel

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "docs" / "fixtures"
TODAY = date(2026, 10, 24)

MINIMAL = """\
version: 1
roadmap:
  title: T
sizes:
  S: 2
  M: 4
subdomains:
  - id: core
    name: Core
    teams:
      - id: alpha
        name: Alpha
        parallel_projects: 2
projects:
  - name: First
    team: alpha
    size: M
    start: 2027-01
"""


def doc(text: str) -> str:
    return textwrap.dedent(text)


def load_raw(text: str, source: str = "r.yaml") -> tuple[RawDoc | None, Collector]:
    diags = Collector(source)
    return load(text.encode("utf-8"), source, diags), diags


def build(text: str, overrides: Overrides | None = None) -> tuple[Model | None, Collector]:
    raw, diags = load_raw(text)
    assert raw is not None, [str(d) for d in diags.items]
    return build_model(raw, diags, overrides or Overrides(default_today=TODAY)), diags


def resolve(text: str, overrides: Overrides | None = None) -> tuple[ResolvedModel | None, Collector]:
    model, diags = build(text, overrides)
    if model is None:
        return None, diags
    return check_references(model, diags), diags


def codes(diags: Collector) -> list[tuple[str, int | None, int | None]]:
    """(code, line, column) of every diagnostic, sorted."""
    return [(d.code.name, d.line, d.col) for d in diags.sorted()]


def messages(diags: Collector) -> list[str]:
    return [d.message for d in diags.sorted()]


def run(argv: list[str], **kwargs: object) -> tuple[int, FakeIO]:
    io = FakeIO(**kwargs)  # type: ignore[arg-type]
    return main(argv, io), io
