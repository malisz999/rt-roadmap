"""Load: input bytes → RawDoc with positions (ADS 4.2). E001, E003, E011 (tags); BOM stripped; every scalar NFC.

The tree is ruamel's round-trip tree (`YAML(typ="rt")`, YAML 1.2), so `NO` and `yes` stay strings (RS IN-1) and
every mapping and sequence keeps its 0-based line/column info. Strings are NFC-normalised in place without
losing that info (ADR-8, RS IN-8). Unquoted dates such as `2026-10-23` stay `datetime.date` (RS IN-2); an
impossible date such as `2026-02-30` stays the string as written, so the validator reports it as E013.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq, TaggedScalar
from ruamel.yaml.constructor import DuplicateKeyError, RoundTripConstructor
from ruamel.yaml.error import MarkedYAMLError, YAMLError
from ruamel.yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode
from ruamel.yaml.reader import ReaderError
from ruamel.yaml.scalarstring import ScalarString

from rt.diagnostics import Code, Collector, Pos
from rt.io.rawdoc import RawDoc
from rt.io.streams import MAX_INPUT_BYTES

__all__ = ["load", "load_text", "make_yaml"]

_CORE = "tag:yaml.org,2002:"
# Tags a document may carry: the YAML 1.2 core schema, timestamps (IN-2) and merge keys. Anything else is E011
# (ADS 9.5, C2), e.g. `!foo`, `!!binary`, `!!set`, `!!omap`, `!!python/object`.
_ALLOWED_TAGS = frozenset(
    _CORE + t for t in ("str", "int", "float", "bool", "null", "map", "seq", "timestamp", "merge")
)


class _Constructor(RoundTripConstructor):
    """Round-trip constructor that records non-core tags and tolerates impossible dates."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.bad_tags: list[tuple[str, int, int]] = []  # (tag, 0-based line, 0-based column)

    def construct_object(self, node: Any, deep: bool = False) -> Any:
        tag = getattr(node.tag, "value", node.tag)
        if isinstance(tag, str) and tag not in _ALLOWED_TAGS:
            self.bad_tags.append((tag, node.start_mark.line, node.start_mark.column))
        return super().construct_object(node, deep)

    def construct_yaml_timestamp(self, node: Any, values: Any = None) -> Any:
        try:
            return super().construct_yaml_timestamp(node, values)
        except ValueError:  # e.g. 2026-02-30: keep the text, the validator reports E013 at its position
            return self.construct_scalar(node)


_Constructor.add_constructor(_CORE + "timestamp", _Constructor.construct_yaml_timestamp)


def make_yaml() -> YAML:
    """The round-trip YAML 1.2 instance rt loads with (also usable by rt convert for the base file)."""
    yaml = YAML(typ="rt")
    yaml.Constructor = _Constructor
    return yaml


def load(data: bytes, source: str, diags: Collector) -> RawDoc | None:
    """Decode UTF-8 (BOM accepted) and parse YAML 1.2 with ruamel's round-trip loader.

    Reports E001 (empty or whitespace-only input, input over 5 MB, undecodable bytes, YAML syntax error),
    E003 (duplicate key) and E011 (non-core tag), then returns None; otherwise returns the tree with every
    scalar string NFC-normalised.
    """
    if len(data) > MAX_INPUT_BYTES:
        diags.report(Code.E001, Pos(1, 1, source), detail="input too large (more than 5 MB)")
        return None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        line = data.count(b"\n", 0, exc.start) + 1
        line_start = data.rfind(b"\n", 0, exc.start) + 1
        byte = data[exc.start]
        diags.report(
            Code.E001,
            Pos(line, exc.start - line_start + 1, source),
            detail=f"input is not valid UTF-8: cannot decode byte 0x{byte:02X} at line {line}, "
            f"byte {exc.start - line_start + 1}",
        )
        return None
    return load_text(text, source, diags)


def load_text(text: str, source: str, diags: Collector) -> RawDoc | None:
    """Parse already decoded text; see load(). A leading BOM character is ignored, and CRLF line breaks (files saved
    on Windows) become LF, so round-tripped comments never carry a stray CR into rt convert's LF output (RS CV-18)."""
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    if not text.strip():
        diags.report(Code.E001, Pos(1, 1, source), detail="input is empty (did the previous command fail?)")
        return None
    yaml = make_yaml()
    try:
        root = yaml.load(text)
    except DuplicateKeyError as exc:
        _report_duplicates(text, source, diags, exc)
        return None
    except MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        problem = exc.problem or exc.context or "syntax error"
        pos = Pos(mark.line + 1, mark.column + 1, source) if mark is not None else Pos(1, 1, source)
        diags.report(Code.E001, pos, detail=f"invalid YAML: {problem}")
        return None
    except ReaderError as exc:
        diags.report(Code.E001, _index_pos(text, exc.position, source), detail=f"invalid YAML: {exc.reason}")
        return None
    except YAMLError as exc:  # pragma: no cover - ruamel raises the subclasses above
        diags.report(Code.E001, Pos(1, 1, source), detail=f"invalid YAML: {exc}")
        return None

    bad_tags: list[tuple[str, int, int]] = yaml.constructor.bad_tags
    if bad_tags:
        for tag, line, col in sorted(set(bad_tags), key=lambda t: (t[1], t[2], t[0])):
            shown = tag.replace(_CORE, "!!", 1)
            diags.report(Code.E011, Pos(line + 1, col + 1, source), detail=f'tag "{shown}" is not allowed; remove it')
        return None

    duplicates: list[tuple[str, Pos]] = []
    root = _normalise(root, source, duplicates, set())
    if duplicates:
        for key, pos in duplicates:
            diags.report(Code.E003, pos, key=key)
        return None
    return RawDoc(root=root, source=source)


# --- helpers ------------------------------------------------------------------------------------------------------


def _index_pos(text: str, index: int, source: str) -> Pos:
    line = text.count("\n", 0, index) + 1
    line_start = text.rfind("\n", 0, index) + 1
    return Pos(line, index - line_start + 1, source)


def _report_duplicates(text: str, source: str, diags: Collector, exc: DuplicateKeyError) -> None:
    """Report every duplicate key in the document (RS IN-4, IN-6) by walking the composed node tree."""
    found: list[tuple[str, Pos]] = []
    try:
        node = make_yaml().compose(text)
    except YAMLError:  # pragma: no cover - the document composed once already
        node = None
    if node is not None:
        _find_duplicates(node, source, found, set())
    if not found:  # pragma: no cover - fall back to ruamel's own report
        mark = exc.problem_mark
        found.append(("?", Pos(mark.line + 1, mark.column + 1, source) if mark else Pos(1, 1, source)))
    for key, pos in sorted(found, key=lambda kp: (kp[1].line, kp[1].col)):
        diags.report(Code.E003, pos, key=key)


def _find_duplicates(node: Node, source: str, found: list[tuple[str, Pos]], seen: set[int]) -> None:
    if id(node) in seen:
        return
    seen.add(id(node))
    if isinstance(node, MappingNode):
        keys: set[tuple[str, str]] = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode):
                tag = getattr(key_node.tag, "value", key_node.tag)
                ident = (str(tag), unicodedata.normalize("NFC", key_node.value))
                if ident in keys:
                    mark = key_node.start_mark
                    found.append((ident[1], Pos(mark.line + 1, mark.column + 1, source)))
                keys.add(ident)
            _find_duplicates(key_node, source, found, seen)
            _find_duplicates(value_node, source, found, seen)
    elif isinstance(node, SequenceNode):
        for item in node.value:
            _find_duplicates(item, source, found, seen)


def _normalise_scalar(value: Any) -> Any:
    """NFC for strings (keeping ruamel's string subclasses); `!!str` tagged scalars become plain strings."""
    if isinstance(value, TaggedScalar):
        return unicodedata.normalize("NFC", str(value.value))
    if isinstance(value, str):
        if unicodedata.is_normalized("NFC", value):
            return value
        normal = unicodedata.normalize("NFC", value)
        return type(value)(normal) if isinstance(value, ScalarString) else normal
    return value


def _normalise(node: Any, source: str, duplicates: list[tuple[str, Pos]], seen: set[int]) -> Any:
    """NFC every string key and value in place, keeping order, positions and comments."""
    if isinstance(node, CommentedMap):
        if id(node) in seen:
            return node
        seen.add(id(node))
        for key in list(node.keys()):
            value = node[key]
            normal = _normalise(value, source, duplicates, seen)
            if normal is not value:
                node[key] = normal
        renamed = [k for k in node if isinstance(k, str) and not unicodedata.is_normalized("NFC", k)]
        for old in renamed:
            new = unicodedata.normalize("NFC", old)
            if new in node:  # two keys that are equal after NFC (RS IN-4, IN-8)
                line, col = node.lc.key(old)
                duplicates.append((new, Pos(line + 1, col + 1, source)))
                continue
            index = list(node.keys()).index(old)
            value = node.pop(old)
            node.insert(index, new, value)
            if old in node.lc.data:
                node.lc.data[new] = node.lc.data.pop(old)
            if old in node.ca.items:
                node.ca.items[new] = node.ca.items.pop(old)
        return node
    if isinstance(node, CommentedSeq):
        if id(node) in seen:
            return node
        seen.add(id(node))
        for index, item in enumerate(node):
            normal = _normalise(item, source, duplicates, seen)
            if normal is not item:
                node[index] = normal
        return node
    return _normalise_scalar(node)
