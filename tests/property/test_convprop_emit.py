"""The fast project emitter is byte-identical to ruamel's own dump (RS CV-18, NF-11)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from rt.convert.emit import dump, dump_slow, header_comment
from rt.convert.skeleton import Skeleton

TRICKY = [
    "yes",
    "no",
    "NO",
    "true",
    "null",
    "~",
    "123",
    "0o17",
    "1e3",
    "2027-01",
    "2027-01-15",
    "-",
    "- x",
    "? x",
    "a: b",
    "a #b",
    "#x",
    "[x]",
    "{x}",
    "x,y",
    "&a",
    "*a",
    "!x",
    "|",
    ">",
    "'q'",
    '"q"',
    "%x",
    "@x",
    "`x",
    " lead",
    "trail ",
    "multi\nline",
    "tab\there",
    "Płatności – łańcuch",
    "ąćęłńóśźż",
    "a b",
    "x" * 300,
]
TEXT = st.one_of(
    st.sampled_from(TRICKY),
    st.text(alphabet=st.sampled_from(list("aZ0 :#,[]{}-?'\"!&*|>%@`łŻ\n\t.")), min_size=1, max_size=20),
)


@st.composite
def projects(draw: st.DrawFn) -> list[CommentedMap]:
    out = []
    for _ in range(draw(st.integers(1, 6))):
        p = CommentedMap()
        if draw(st.booleans()):
            p["id"] = draw(TEXT)
        p["name"] = draw(TEXT)
        p["team"] = draw(TEXT)
        if draw(st.booleans()):
            p["start"] = draw(TEXT)
        if draw(st.booleans()):
            p["size"] = draw(TEXT)
        if draw(st.booleans()):
            p["ongoing"] = True
        deps = draw(st.lists(TEXT, max_size=3))
        if deps:
            seq = CommentedSeq(deps)
            seq.fa.set_flow_style()
            p["depends_on"] = seq
        if draw(st.booleans()):
            p["description"] = draw(TEXT)
        out.append(p)
    return out


@settings(max_examples=300, deadline=None)
@given(projects())
def test_fast_dump_equals_ruamel(items: list[CommentedMap]) -> None:
    sk = Skeleton()
    sk.add("Team", "Roadmap", 2)
    doc = sk.build()
    doc["projects"] = CommentedSeq(items)
    assert dump(doc, "x.csv") == header_comment("x.csv") + dump_slow(doc)
