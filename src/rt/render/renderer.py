"""PageVM → HTML (ADS 7). No logic beyond loops and conditionals in templates."""

from __future__ import annotations

import re
from functools import cache
from importlib import resources

from jinja2 import Environment, PackageLoader, StrictUndefined
from markupsafe import Markup

from rt.layout.viewmodel import PageVM

__all__ = ["render_html", "stylesheet"]


@cache
def _environment() -> Environment:
    """The Jinja environment exactly as ADS 7.3 fixes it."""
    return Environment(
        loader=PackageLoader("rt", "render/templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


@cache
def stylesheet() -> str:
    """The bundled stylesheet, inlined into the page's one `<style>` element (RS OUT-2)."""
    text = resources.files("rt.render").joinpath("static/rt.css").read_text(encoding="utf-8")
    return compact_css(text)


_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_AROUND_PUNCT = re.compile(r"\s*([{};])\s*")
_SPACE = re.compile(r"\s+")
_AFTER_COLON = re.compile(r": ")


def compact_css(text: str) -> str:
    """Drop comments, the whitespace around braces and semicolons, and the space after `:` (`left:24px`).
    Commas keep their space, so the font stack reads exactly as RS OUT-3 writes it; no `content` string in the
    stylesheet contains `: `."""
    text = _COMMENT.sub("", text)
    text = _AROUND_PUNCT.sub(r"\1", text)
    return _AFTER_COLON.sub(":", _SPACE.sub(" ", text)).strip()


def render_html(page: PageVM) -> str:
    """One self-contained UTF-8 HTML5 document with LF line endings (RS OUT-1 to OUT-5)."""
    # The stylesheet and the generated `:root` sizes are numbers and rt's own text only (ADS 9.5).
    css = Markup(stylesheet() + page.css_vars + "\n")
    html = _environment().get_template("page.html.j2").render(page=page, css=css)
    return html.replace("\r\n", "\n")
