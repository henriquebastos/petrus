"""Canonical Petri-net Graphviz presentation and local rendering."""

from __future__ import annotations

import subprocess
from pathlib import Path
from xml.etree import ElementTree

import pytest

from petrus.impetus.petrinet.dot import render, to_dot
from petrus.impetus.petrinet.marking import Marking, Token
from petrus.impetus.petrinet.schema import (
    AnonymousDeclaration,
    Arc,
    ArcMode,
    Cel,
    Delay,
    Net,
    NetPath,
    Place,
    Transition,
    Until,
)


def _golden_net() -> Net:
    source = NetPath("scope.input")
    transition = NetPath("scope.run")
    target = NetPath("scope.output")
    return Net(
        [Place(source, "Work"), Place(target)],
        [Transition(transition, handler="process", guards=("ready",), timers=(Delay(5),))],
        [Arc(source, transition), Arc(transition, target)],
        name="example",
    )


@pytest.mark.parametrize(
    (
        "theme",
        "direction",
        "background",
        "cluster",
        "primary",
        "secondary",
        "place",
        "transition",
        "consume",
        "rankdir",
    ),
    [
        ("dark", "top-down", "#0d1117", "#161b22", "#e6edf3", "#8b949e", "#58a6ff", "#d29922", "#8b949e", "TB"),
        ("dark", "left-right", "#0d1117", "#161b22", "#e6edf3", "#8b949e", "#58a6ff", "#d29922", "#8b949e", "LR"),
        ("light", "top-down", "#ffffff", "#f6f8fa", "#1f2328", "#59636e", "#0969da", "#9a6700", "#57606a", "TB"),
        ("light", "left-right", "#ffffff", "#f6f8fa", "#1f2328", "#59636e", "#0969da", "#9a6700", "#57606a", "LR"),
    ],
)
def test_to_dot_has_deterministic_golden_source_for_each_presentation(
    theme: str,
    direction: str,
    background: str,
    cluster: str,
    primary: str,
    secondary: str,
    place: str,
    transition: str,
    consume: str,
    rankdir: str,
) -> None:
    expected = f'''digraph "impetus" {{
  graph [bgcolor="{background}", fontcolor="{primary}", fontname="Helvetica", label="example", labelloc="t", nodesep="0.6", pad="0.25", rankdir="{rankdir}", ranksep="1.0"];
  node [fontcolor="{primary}", fontname="Helvetica"];
  edge [fontcolor="{secondary}", fontname="Helvetica", fontsize="10"];
  subgraph "cluster_0" {{
    graph [color="{secondary}", fillcolor="{cluster}", fontcolor="{secondary}", label="scope", style="filled", tooltip="scope"];
    "p0" [color="{place}", fillcolor="{background}", label=<<TABLE BORDER="0" CELLBORDER="0" CELLPADDING="1"><TR><TD><B><FONT COLOR="{primary}" POINT-SIZE="14">input</FONT></B></TD></TR><TR><TD><FONT COLOR="{secondary}" POINT-SIZE="9">Work</FONT></TD></TR></TABLE>>, shape="ellipse", style="filled", tooltip="scope.input"];
    "p1" [color="{place}", fillcolor="{background}", label=<<TABLE BORDER="0" CELLBORDER="0" CELLPADDING="1"><TR><TD><B><FONT COLOR="{primary}" POINT-SIZE="14">output</FONT></B></TD></TR></TABLE>>, shape="ellipse", style="filled", tooltip="scope.output"];
    "t0" [color="{transition}", fillcolor="{cluster}", label=<<TABLE BORDER="0" CELLBORDER="0" CELLPADDING="1"><TR><TD><B><FONT COLOR="{primary}" POINT-SIZE="14">run</FONT></B></TD></TR><TR><TD><FONT COLOR="{secondary}" POINT-SIZE="9">handler: process · guard: ready · delay: 5</FONT></TD></TR></TABLE>>, shape="box", style="rounded,filled", tooltip="scope.run\\nhandler: process\\nguards: ready\\ntimers: delay: 5"];
  }}
  "p0" -> "t0" [arrowhead="normal", color="{consume}", label="Work", style="solid", tooltip="scope.input -> scope.run"];
  "t0" -> "p1" [arrowhead="normal", color="{consume}", style="solid", tooltip="scope.run -> scope.output"];
}}
'''

    assert to_dot(_golden_net(), theme=theme, direction=direction) == expected
    assert to_dot(_golden_net(), theme=theme, direction=direction) == expected


@pytest.mark.parametrize(
    ("theme", "marked_color", "consume_color", "read_color", "inhibit_color"),
    [
        ("dark", "#1f6feb", "#8b949e", "#58a6ff", "#f85149"),
        ("light", "#ddf4ff", "#57606a", "#0969da", "#cf222e"),
    ],
)
def test_to_dot_presents_marking_declarations_and_every_arc_semantic(
    theme: str,
    marked_color: str,
    consume_color: str,
    read_color: str,
    inhibit_color: str,
) -> None:
    consume = NetPath("flow.consume")
    read = NetPath("flow.read")
    inhibit = NetPath("flow.inhibit")
    done = NetPath("flow.done")
    run = NetPath("flow.run")
    net = Net(
        [Place(consume), Place(read), Place(inhibit), Place(done)],
        [Transition(run, handler="handle", guards=(Cel("binding.ok"), "allowed"), timers=(Delay(2), Until(9)))],
        [
            Arc(consume, run, weight=2, color="Job", filter=Cel('token.kind == "ready"')),
            Arc(read, run, mode=ArcMode.READ, filter="visible"),
            Arc(inhibit, run, mode=ArcMode.INHIBIT, color="Blocker"),
            Arc(run, done, color="Result"),
        ],
    )
    marking = Marking({consume: (Token("Job", {"secret": "must-not-render"}), Token("Job", object()))})

    source = to_dot(net, marking, theme=theme)  # type: ignore[arg-type]

    assert f'fillcolor="{marked_color}", label=<' in source
    assert f'<FONT COLOR="{marked_color}"' not in source
    assert ">consume</FONT>" in source
    assert ">2 tokens</FONT>" in source
    assert "secret" not in source
    assert ">run</FONT>" in source
    assert ">handler: handle · 2 guards · 2 timers</FONT>" in source
    assert (
        'tooltip="flow.run\\nhandler: handle\\nguards: cel: binding.ok; allowed\\ntimers: delay: 2; until: 9"' in source
    )
    assert f'color="{consume_color}", label="2× · Job · filter: cel: token.kind == \\"ready\\""' in source
    assert f'color="{read_color}", label="read · filter: visible", style="dashed"' in source
    assert f'arrowhead="odot", color="{inhibit_color}", label="inhibit · Blocker", style="dashed"' in source
    assert 'label="Result", style="solid"' in source


def test_to_dot_groups_top_level_scopes_with_opt_out() -> None:
    net = _golden_net()

    assert 'subgraph "cluster_0"' in to_dot(net)
    assert "subgraph" not in to_dot(net, group_scopes=False)


def test_to_dot_preserves_parallel_arcs_and_escapes_user_text() -> None:
    place = NetPath('scope.in"put')
    transition = NetPath("scope.run")
    net = Net(
        [Place(place, 'A "<quoted>" & \\ color')],
        [Transition(transition, handler='handle "this"\\now')],
        [Arc(place, transition), Arc(place, transition)],
        name='net "name"\\literal',
    )

    source = to_dot(net)

    assert 'label="net \\"name\\"\\\\literal"' in source
    assert ">in&quot;put</FONT>" in source
    assert ">A &quot;&lt;quoted&gt;&quot; &amp; \\ color</FONT>" in source
    assert "handler: handle &quot;this&quot;\\now" in source
    assert 'tooltip="scope.in\\"put -> scope.run"' in source
    assert source.count('"p0" -> "t0"') == 2


def test_to_dot_normalizes_graphviz_text_without_losing_unicode_or_tabs() -> None:
    place = NetPath("scope.café\tinput")
    transition = NetPath("scope.run")
    net = Net([Place(place, "line one\r\nline two")], [Transition(transition)], [Arc(place, transition)])

    source = to_dot(net)

    assert ">café\tinput</FONT>" in source
    assert 'line one<BR ALIGN="CENTER"/>line two</FONT>' in source
    assert "\\t" not in source


def test_to_dot_marks_sources_and_keeps_anonymous_declarations_in_tooltips() -> None:
    source_transition = NetPath("ingress.open")
    target = NetPath("ingress.opened")
    net = Net(
        [Place(target)],
        [Transition(source_transition, handler=AnonymousDeclaration("project_open"))],
        [Arc(source_transition, target)],
    )

    dot = to_dot(net)

    assert ">source · handler: project_open</FONT>" in dot
    assert ">anonymous<" not in dot
    assert 'penwidth="2"' in dot
    assert 'style="rounded,filled,dashed"' in dot
    assert 'tooltip="ingress.open\\nsource transition\\nhandler: project_open (anonymous declaration)"' in dot


def test_to_dot_rejects_nul_graphviz_text() -> None:
    net = Net([Place(NetPath("bad\0place"))], [], [])

    with pytest.raises(ValueError, match="Graphviz text cannot contain a NUL character"):
        to_dot(net)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"theme": "sepia"}, "theme must be 'dark' or 'light'"),
        ({"direction": "TB"}, "direction must be 'top-down' or 'left-right'"),
    ],
)
def test_to_dot_rejects_unknown_presentation_arguments(arguments: dict[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        to_dot(_golden_net(), **arguments)


def test_to_dot_requires_canonical_net() -> None:
    with pytest.raises(TypeError, match="canonical Net"):
        to_dot(object())  # type: ignore[arg-type]


def test_render_writes_dot_without_invoking_graphviz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "net.dot"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("Graphviz was invoked"))

    result = render(_golden_net(), target)

    assert result == target
    assert target.read_text() == to_dot(_golden_net())


def test_render_rejects_unsupported_suffix(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"unsupported Graphviz output suffix '\.jpg'.*\.dot, \.svg, \.png, or \.pdf"):
        render(_golden_net(), tmp_path / "net.jpg")


def test_render_reports_missing_graphviz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("petrus.impetus.petrinet.dot.shutil.which", lambda executable: None)

    with pytest.raises(RuntimeError, match="Graphviz 'dot' executable was not found"):
        render(_golden_net(), tmp_path / "net.svg")


def test_render_reports_graphviz_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("petrus.impetus.petrinet.dot.shutil.which", lambda executable: "/usr/bin/dot")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stderr="syntax exploded\n"),
    )

    with pytest.raises(RuntimeError, match="Graphviz 'dot' failed.*syntax exploded"):
        render(_golden_net(), tmp_path / "net.pdf")


@pytest.mark.parametrize(("suffix", "format_name"), [(".svg", "svg"), (".png", "png"), (".pdf", "pdf")])
def test_render_infers_each_graphviz_output_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, format_name: str
) -> None:
    target = tmp_path / f"net{suffix}"
    calls = []
    monkeypatch.setattr("petrus.impetus.petrinet.dot.shutil.which", lambda executable: "/usr/bin/dot")

    def succeed(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 0, stderr="")

    monkeypatch.setattr(subprocess, "run", succeed)

    assert render(_golden_net(), target) == target
    assert calls == [
        (
            ["/usr/bin/dot", f"-T{format_name}", "-o", str(target)],
            {
                "input": to_dot(_golden_net()),
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "check": False,
            },
        )
    ]


def test_render_reports_graphviz_start_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("petrus.impetus.petrinet.dot.shutil.which", lambda executable: "/usr/bin/dot")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("denied")))

    with pytest.raises(RuntimeError, match="Graphviz 'dot' could not be started: denied"):
        render(_golden_net(), tmp_path / "net.png")


@pytest.mark.parametrize(
    ("theme", "background", "cluster", "primary", "secondary", "place"),
    [
        ("dark", "#0d1117", "#161b22", "#e6edf3", "#8b949e", "#58a6ff"),
        ("light", "#ffffff", "#f6f8fa", "#1f2328", "#59636e", "#0969da"),
    ],
)
def test_render_produces_real_svg_with_theme_palette(
    tmp_path: Path,
    theme: str,
    background: str,
    cluster: str,
    primary: str,
    secondary: str,
    place: str,
) -> None:
    target = render(_golden_net(), tmp_path / f"net-{theme}.svg", theme=theme)

    svg = target.read_text()
    assert "<svg" in svg
    assert f'fill="{background}"' in svg
    assert f'stroke="{place}"' in svg
    root = ElementTree.parse(target).getroot()
    cluster_group = next(element for element in root.iter() if element.attrib.get("class") == "cluster")
    cluster_polygon = next(element for element in cluster_group.iter() if element.tag.endswith("polygon"))
    assert cluster_polygon.attrib["fill"] == cluster
    text = [element for element in root.iter() if element.tag.endswith("text")]
    primary_name = next(element for element in text if element.text == "input")
    secondary_metadata = next(
        element for element in text if element.text == "Work" and element.attrib["font-size"] == "9.00"
    )
    assert primary_name.attrib["font-weight"] == "bold"
    assert primary_name.attrib["font-size"] == "14.00"
    assert primary_name.attrib["fill"] == primary
    assert "font-weight" not in secondary_metadata.attrib
    assert secondary_metadata.attrib["font-size"] == "9.00"
    assert secondary_metadata.attrib["fill"] == secondary
