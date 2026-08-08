"""Deterministic Graphviz presentation of a canonical Petri-net ``Net``."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping
from html import escape
from pathlib import Path
from typing import Literal

from petrus.impetus.petrinet.marking import Marking
from petrus.impetus.petrinet.schema import (
    AnonymousDeclaration,
    Arc,
    Cel,
    Delay,
    Net,
    NetPath,
    Place,
    Transition,
    Until,
)

type _Theme = Literal["dark", "light"]
type _Direction = Literal["top-down", "left-right"]
type _Node = tuple[NetPath, str, Place | Transition]

_PALETTES = {
    "dark": {
        "canvas": "#0d1117",
        "cluster": "#161b22",
        "primary": "#e6edf3",
        "secondary": "#8b949e",
        "place": "#58a6ff",
        "transition": "#d29922",
        "consume": "#8b949e",
        "read": "#58a6ff",
        "inhibit": "#f85149",
        "marked": "#1f6feb",
    },
    "light": {
        "canvas": "#ffffff",
        "cluster": "#f6f8fa",
        "primary": "#1f2328",
        "secondary": "#59636e",
        "place": "#0969da",
        "transition": "#9a6700",
        "consume": "#57606a",
        "read": "#0969da",
        "inhibit": "#cf222e",
        "marked": "#ddf4ff",
    },
}
_RANKDIRECTIONS = {"top-down": "TB", "left-right": "LR"}
_OUTPUT_FORMATS = {".svg": "svg", ".png": "png", ".pdf": "pdf"}


def _text(value: object) -> str:
    text = str(value)
    if "\0" in text:
        raise ValueError("Graphviz text cannot contain a NUL character")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _quote(value: object) -> str:
    escaped = _text(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _attributes(values: Mapping[str, object]) -> str:
    return ", ".join(f"{name}={_quote(value)}" for name, value in values.items())


def _rich_label(primary: object, secondary: str, palette: dict[str, str]) -> str:
    primary_text = escape(_text(primary), quote=True).replace("\n", '<BR ALIGN="CENTER"/>')
    secondary_text = escape(_text(secondary), quote=True).replace("\n", '<BR ALIGN="CENTER"/>')
    rows = f'<TR><TD><B><FONT COLOR="{palette["primary"]}" POINT-SIZE="14">{primary_text}</FONT></B></TD></TR>'
    if secondary_text:
        rows += f'<TR><TD><FONT COLOR="{palette["secondary"]}" POINT-SIZE="9">{secondary_text}</FONT></TD></TR>'
    return f'<<TABLE BORDER="0" CELLBORDER="0" CELLPADDING="1">{rows}</TABLE>>'


def _node_attributes(before: Mapping[str, object], label: str, after: Mapping[str, object]) -> str:
    return f"{_attributes(before)}, label={label}, {_attributes(after)}"


def _declaration(value: object) -> str:
    if isinstance(value, Cel):
        return f"cel: {value.expression}"
    if isinstance(value, AnonymousDeclaration):
        return value.display_name or "anonymous declaration"
    return str(value)


def _declaration_tooltip(value: object) -> str:
    declaration = _declaration(value)
    if isinstance(value, AnonymousDeclaration) and value.display_name is not None:
        return f"{declaration} (anonymous declaration)"
    return declaration


def _timer(timer: Delay | Until) -> str:
    if isinstance(timer, Delay):
        return f"delay: {timer.duration}"
    return f"until: {timer.instant}"


def _transition_details(transition: Transition, is_source: bool) -> tuple[str, str]:
    concise: list[str] = []
    tooltip = [str(transition.path)]
    if is_source:
        concise.append("source")
        tooltip.append("source transition")
    if transition.handler is not None:
        handler = _declaration(transition.handler)
        concise.append(
            "handler"
            if isinstance(transition.handler, AnonymousDeclaration) and transition.handler.display_name is None
            else f"handler: {handler}"
        )
        tooltip.append(f"handler: {_declaration_tooltip(transition.handler)}")
    if transition.guards:
        guards = [_declaration(guard) for guard in transition.guards]
        if len(guards) == 1:
            guard = transition.guards[0]
            concise.append(
                "guard"
                if isinstance(guard, AnonymousDeclaration) and guard.display_name is None
                else f"guard: {guards[0]}"
            )
        else:
            concise.append(f"{len(guards)} guards")
        tooltip.append(f"guards: {'; '.join(_declaration_tooltip(guard) for guard in transition.guards)}")
    if transition.timers:
        timers = [_timer(timer) for timer in transition.timers]
        concise.append(timers[0] if len(timers) == 1 else f"{len(timers)} timers")
        tooltip.append(f"timers: {'; '.join(timers)}")
    return " · ".join(concise), "\n".join(tooltip)


def _place_line(identifier: str, place: Place, count: int, palette: dict[str, str], indent: str) -> str:
    secondary = []
    if place.color is not None:
        secondary.append(place.color)
    if count:
        secondary.append(f"{count} {'token' if count == 1 else 'tokens'}")
    before = {
        "color": palette["place"],
        "fillcolor": palette["marked"] if count else palette["canvas"],
    }
    after = {
        "shape": "ellipse",
        "style": "filled",
        "tooltip": str(place.path),
    }
    label = _rich_label(place.path[-1], " · ".join(secondary), palette)
    return f"{indent}{_quote(identifier)} [{_node_attributes(before, label, after)}];"


def _transition_line(
    identifier: str, transition: Transition, is_source: bool, palette: dict[str, str], indent: str
) -> str:
    secondary, tooltip = _transition_details(transition, is_source)
    before = {
        "color": palette["transition"],
        "fillcolor": palette["cluster"],
    }
    after = {
        **({"penwidth": 2} if is_source else {}),
        "shape": "box",
        "style": "rounded,filled,dashed" if is_source else "rounded,filled",
        "tooltip": tooltip,
    }
    label = _rich_label(transition.path[-1], secondary, palette)
    return f"{indent}{_quote(identifier)} [{_node_attributes(before, label, after)}];"


def _node_line(
    node: _Node,
    counts: dict[NetPath, int],
    source_transitions: set[NetPath],
    palette: dict[str, str],
    indent: str,
) -> str:
    path, identifier, value = node
    if isinstance(value, Place):
        return _place_line(identifier, value, counts.get(path, 0), palette, indent)
    return _transition_line(identifier, value, path in source_transitions, palette, indent)


def _node_lines(
    nodes: list[_Node],
    counts: dict[NetPath, int],
    source_transitions: set[NetPath],
    palette: dict[str, str],
    group_scopes: bool,
) -> list[str]:
    scoped: dict[str, list[_Node]] = {}
    unscoped = []
    for node in nodes:
        path = node[0]
        if group_scopes and len(path) > 1:
            scoped.setdefault(path[0], []).append(node)
        else:
            unscoped.append(node)
    lines = [_node_line(node, counts, source_transitions, palette, "  ") for node in unscoped]
    for position, (scope, members) in enumerate(scoped.items()):
        lines.append(f'  subgraph "cluster_{position}" {{')
        cluster_attributes = {
            "color": palette["secondary"],
            "fillcolor": palette["cluster"],
            "fontcolor": palette["secondary"],
            "label": scope,
            "style": "filled",
            "tooltip": scope,
        }
        lines.append(f"    graph [{_attributes(cluster_attributes)}];")
        lines.extend(_node_line(node, counts, source_transitions, palette, "    ") for node in members)
        lines.append("  }")
    return lines


def _arc_line(arc: Arc, source: str, target: str, palette: dict[str, str]) -> str:
    label = []
    if arc.is_read:
        semantic = "read"
    elif arc.is_inhibit:
        semantic = "inhibit"
    else:
        semantic = "consume"
    if not arc.is_consume:
        label.append(semantic)
    if arc.weight != 1:
        label.append(f"{arc.weight}×")
    if arc.color is not None:
        label.append(arc.color)
    if arc.filter is not None:
        label.append(f"filter: {_declaration(arc.filter)}")
    attributes: dict[str, object] = {
        "arrowhead": "odot" if arc.is_inhibit else "normal",
        "color": palette[semantic],
    }
    if label:
        attributes["label"] = " · ".join(label)
    attributes["style"] = "solid" if arc.is_consume else "dashed"
    attributes["tooltip"] = f"{arc.source} -> {arc.target}"
    return f"  {_quote(source)} -> {_quote(target)} [{_attributes(attributes)}];"


def _presentation(theme: str, direction: str) -> tuple[dict[str, str], str]:
    if theme not in _PALETTES:
        raise ValueError(f"theme must be 'dark' or 'light', got {theme!r}")
    if direction not in _RANKDIRECTIONS:
        raise ValueError(f"direction must be 'top-down' or 'left-right', got {direction!r}")
    return _PALETTES[theme], _RANKDIRECTIONS[direction]


def to_dot(
    net: Net,
    marking: Marking | None = None,
    *,
    theme: _Theme = "dark",
    direction: _Direction = "top-down",
    group_scopes: bool = True,
) -> str:
    """Return deterministic Graphviz DOT source for one canonical ``Net``."""
    if not isinstance(net, Net):
        raise TypeError(f"to_dot requires a canonical Net (use built.net for a BuiltNet), got {net!r}")
    if marking is not None and not isinstance(marking, Marking):
        raise TypeError(f"marking must be a Marking or None, got {marking!r}")
    palette, rankdir = _presentation(theme, direction)
    counts = marking.counts() if marking is not None else {}
    places = [(path, f"p{position}", place) for position, (path, place) in enumerate(net.places.items())]
    transitions = [
        (path, f"t{position}", transition) for position, (path, transition) in enumerate(net.transitions.items())
    ]
    nodes: list[_Node] = [*places, *transitions]
    identifiers = {path: identifier for path, identifier, _ in nodes}
    source_transitions = {path for path in net.transitions if net.is_source(path)}

    graph_attributes: dict[str, object] = {
        "bgcolor": palette["canvas"],
        "fontcolor": palette["primary"],
        "fontname": "Helvetica",
    }
    if net.name is not None:
        graph_attributes["label"] = net.name
        graph_attributes["labelloc"] = "t"
    graph_attributes["nodesep"] = "0.6"
    graph_attributes["pad"] = "0.25"
    graph_attributes["rankdir"] = rankdir
    graph_attributes["ranksep"] = "1.0"
    lines = [
        'digraph "impetus" {',
        f"  graph [{_attributes(graph_attributes)}];",
        f'  node [fontcolor={_quote(palette["primary"])}, fontname="Helvetica"];',
        f'  edge [fontcolor={_quote(palette["secondary"])}, fontname="Helvetica", fontsize="10"];',
    ]

    lines.extend(_node_lines(nodes, counts, source_transitions, palette, group_scopes))
    for arc in net.arcs:
        lines.append(_arc_line(arc, identifiers[arc.source], identifiers[arc.target], palette))
    lines.append("}")
    return "\n".join(lines) + "\n"


def render(
    net: Net,
    target: Path | str,
    marking: Marking | None = None,
    *,
    theme: _Theme = "dark",
    direction: _Direction = "top-down",
    group_scopes: bool = True,
) -> Path:
    """Write DOT directly or render SVG, PNG, or PDF through local Graphviz."""
    path = Path(target)
    suffix = path.suffix.lower()
    if suffix not in {".dot", *_OUTPUT_FORMATS}:
        raise ValueError(f"unsupported Graphviz output suffix {path.suffix!r}; expected .dot, .svg, .png, or .pdf")
    source = to_dot(net, marking, theme=theme, direction=direction, group_scopes=group_scopes)
    if suffix == ".dot":
        path.write_text(source, encoding="utf-8", newline="")
        return path

    executable = shutil.which("dot")
    if executable is None:
        raise RuntimeError("Graphviz 'dot' executable was not found; install Graphviz or render to a .dot file")
    try:
        result = subprocess.run(
            [executable, f"-T{_OUTPUT_FORMATS[suffix]}", "-o", str(path)],
            input=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as error:
        raise RuntimeError(f"Graphviz 'dot' could not be started: {error}") from error
    if result.returncode:
        diagnostic = result.stderr.strip() or "no diagnostic output"
        raise RuntimeError(f"Graphviz 'dot' failed with exit code {result.returncode}: {diagnostic}")
    return path


__all__ = ["render", "to_dot"]
