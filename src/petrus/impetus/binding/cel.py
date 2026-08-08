"""
The CEL adapter: compiles inline ``Cel`` expressions into pure callables.

Backed by ``cel-python`` (``celpy``), the kernel's one runtime dependency. The
binding layer compiles declared expressions at instance construction — a
syntactically invalid expression is a declared mismatch: it fails fast and
never evaluates. The compiled filter sees the token's data fields as bare
variables (``amount >= 100``); color matching stays outside CEL, on the arc's
inscription. A token whose data is not a mapping has no fields to expose, so
evaluation raises — which enabledness reads as not admitted and surfaces as a
diagnostic, exactly like any other per-token evaluation error.

The compiled completion condition sees each place as a bare variable bound to
the place's FIFO queue, each token a ``{color, data}`` map — the marking is
colored tokens at places, and the expression reads exactly that (Navigator
ruling). A free variable naming no place is a second declared mismatch, caught
at compile by ``free_variables``; the runtime owns the not-holding-plus-
diagnostic reading of concrete evaluation errors.

The compiled guard sees the same place-as-variable, ``{color, data}`` shape
scoped down to the firing binding: each of the declaring transition's
consume/read input places binds to the binding's selected tokens from that
place — a guard reads the binding, never the wider marking, so those places
are the whole scope and any other free variable is a declared mismatch
(Navigator ruling). Enabledness owns the not-satisfied-plus-diagnostic reading
of concrete evaluation errors.

The three environments deliberately differ today — bare data fields for a
filter, place-keyed token structs for guards and completion — each ruled in
its own slice, never designed together. Whether the tier should have one
unified data-exposure design is an open design question; carried debt
(docs/project/debt/items/
2026-07-09T2200Z-cel-data-exposure-has-no-unified-design.md).
"""

from __future__ import annotations

# Python imports
from collections.abc import Callable, Iterable, Mapping

# Pip imports
import celpy

# Internal imports
from petrus.impetus.petrinet import Binding, Cel, Filter, Guard, Marking, NetPath, Token

type Completion = Callable[[Marking], bool]

# CEL macros bind their first argument as a local variable within their second.
MACROS = frozenset({"exists", "all", "exists_one", "map", "filter"})


def compile_filter(declaration: Cel) -> Filter:
    """
    Compile an inline ``Cel`` declaration into a pure single-token filter.

    Raises ``ValueError`` on a syntactically invalid expression. The returned
    filter lets per-token evaluation errors (an undeclared field, a type
    mismatch, non-mapping data) propagate; enabledness owns the
    not-admitted-plus-diagnostic reading.
    """
    environment, tree = _parsed(declaration, "filter")
    program = environment.program(tree)

    def evaluate(token: Token) -> bool:
        if not isinstance(token.data, Mapping):
            raise TypeError(f"CEL filters read data fields; token data is {type(token.data).__name__}, not a mapping")
        return bool(program.evaluate({name: celpy.json_to_cel(value) for name, value in token.data.items()}))

    return evaluate


def compile_completion(declaration: Cel, places: Iterable[NetPath]) -> Completion:
    """
    Compile an inline ``Cel`` declaration into a pure marking predicate.

    The expression sees each declared place as a bare variable bound to the
    place's queue as a list of ``{color, data}`` maps (a black token is
    ``{color: null, data: null}``; a place the sparse marking omits binds to
    the empty list, so emptiness is expressible). Raises ``ValueError`` on a
    syntactically invalid expression or a free variable naming no place —
    both declared mismatches that fail fast and never evaluate. The returned
    predicate lets evaluation errors on a concrete marking propagate; the
    runtime owns the not-holding-plus-diagnostic reading.
    """
    environment, tree = _parsed(declaration, "completion")
    queues = {str(path): path for path in places}
    unknown = free_variables(tree) - queues.keys()
    if unknown:
        raise ValueError(f"CEL completion {declaration.expression!r} references unknown place(s): {sorted(unknown)}")
    program = environment.program(tree)

    def evaluate(marking: Marking) -> bool:
        activation = {name: celpy.json_to_cel(_structs(marking.place(path))) for name, path in queues.items()}
        return bool(program.evaluate(activation))

    return evaluate


def compile_guard(declaration: Cel, transition: NetPath, places: Iterable[NetPath]) -> Guard:
    """
    Compile an inline ``Cel`` declaration into a pure guard over a binding.

    ``places`` is the declaring ``transition``'s consume/read input places —
    the expression's whole scope: a guard reads the binding, never the wider
    marking, and an inhibit arc's satisfaction contributes no tokens a guard
    could read (Navigator ruling); the transition itself is address-only, for
    the rejection message. The expression sees each place as a bare variable
    bound to the binding's selected tokens from that place — consumed
    selections first, read after, the ``Binding.peeked`` ordering — each token
    a ``{color, data}`` map (a black token is nulls). Raises ``ValueError`` on
    a syntactically invalid expression or a free variable outside the scope —
    both declared mismatches that fail fast and never evaluate. The returned
    guard lets evaluation errors on a concrete binding propagate; enabledness
    owns the not-satisfied-plus-diagnostic reading.
    """
    environment, tree = _parsed(declaration, "guard")
    unknown = free_variables(tree) - {str(path) for path in places}
    if unknown:
        raise ValueError(
            f"CEL guard {declaration.expression!r} on transition {transition} references name(s) outside "
            f"its consume/read input places {sorted(str(path) for path in places)}: {sorted(unknown)}"
        )
    program = environment.program(tree)

    def evaluate(binding: Binding) -> bool:
        selections: dict[str, list[dict]] = {}
        for place, tokens in binding.consumed + binding.read:
            selections.setdefault(str(place), []).extend(_structs(tokens))
        return bool(program.evaluate({name: celpy.json_to_cel(structs) for name, structs in selections.items()}))

    return evaluate


def _parsed(declaration: Cel, kind: str) -> tuple[celpy.Environment, celpy.Expression]:
    """Parse ``declaration``, or raise the declared-mismatch ``ValueError`` naming which ``kind`` of slot it is."""
    environment = celpy.Environment()
    try:
        return environment, environment.compile(declaration.expression)
    except celpy.CELParseError as error:
        raise ValueError(f"invalid CEL {kind} {declaration.expression!r}: {error}") from error


def _structs(tokens: Iterable[Token]) -> list[dict]:
    """Tokens in the expressions' ``{color, data}`` map encoding (a black token is nulls)."""
    return [{"color": token.color, "data": token.data} for token in tokens]


def free_variables(tree) -> set[str]:
    """
    The free variable names of a compiled CEL expression: identifiers in
    variable position (``ident`` nodes), minus names a macro binds — function
    names (``size(...)``) sit in call position and never appear as ``ident``.
    The subtraction is global rather than scope-precise, so a macro variable
    shadowing a real place name is permissively skipped, never falsely
    rejected — which also lets a macro variable shadowing an OUT-of-scope name
    escape construction-time scope checks and surface at evaluation instead;
    carried debt (docs/project/debt/items/
    2026-07-09T2100Z-macro-shadowed-scope-references-escape-construction-checks.md).
    ``tree`` is what ``celpy`` compiles to — a lark tree, kept
    duck-typed because lark is an undeclared transitive dependency.
    """
    idents = {str(node.children[0]) for node in tree.find_data("ident")}
    bound = set()
    for node in tree.find_data("member_dot_arg"):
        # children: (receiver, method-name token, argument exprlist) — lark
        # tokens are str subclasses, trees are not.
        method = next((child for child in node.children if isinstance(child, str)), None)
        arguments = next(
            (child for child in node.children if not isinstance(child, str) and child.data == "exprlist"), None
        )
        if method in MACROS and arguments is not None and arguments.children:
            variable = next(arguments.children[0].find_data("ident"), None)
            if variable is not None:
                bound.add(str(variable.children[0]))
    return idents - bound
