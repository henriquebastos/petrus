# Engineering Conventions

High-level code conventions for Petrus, distilled from review. Impetus remains
the semantic component named by conventions about Petri-net infrastructure. Each is mined
from a concrete diff where the first implementation diverged from the bar, the
same way we read patterns from changes in the current source tree. This is a living document:
add a convention when a review keeps surfacing the same class of finding;
promote one to an enforced `rules/*.yml` ast-grep rule when it's structural.

The baseline is the quality bar itself — design purity, immutability where
possible but pythonic, simple API, simple to test, YAGNI, naming/concept
integrity. The conventions below are the sharpened, situation-specific edges.

## Scope and authority

This file is the binding home for **reusable implementation practice**. It is
not a second decision corpus or a review transcript with accidental authority.
Classify durable knowledge by what it is:

- product, semantic, or architectural choices with alternatives and
  consequences belong in `docs/project/decisions/records/`;
- accepted structural compromises and their revisit triggers belong in
  `docs/project/debt/items/`;
- the account of what a particular change or review found belongs in its story,
  exploration, or worklog artifact;
- a practice likely to recur across changes belongs here.

A concrete review remains valuable provenance, but one finding does not become
a general rule merely because it appeared in a review. Distill the reusable
practice and leave case-specific history in the artifact that owns the change.
An entry explicitly marked provisional is evidence, not binding convention,
until the Navigator ratifies it.

More-specific ratified specs, decisions, and roadmap constraints override a
generic convention. Surface the conflict in the Plan or Review Checkpoint; do
not silently choose whichever text is more convenient.

## How to use and update this file

Start with the topic map and operational defaults below, then read the numbered
cases relevant to the surface being changed. The numbered cases retain the
reason, failure mode, and review provenance behind the concise rule.

When a review reveals a practice worth retaining:

1. state it in imperative, domain language and name the boundary it governs;
2. record architectural choice or accepted debt in its proper home first;
3. add the smallest reusable rule here, with the concrete review as provenance;
4. promote mechanically checkable structure to `rules/*.yml` rather than
   relying on prose alone.

Do not add framework-specific ceremony before Impetus owns that framework or
surface. A future CLI, telemetry API, database adapter, or worker system earns
its detailed conventions when implementation and review provide evidence.

## Topic map

The cases overlap deliberately; the same failure may illuminate more than one
engineering concern. Numbers refer to the review-derived cases below.

| Concern | Primary conventions |
| --- | --- |
| Domain vocabulary, ownership, and public API | 2, 4–7, 16, 20, 23, 29, 31, 35, 37, 40, 43, 52, 61–62, 67, 69, 72, 79–80, 88–89 |
| Boundary validation, normalization, and diagnostics | 1, 3, 10, 13, 17, 19, 24, 28, 30, 32, 36, 39, 42, 47, 51, 65–66, 75–78 |
| History, durability, transactions, and replay | 28, 33–34, 38, 41, 44–49, 53, 63–73, 86 |
| Scheduling, handlers, activities, and adapters | 32–42, 50–53, 58–60, 62, 67, 69, 72–80, 88 |
| Tests, fakes, fixtures, and evidence claims | 8, 11, 18, 21–22, 25–26, 54–59, 64, 74, 77, 81–82, 84–85 |
| Documentation, decisions, deferrals, and debt | 9, 12, 14–15, 20, 27, 35, 40, 43, 46, 60 |

## Operational defaults

These defaults make the case law usable during ordinary Python work. A more
specific numbered convention wins where one applies.

### Boundaries and code shape

- Keep CLIs, scripts, servers, workers, and transport integrations as thin
  adapters over importable operations. The kernel remains independent of
  presentation, transport, persistence encoding, and compatibility shapes.
- Put translation at the adapter, projection, or persistence boundary that
  owns it. Pass explicit domain values across seams rather than broad request
  objects or ambient context.
- Use a function when an operation has a narrow interface and little state. Use
  an object when binding state and behavior makes the interface materially
  smaller or enforces an invariant. Do not create a class merely to namespace
  one function or a dataclass merely to carry one local handoff.
- Name stable domain concepts and ruled seam carriers. Keep incidental local
  plumbing in simple built-in collections when that remains clear.
- Prefer direct attribute access for a known contract. Reflection and
  `getattr(...)` belong at genuinely dynamic or compatibility boundaries, not
  in defensive code that would hide a closed-union omission.
- Validate semantic invariants once, at the door that owns them and before any
  irreversible fact is recorded. Do not duplicate an already precise local
  Python failure or wrap it without adding boundary context. Contextualize an
  error when crossing a seam would otherwise lose the declaration, identity,
  or operation that failed.

### Scripts and command-line surfaces

- Parse and canonicalize syntax, scalar shape, paths, and operator intent at
  the outer boundary; canonicalize reusable domain input before side effects so
  direct callers receive the same semantics.
- Keep parsing, operation construction, serialization, and rendering separable
  when that makes the surface testable. Inner operations return values or
  structured reports; only the outermost adapter prints, writes, or exits.
- Never silently ignore, neutralize, or overwrite an operator-provided option.
  Reject incompatible options before starting work.

### Tests and evidence

- Production functions should ordinarily have cyclomatic complexity at most
  10. Values from 11–15 require review. Values above 15 require refactoring or
  a narrow, documented exception for a cohesive algorithm such as a parser,
  state machine, or lifecycle fold. Ruff `C901` enforces the default. A
  behavioral edit to an exempt function requires remeasurement and renewed
  review; the existing suppression is not approval for further growth.
- Test the public behavior and the reason it matters, not incidental helper
  decomposition. A pure semantic unit still earns a direct test when that test
  can name a failure more precisely than pipeline coverage.
- Keep one-off setup inline. Extract a fixture, builder, or helper when it names
  a domain scenario or removes meaningful repetition, not merely to shorten a
  test.
- Patch at the seam the unit owns. Prefer strict, small callable fakes whose
  unknown inputs fail loud; a stand-in must not improvise plausible answers.
- Use partial shape assertions only for fields that are genuinely dynamic and
  irrelevant to the behavior. When a record or report shape is the contract,
  assert it whole — including ordering, exact multiplicity, payload, and
  correlation where applicable.
- An architectural improvement is not a throughput claim. Performance claims
  require a named, bounded workload, concurrency and environment, timing and
  memory evidence, failures, and relevant ordering/cache caveats.

## From slice 1 review (`6ea23cf` → `856e15f`)

1. **Fail loud on surface you can't honor yet.** Ratified spec vocabulary stays
   in the schema, but the kernel refuses — `raise NotImplementedError` at
   construction — anything it can't yet execute (a non-consume arc, a
   handler/guard symbol). Never silently mis-execute: a `READ` arc that
   silently consumes is a data-loss bug. The kernel's fail-loud policy mirrors
   the test harness's.

2. **Enforce immutability, don't just assert it.** If a docstring says
   "immutable", make it structurally true — `MappingProxyType` views, frozen
   dataclasses, tuple queues. A prose promise over a public mutable dict rots.

3. **A value object rejects precondition violations.** A public operation that
   cannot satisfy its contract raises (`Marking.consume` on a short queue)
   rather than under-delivering silently, even when today's callers all satisfy
   the precondition.

4. **One concept — one name, one home.** A concept lives in the module named for
   it (`FiringOccurrence` belongs in `petrus.impetus.instance`, not authority), and the same
   ubiquitous-language term is spelled identically across layers (`candidates()`
   as both the pure function and the instance method). No synonym pairs for one
   idea.

5. **Don't leak oracle/fixture vocabulary into the kernel.** Names come from the
   `docs/project/glossary/` ubiquitous language, not the trace format (`TokensInitialized`,
   not `TokensSeeded` from the fixtures' `seedMarking`). The harness owns the
   oracle dialect; the kernel owns the spec's.

6. **Curate the public surface at its defining ownership module.** Public
   concepts are imported from the module that owns them. Project and component
   roots do not become compatibility or concept facades; `__all__` curates an
   ownership module without flattening the hierarchy.

7. **Constructors accept one canonical form.** Reject invalid/empty input; add
   alternative spellings only when a real caller needs them (`NetPath` takes a
   dotted string or a `NetPath`, and rejects the empty address).

8. **Tests encode intent, not just presence.** Assert record *ordering* (replay
   correctness depends on consume preceding produce), integration paths
   (fan-out through `fire()`/`step()`, not only the `passthrough()` unit), and
   loud failure on corruption (`replay_marking` rejects a diverging consume). A
   test that can't fail when the contract changes is missing.

9. **Annotate deliberately deferred surface where it lives.** Inert placeholders
   (`Status.COMPLETED`/`STUCK`) carry a co-located deferral comment, so a reader
   sees intent rather than forgotten code — distinct from dangerous unimplemented
   surface, which is guarded by convention 1.

## From slice 2 review (`959ee5e` → `bfcedfe`)

10. **The slice that widens a surface owns its new guards.** Admitting new
    vocabulary admits shapes the kernel cannot honor, and they must be rejected in
    the same slice, at construction — not left for later. Slice 2 opened read/
    inhibit modes and made weight semantically active, and shipped two silent
    defects: a non-source transition with only read/inhibit arcs livelocks (fires
    forever consuming nothing), and an unvalidated `weight < 1` mis-gates or
    livelocks. Fail-loud (convention 1) and value-object preconditions (convention
    3) apply to what a change newly makes *reachable* — including a field that was
    safe only while pinned — not only to what it explicitly implements.

11. **Assert every item the contract enumerates, not a sufficient subset.** The
    replay driver asserted `markingAfter` — which *implies* the produced token —
    but not `produced` itself, which the replay contract lists explicitly, so a
    broken `Firing.produced` would pass silently. Indirect coverage is not
    contract coverage: assert each listed item so a regression in any one fails.
    Equally, a prose coverage claim ("five fixtures drive replay") must be backed
    by the executable suite, never outrun it.

12. **Phrase a deferral by missing capability, not by version number.** "not
    supported in slice 1" misdescribes the code the moment slice 2 lands beside
    it; "awaits the handler slice" / "not yet" stays true. Deferral labels name
    the capability they wait on so they cannot silently go stale — convention 9
    with a shelf life.

## From slice 3 review (`0e779e7` → `f6cdce9`)

13. **Emit every field the ruling enumerates, not a sufficient subset.** The
    guard-error diagnostic carried symbol, transition, and error — but not the
    token, which the decision record lists explicitly, and which is the one
    field that distinguishes a typo'd guard from a healthy false. When a ruling
    enumerates a payload (diagnostic, record, message), ship each listed item;
    the field that feels omittable is usually the discriminating one.
    Convention 11's emit-side twin.

14. **A slice re-reads the prose it invalidates.** New semantics silently
    change what neighboring prose means: promoting "peeked" to the spec's term
    of art (everything a guard sees) left slice-2 comments using the same word
    for read-arc tokens only, and adding the warning channel left the module
    docstring's "no side effects" claim false — both in the very file the slice
    edited. Sweeping the surrounding docstrings/comments for statements the
    diff just made stale is part of the change, not cleanup: prose is invariant
    surface (conventions 2 and 12) and it rots at the diff that contradicts it,
    not later.

15. **Under-implementing a ratified contract is ledger debt, never drift.**
    The flat guard mapping knowingly under-implements ratified transition-local
    symbol scoping, but today's flat nets cannot observe the difference — so
    there is nothing to fail loud *on*. Fail-loud (convention 1) covers what
    would mis-execute; for a deliberate simplification that executes correctly
    within current reach, the explicit debt item (revisit trigger + closure
    condition, referenced from the code) is the loudness. The one forbidden
    option is resolving the gap silently, by implementation shape alone.

## From slice 4 review (`69e423b` → `bc48fcb`)

16. **A ruled default gets exactly one home.** The ruling "passthrough is a
    default *binding*" places the no-symbol→passthrough resolution at the
    binding layer — yet `fire()` also grew `handler=passthrough` as a parameter
    default. Behavior was uniform, so nothing misfired; the cost is conceptual:
    two sites now encode one decision, a future change must move both, and a
    reader cannot tell which is authoritative. When a decision record assigns a
    default (or any policy) to a layer, other layers take that value as a
    *required argument* — convenience defaults elsewhere are convention 4's
    "one concept, one home" violated in parameter position.

17. **Normalize at the boundary that admits spellings.** A contract that
    accepts equivalent spellings (`NetPath | str` destination keys) must
    resolve them to the canonical identity *before* any downstream artifact is
    built, or the spelling leaks into semantics: two keys naming one place
    yielded two `TokensProduced` records for one deposit-set, and the
    handler-owned sequences flowed unsnapshotted past the seam. Coalesce and
    copy once, at the entry point (`emitted[place] = ... + tuple(tokens)`);
    everything after speaks only canonical, kernel-owned values. Convention 2's
    boundary twin: immutability and identity are both established where foreign
    data enters, not re-derived by each consumer.

18. **New surface earns the tests its precedent already has.** The handler path
    reused `fire()`'s lifecycle yet its tests asserted membership where the
    passthrough precedent asserted full record ordering, skipped
    `firing.produced` — the very field the per-arc contract slice is about —
    and covered str-keys only by accident of one fixture's spelling. When a
    slice adds a parallel path (a new handler beside passthrough, a new mode
    beside consume), port the strongest existing assertions to it and name a
    test for each contract clause the new path adds; coverage by coincidence
    reads as coverage until the refactor that breaks it. Conventions 8 and 11
    applied at the moment of parallel-surface creation.

## From slice 5 review (`2430a11` → `04a29b8`)

19. **A new rejection audits its siblings at the same boundary.** The slice
    rejected `filter` on output arcs ("an ignored narrowing would silently
    mis-describe the deposit") while `mode` — sitting on the same
    transition→place branch, equally ignored-if-present, equally denied by the
    spec — stayed silently accepted. Writing a guard for one field proves the
    boundary was auditable; every sibling field with the same
    ignored-if-present character there is handled in the same pass, or the
    new guard's own rationale convicts the omission. Convention 10 pointed at
    the surface a change *illuminates*, not only the surface it adds.

20. **A slice that layers a concept re-scopes the names beneath it.** Making
    input admission a layered predicate (nominal color narrowed by filter,
    computed in `enabledness.admitted`) silently demoted `Arc.admits` from
    the whole truth to the color half — while its docstring kept claiming
    "whether this arc admits ``token``", contradicted by the very module that
    now uses "admits" for the full concept. When new semantics split one
    predicate into partial and full, the name left holding the partial must
    say which part it holds and point at the whole, in the same diff — else a
    future caller takes the part for the whole. Convention 14 for meanings:
    prose can rot without the diff ever touching its file.

21. **Precedent tests port to every sibling path and every new pure unit.**
    The slice created three selection paths (colored, named-filter, CEL) and
    gave only the first the precedent's full record-ordering + replay
    assertions; it created three pure module-level units (`selection`,
    `admitted`, `compile_filter`) and exercised them only through the
    `NetInstance` pipeline, against the suite's own standalone-`passthrough`
    precedent. Convention 18 counts per path and per layer, not per slice:
    each parallel sibling gets the flagship's assertions, and a pure unit
    earns a direct test beside its pipeline coverage — when integration
    coverage regresses it names the pipeline, not the function.

## From slice 6 review (`6231def` → `19fce34`)

22. **A defended looseness is a contract clause; its apology names its test.**
    `free_variables` carried a docstring paragraph justifying a deliberate
    imprecision — the macro subtraction is "global rather than scope-precise,
    … permissively skipped, never falsely rejected" — and no test at any level
    exercised a macro variable actually shadowing a place name. Three lenses
    converged on the same gap. Whenever prose *defends* a behavior (a
    conservative approximation, a permissive skip, an error≡false reading),
    that defense is the specification of the one test that must exist: the
    case the paragraph was written to excuse, pinned so the well-meaning
    refactor that "fixes" the imprecision fails a test instead of silently
    changing construction-time semantics. Convention 21 says a pure unit gets
    a direct test; this says which case that test must contain.

23. **Implementation-type aliases live at their evaluation site; a type-only
    back-edge is an accepted price.** Reviewers split on `Completion` homing
    in `runtime` (its evaluator) at the cost of a `TYPE_CHECKING` reverse
    import in `cel` (its producer). Navigator ruling: the evaluation site
    wins — `Filter`/`Guard` live in `enabledness`, `Handler` in `firing`,
    `Completion` in `runtime`, each beside the code that calls it, and a
    producer below borrows the name through a documented type-only edge
    (the `schema`↔`marking` precedent). What stays forbidden is a *runtime*
    upward import; what stays wrong is homing a concept by import
    convenience rather than by ownership. Don't re-litigate the edge when
    registrations/ingress add their own callable types.

## From slice 7 review (`6ca8e4b` → `1e868a0`)

24. **A rejection names its declaration and both sides of the mismatch.** The
    guard scope rejection said only "references place(s) outside its
    transition's consume/read inputs: ['elsewhere']" — while every sibling
    construction-time rejection carries its node (`Arc.__post_init__` appends
    `source -> target`, `Transition.__post_init__` its path, `Net` names the
    offending arc or transition), and the runtime call site had the
    transition path in hand and dropped it. Worse, the wording asserted the
    unknown name *is* a place, misdescribing a plain typo. A rejection
    message carries the address of the declaration it rejects, what was
    allowed, and what was found — and stays honest about what it cannot know
    (an unresolved name is a *name*, not a "place"). Convention 13's
    enumerate-every-field discipline applied to error prose.

25. **"Like its sibling" is a checkable claim.** The guard-resolution stanza
    said it resolves declarations "like filters" while being shaped
    differently: the filter block curates declared entries only, the guard
    block copied the whole user mapping and overlaid compiled expressions,
    recomputing per-declaration what the sibling hoists. Nothing misbehaved;
    the cost is a reader comparing two side-by-side stanzas that encode one
    idea two ways, with prose vouching for a parity that isn't there. A
    comment claiming parity makes the shapes one contract: build the stanza
    the sibling's way or drop the claim. Convention 4 at stanza scale, with
    convention 14's rule that the vouching prose rots first.

26. **A value-keyed mapping that collapses declaration sites states and pins
    its collapse invariant.** Keying compiled guards by the frozen `Cel`
    value merges equal expressions declared on different transitions into
    one entry, last compile wins — sound only because the compiled closure
    captures the expression alone and reads the binding by place name (scope
    is a compile-time check, not captured state). That invariant was
    load-bearing and unstated: a refactor making the closure scope-dependent,
    or deduplicating compilation per unique expression, would silently skip
    one site's validation or misapply another's scope. State the invariant
    at the mapping and pin both collapse edges: equal declarations on two
    sites both work, and per-site validation still rejects the site where
    the shared value is invalid. Convention 22 for identity: the defense
    here is not prose but a hash semantics.

27. **Closing a capability gap sweeps the ratified prose that excused it.**
    `net-schema.md` and `handler-contract.md` still described guards as
    symbols-only — reconcilable with reality while the kernel truly accepted
    only symbols, actively false the moment this slice landed the second
    encoding, and neither file was in the diff. Staleness dates from the
    decision record, but it *bites* at the capability: the slice that makes
    prose false owns the sweep, and the sweep extends beyond the files the
    diff touches to the ratified documents describing the old boundary.
    Conventions 14 and 20 widened from the edited file to the spec surface.

## From slice 8 review (`6f61f41` → `1f49b0a`)

28. **The seam where the outside world enters validates before it records.**
    `deliver()` rejected the empty delivery *before* appending the event fact
    ("a caller bug, not a fact worth recording") — then recorded and routed a
    `str` payload two statements later, because a str is a `Sequence` and no
    element was checked: the history asserted an external-event fact that
    never happened in that shape. The same method drew the line and crossed
    it. An append-only history takes only vetted facts — every rejection a
    boundary owes happens before its first append — and the ingress seam,
    where foreign data becomes kernel values, owes strictly more than the
    internal type-trusting boundaries (whose uniform posture is filed debt,
    not silently diverged from). Convention 17's normalize-at-the-boundary,
    sharpened by irreversibility: you cannot unrecord.

29. **Prose exclusivity is an invariant the value object enforces.** The
    `Binding` docstring said delivered tokens arrive "*instead*" of selections
    and `tokens` said "consumed ... **or** delivered" — while the code
    concatenated, and nothing rejected the consumed+delivered chimera a
    public constructor made expressible. When a docstring states an
    either/or, that is a structural claim: enforce it (`__post_init__`
    raising on the hybrid) or reword to honest concatenation — never prose
    saying "or" over code doing "and". Convention 2 widened from
    immutability to shape: promises about which combinations exist are made
    structurally true, not asserted.

30. **Sibling entry points to one surface discriminate misuse identically.**
    `deliver()` told apart the typo ("not a transition of this net"), the
    concept error ("it has input arcs"), and the lifecycle error ("sealed");
    its sibling door into the same registration surface, `seal()`, collapsed
    the first two into one membership test whose message misdescribed the
    typo as a non-source. The misuse classes are the surface's, not the
    method's: a second entry point ports the first's rejection granularity —
    convention 24 applied across the sibling set, with no prose parity claim
    (convention 25) needed to trigger it.

31. **A ruling's spelled call shape is enumerated surface — parameter names
    included.** The ratified fork answers wrote `deliver(source, ...)` and
    `seal(source)`; the implementation spelled both parameters `transition`,
    under-describing methods that accept only sources and raise on anything
    else. A public keyword-callable signature is part of what a ruling
    enumerates (convention 13 in parameter position), and independently: name
    a parameter by the contract it enforces, not the wider type it coerces.
    The rename was free at the slice with no external callers; it never is
    again.

## From slice 9 review (`d4e4ae5` → `3f6bfb2`)

32. **A guard enforces every conjunct its own rationale enumerates.** The
    timed-net clock check raised a declared ValueError naming a required
    *pair* — "pass the watermark and entry instants" — and checked only the
    watermark: a caller supplying the first without the second crashed two
    stanzas later on a raw IndexError in the anchor lookup, the undiagnostic
    failure the guard existed to prevent. When a fail-loud rejection's
    message (or docstring) names N requirements, each one is checked — at
    the guard when it is knowable there, at the use site (with the concrete
    shortfall named) when it is not. Conventions 11/13's
    assert-and-emit-every-item discipline, applied to validation inputs.

33. **A stateful instance's derived views speak only its recorded truth.**
    `NetInstance.candidates(at=10)` let a caller observe a binding matured
    at an instant no appended record proves time reached — a hypothetical
    "now" on the very object whose clock is *defined* as the instant of its
    latest append. Nothing could misfire, but the surface contradicted the
    model: the instance's projections (candidates, status, next_maturation)
    answer only for the watermark; "what if" evaluation belongs to the pure
    layer, which takes any clock explicitly. Internal prospection is fine —
    `step()` probes its effective instant and either commits it with the
    selection record or discards it — but it stays private, and its
    judgment becomes observable only through the append that justifies it.

34. **An identity between two mutations gets one commit point.** The module
    docstring vouched "the watermark is the instant of the latest appended
    record", but advance-then-append was a convention hand-rolled at four
    sites (step, deliver, seal, wake) — nothing structural stopped the next
    appending method from breaking the identity silently. When an invariant
    ties mutation A to mutation B, home the pair in one place (`_advance`,
    called exactly when a method commits to appending) and let every site
    say the intent, not re-implement it. Convention 4 for invariants:
    repetition is where identities rot, one home is where they hold.

35. **A uniform shape yields to a value invariant — deviate minimally and
    annotate in place.** Ruling 1 gave every record `instant` as a keyword
    field defaulting to 0; `TimerMatured` carries a cross-field invariant
    (observed ≥ maturation) that no honest default can satisfy — a default
    that exists only to raise serves no caller. Navigator ruling: the
    invariant wins, minimally — keep the half of the convention the
    invariant permits (keyword-ness, via `kw_only=True`), drop the half it
    forbids (the default), and say why in a docstring clause where the
    deviation lives (convention 9), so a future uniformity sweep doesn't
    "fix" it into a landmine. Conformance is to the reason for the shape,
    not the shape.

## From slice 10a review (`ca525fe` → `0ebe461`)

36. **Sibling doors reject each other's traffic.** When a surface has two
    entry points partitioned by concept — `deliver()` for source transitions,
    `begin()` for scheduled ones — each door owes the *mirror* of the other's
    concept rejection, not only its own parameter checks. `begin()` shipped
    three careful rejections (foreign, delivered, stale) and accepted the one
    binding that belongs to the other door: an empty hand-built binding for a
    source transition, which minted a `CandidateSelected` the spec
    categorically forbids and fired a source spontaneously. Two lenses found
    it independently; the skeptics could not refute it. Convention 30 makes
    sibling doors discriminate *identically*; this is its partition twin: the
    door boundary itself is the first misuse class a new door must enforce,
    because the sibling's guard (`deliver` rejecting non-sources) proves the
    partition was known.

37. **Name a judgment by its subject, in the ruling's vocabulary; the
    consequence's name belongs on the consequence.** The binding layer's
    purity judgment traveled as `observed: bool` — a name describing what
    happens to the result (it becomes an observed fact), attached to a
    parameter judging the handler, reading backwards at the call site
    (`_observed(transition)` — "is the transition observed?"). The ruling's
    own words were pure/impure; the parameter is now `impure`, the instance
    helper `_impure()`, and "observed" stays on `HandlerResultRecorded`,
    the consequence it truthfully describes. One judgment had three
    spellings across two modules — convention 4 for flags: when a decision
    crosses a seam as an argument, it carries one name, taken from the
    decision's own language.

38. **A producer that returns a whole assembled from the caller's part also
    returns the part it added.** `end_firing` returned `Firing.records` as
    `attempt.records + new_records`, and the committing site recovered what
    to append by `firing.records[len(attempt.records):]` — a cross-module
    prefix identity held by length arithmetic, breakable by any reorder
    inside the producer with no test naming the coupling. Two lenses flagged
    it. `complete_firing` now returns the end records it minted alongside
    the assembled outcome; the committer appends the return verbatim and
    re-derives nothing. Convention 34 for return values: the producer owns
    the split it created — a caller subtracting one return from another to
    reconstruct it is the identity rotting in arithmetic.

## From slice 10b review (`8d9a446` → `7907ae3`)

39. **A ruled surface's rejections share one home and discriminate
    categorical-first.** The ruling's six registration-effect validity rules
    landed in two layers, because one — effects require an impure handler —
    was knowable in the pure half, where the incoherent record set would have
    been minted. The split cost precedence: the instance's checks ran first,
    so a pure firing carrying an *unarmed* close was told "not armed" (the
    downstream symptom) instead of "effects require an impure handler" (the
    category that forbids the whole question). When a ruling enumerates the
    validity rules of one surface, they live in one validation home at the
    committing seam, ordered most-categorical-first; a lower layer that could
    check one rule locally trusts the seam for it exactly as it trusts the
    rules it cannot check. Knowability is not a homing reason — conventions
    4/16 in validation position, with convention 30's discrimination
    sharpened into an ordering rule.

40. **A family member's rename is family-wide or deferred, never
    piecemeal.** Convention 31 renames a parameter to the contract it
    enforces while the rename is free — and by it, `RegistrationOpened`/
    `RegistrationClosed` should spell their node `source`, as their sibling
    value object and the ruled `deliver(source)`/`seal(source)` signatures
    already do. But the field sits in a record family whose every member —
    including the equally source-only `ExternalEventRecorded` — spells its
    node `transition`; renaming only the pair in reach would split one
    family vocabulary into two spellings, a worse state than the uniform
    imprecision. When the more-precise name would fork a deliberately
    uniform family whose public schema is one deferred decision, keep the
    family's spelling and write the rename down where the deferral lives, so
    the schema moment decides it family-wide. Convention 31 bounded by
    convention 4's one-vocabulary rule.

## From slice 10c review (`3e849df` → `eca2846`)

41. **A contract clause that leaves an obligation "for the caller" binds
    every caller.** The registration ruling pinned `complete()`'s rejection
    path at the seam — nothing appends, "the attempt stays in flight *for
    the runtime to fail()*" — and slice 10c shipped two drivers of that seam
    whose terminal-failure guards covered only the handler run: a result the
    commit rejected escaped both, leaving a begun attempt in flight with no
    terminal record. The delegation clause had been read as documentation;
    it is enumerated surface. When a seam's contract hands a duty to its
    caller, each caller discharges it and pins it with its own test — the
    seam's test proves the state is *left*, only a caller's test proves it
    is *taken*. Convention 13's enumerate-every-item discipline applied to
    obligations that cross a seam.

42. **Guard on the condition the message states.** The early-wake refusal
    reported "clock woke at {observed}, before the requested maturation
    {pending}" while its predicate tested a downstream proxy — `wake()`
    returning None — equivalent to the stated comparison only through a
    load-bearing comment about what appends between two calls. Widen the
    proxy's semantics and the message silently lies. When a rejection
    asserts a relation between values it holds in hand, the guard performs
    that comparison; a proxy signal is admissible only where the direct
    check is unknowable at the guard. Convention 24's honesty moved from
    the message into the predicate.

43. **Coining a layer name is a ubiquitous-language event.** The slice
    introduced "the driving runtime" across module docstrings, an ast-grep
    rule message, tests, and a commit message — while CONTEXT.md neither
    defined the term nor stopped assigning the responsibilities the slice
    had just moved (wakeups, timestamping, scheduler application) to the
    old holders. Convention 5 reads names *out of* the registry; its
    converse is that putting a new name *into* circulation owns the
    registry in the same diff: register the concept, and re-home the
    entries whose duties it took — else code and language fork at exactly
    the seam the name exists to mark. Convention 27's sweep, in the
    coining direction.

## From the persistence-seam review (`f2ccfcd` → `1fc0335`)

44. **The slice that makes a step fallible re-audits every caller's commit
    ordering.** Injecting a durable history made `history.append` — until
    then a pure list mutation that could not raise — able to fail, and five
    appending doors were exposed committing dependent state *before* it:
    `_advance` (and `_next_attempt`) ran ahead of the append, so a raising
    backend left the watermark claiming an instant no appended record
    proves. Two reviewers converged on it independently. The ordering was
    not a defect when written; it became one at the slice that widened the
    failure modes — and that slice owns the audit: fallible effect first,
    dependent state after, pinned with both the real failure (an
    unencodable record) and a refusing double (I/O). Convention 10 applied
    to failure modes rather than vocabulary, with convention 34's one
    commit point gaining an order: advance-after-append.

45. **One semantic fact commits as one append batch.** Construction's
    initial records, begin's initiation+begin set, and seal's close-all
    each appended record-by-record — harmless in memory, but a durable
    backend makes each call its own commit, so a mid-fact failure could
    persist a valid *partial fact* (an initiation with no begin, half a
    seal) that loads back as truth. A door that appends a multi-record
    fact hands the whole batch to one `extend`, and the backend makes a
    batch durable whole or not at all. Convention 28's no-partial-fact,
    lifted from validation order to append granularity.

46. **Scope a durability claim to the failure class the code structurally
    rules out.** "Whole-batch or nothing — never a valid prefix of a
    failed commit" was true against encoding failures (the batch encodes
    before the file opens) and false against OS write failures (a
    complete-line prefix can land and loads back silently). The honest
    spelling names the class each guarantee covers and states the posture
    for the rest: encode-fails-loud before the file opens; an OS failure
    is the crash posture — a torn line fails loud at load, a complete-line
    prefix reads back as a consistent earlier history that memory never
    got ahead of. Conventions 22/29 applied to atomicity prose: an
    absolute a refactor can trust is worse than a bounded truth.

## From the resume-constructor review (`4eca82d` → `6fe7010`)

47. **A door that admits N projections of recorded state guards all N
    symmetrically.** resume rebuilt three node-bearing projections and
    guarded two: registration sources and in-flight transitions each got a
    foreign-node rejection, while the marking — the one projection that
    literally carries tokens — replayed unvalidated, silently seating
    tokens on places the net does not have; the docstring meanwhile
    claimed the door whole ("records naming nodes this net does not
    have... are a foreign trace"). Both skeptics confirmed the blocker.
    The sibling guards prove the door was known; the projection they skip
    is where the trace diverges silently. Convention 32's
    every-enumerated-conjunct, counted per projection — and the live entry
    points' partition rules (begin never schedules a source, deliver never
    feeds a non-source) bind the rebuilt traffic too (convention 36).

48. **A rebuilt value is valid only if the live writer could have written
    it.** The resume folds first accepted states no instance can produce:
    consumed records disagreeing with the transition's consume arcs,
    instants stepping backwards, end records with no terminal boundary (a
    torn commit batch whose re-execution would deposit twice). "The single
    writer validated before appending" is itself a replayable invariant:
    every projection re-checks what the writer's own validation
    guaranteed, and a trace that disagrees is replay divergence, loud —
    never material to rebuild from. `replay_marking`'s original
    cannot-consume-what-isn't-there check was this rule's seed; a new fold
    inherits the posture for its own invariants, not just its mechanics.

49. **Fold a closed union loud-by-exclusion, not silent-by-reflection.**
    The attempt-counter scan read `getattr(record, "attempt", None)` —
    stringly-typed, and silently skipping any future record category
    without the field. The fold now excludes the two attempt-less types by
    isinstance and reads `.attempt` off everything else, so a new union
    member breaks the fold loudly until deliberately classified — the
    union-completeness twin of the codec test that fails until a new
    category is proven. On a closed union, write the fold so the unknown
    member breaks the build, never the data.

## From the interleave-seam review (`beaa717` → `120c361`)

50. **Calling an adapter a twin makes the sibling's distrust enumerated
    surface.** The module sold `Sensor` as "the Clock's ingress twin", and
    the Clock's contract is *guarded*: an early wake is refused with a
    ValueError over spinning on it. The twin's one unguardable break — a
    sensor returning None, which reads falsy, a plausible "nothing to
    deliver" — was silently converted into ending the run. A contract break
    that no downstream door can catch is exactly the one the consulting seam
    must refuse itself; the sibling's guard proves the posture was known.
    Convention 25 ("like its sibling" is checkable) extended from
    implementation shape to failure posture, with convention 36's
    partition logic: the misuse the twin cannot delegate is the first one
    it owes.

51. **Snapshot an adapter's answer before judging it.** The sensing leg
    judged `if deliveries:` directly on the adapter's return — truthiness
    on a shape the loop does not own, and a generator is truthy while
    empty: the loop would consult forever, landing nothing, appending
    nothing — a silent spin two stanzas below the guard that refuses
    exactly that failure for the Clock. `tuple(answer)` at the consult
    makes the emptiness judgment structural and hands the loop its own
    immutable copy. Convention 17's normalize-at-the-boundary applied to
    control flow: a judgment (emptiness, truthiness, length) on foreign
    data happens only after the seam owns a snapshot of it.

52. **A projection named by a predicate contains exactly what satisfies
    it.** `armed` mapped *every* source door, sealed ones as empty sets —
    so the natural read (`if instance.armed`) was true on a fully sealed
    net, and the property's own consumers dodged the name's lie with
    `any(...values())`. When the kernel itself must re-filter a property to
    get what the name promises, the shape is wrong: make the mapping's
    truth BE the judgment (armed doors only), and leave the adjacent
    question the extra entries answered (is this node a source at all?) to
    the surface that owns it (`net.is_source`). Convention 4's
    one-concept-one-name in property position: the name is the whole
    contract.

53. **Adapter memory that the records can prove seeds from the records at
    resume.** The git-tree sensor's dedup memory (`last_delivered`) is
    live-side state, lost at a crash — but the `tree_state` mirror it fed
    IS that memory, recorded: a fresh unseeded sensor re-delivered the
    state the history already held, growing a resumed run's record past its
    uninterrupted twin's. Resume's rule for callables ("code, not facts —
    re-supplied") has a converse for adapter state: what is derivable from
    the recorded projections is *derived*, never reset — seed the fresh
    adapter from the projection (`GitTreeSensor.resuming`), and pin the
    no-redundant-fact property with a resume regression. Convention 48's
    live-writer discipline extended to the adapters around the instance.

## From the agent-handler review (`450227f` → `5f6ef7a`, `43d2bcc`)

54. **Pin a complement property at the crash point where it costs, not
    where it is free.** At-least-once ("a crash mid firing re-executes on
    resume") was pinned only at the virgin-territory crash — begun, agent
    never ran — where re-execution is benign by construction. The crash
    point where the promise actually bites (the agent worked and committed,
    the process died before the result was recorded, re-execution collides
    with the territory) was the module docstring's own claim, pinned
    nowhere — and it is exactly the pressure the experiment exists to
    surface (non-idempotent handlers under at-least-once). Convention 22's
    prose-specifies-the-test, sharpened: of a property's crash points, the
    one that must exist as a test is the one where the property costs.

55. **A tripwire is armed only if the failure cannot reproduce the recorded
    answer.** The scripted agent's invocation ordinal was sold as making
    "any re-invocation observable in what the net records" — but the replay
    tests hand resume a FRESH agent, whose wrongful first call reports
    "invocation 1", byte-identical to the recorded fact; only the demoted
    counter actually pinned the property. Three reviewers (two lenses and
    gpt-5.5) converged independently. Seed the fake's state past the
    recorded output (`fresh.invocations = 41`) so the wrong path cannot
    echo the right answer, or scope the claim to the lifetime it covers
    (convention 46). A tripwire that the advertised failure walks through
    untripped is prose, not proof.

56. **A poison pin covers exactly the surface its claim names.** "Proves no
    handler ran at all" while poisoning one handler of four: the other
    three were live closures, and a replay that wrongly re-ran them would
    have passed silently. Either poison the whole mapping so the sentence
    is what the test proves, or shrink the sentence to what the poison
    covers. The claim's scope and the instrumentation's scope are one
    decision, not two.

57. **Assert a recorded fact whole: payload, multiplicity, correlation.**
    The replay pin probed that *a* `HandlerResultRecorded` for the
    transition existed and read one token out of it — an existence probe
    that would have admitted a duplicated record, a wrong destination, or
    an uncorrelated attempt. A test that leans on a record asserts the
    record: exactly one, its exact destination-coalesced payload, and the
    attempt id tying it to its firing's terminal boundary (convention 11's
    each-enumerated-item, applied to the history's records).

## From the ES-008 join-correlation review (`3e408d9`…`7ddc2d5` → `a119b9c`)

58. **A computation widened from one result to many keeps its old result
    first, and that ordering is the contract.** Candidate enumeration went
    from one FIFO-head binding per transition to every admissible binding
    (the cross product of each arc's admitted combinations). The head
    selection stays the *first* binding — input-arc-major, FIFO-position-
    minor — so the conservative scheduler (`select_conservative` takes
    `bindings[0]`) fires byte-identical to the single-binding path, and the
    whole existing suite needed only the pins that *asserted* the old
    narrowness to flip. When a slice turns a one-of into an all-of, the
    determinism the callers depended on is preserved by making the former
    single result the ordered head — and that order is pinned as a contract
    (full ordered lists, exact multiplicity), not left to `itertools`
    incidental behavior. Convention 4's one-home for the default, in
    enumeration position: the default policy still gets exactly one answer,
    now by ordering rather than by the core pre-choosing.

59. **A guard that would wedge under the old narrowness is only safe once the
    enumeration that skips-not-disables lands.** The operator gate's
    `PAIRED` id-match guard correlates each decision to its own issue at the
    approve/reject joins — expressible all along, but under single-binding
    enumeration a mismatched FIFO head pair would have *disabled* the join
    even with the matching pair sitting deeper in the queues (a wedge worse
    than the FIFO mis-pairing it replaced). The guard and the enumeration
    are one capability: the per-binding skip (a skipped selection never
    disables a transition another selection enables) is the *precondition*
    that turns "the decision for THIS issue" from a wedge into a filter.
    When a correlation/narrowing guard rides on top of candidate selection,
    it is safe exactly when enumeration offers the alternative it needs —
    name that dependency, and pin both the guard picking the deeper match
    *and* the wedge it would have been without enumeration.

60. **Evidence stamped for routing is stripped at the door that spends it,
    by a handler, and the strip's scope is pinned where it stops.** The
    verify verdict (`passed`) exists for the routing filters; once the flow
    has routed, it is spent residue, not domain data — so `finish` strips it
    off the done token via a shaping handler (passthrough never reshapes;
    the `refresh_tree` precedent). The cost is honest — one activity record
    per landing — and, crucially, the *scope* is pinned: the terminal door
    strips, and a test pins that the reject loop-back still carries the
    stale stamp, so the wider evidence-clearing-on-loop-backs pressure stays
    visibly open rather than looking closed. When a shaping handler removes
    a field, pin both the removal at its door and the surface it does *not*
    reach (convention 56 for a strip: the claim's scope and the handler's
    scope are one decision). *(Provisional: the `finish`-strips-evidence
    call is recorded for Navigator ratification in the ES-008 story, not
    settled by this review.)*

61. **Subclass a native type only when its native equality carries your
    semantics; wrap when your distinction is the point.** `NetPath` IS a
    `tuple` subclass rightly: a path is semantically a segment sequence in
    one namespace, so tuple equality is path equality. `Cel` must NOT be a
    `str` subclass: str equality ignores subclasses, so a named symbol and a
    bare-identifier expression would collide as registry keys — the tag IS
    the distinction, and the wrapper mirrors the IR's explicit tag (JSON has
    no subclasses). The test is one question: does the native type's
    equality preserve or erase the concept you are encoding? (Ruled during
    ES-012 session 1; `Cel.__str__` is the sanctioned concession —
    presentation without identity.)

62. **Kernel data flow is eager function composition over owned,
    glossary-named value types.** Each step is called immediately and its
    value result feeds the next (`route(admitted, outputs)`), mirroring the
    macro pipeline (`candidates → scheduler → begin → complete`). No lazy
    pipelines or generator chains in semantic data flow: values are facts —
    materialization is where something becomes recordable, comparable, and
    replayable. A collection verb (method or function) exists only when the
    glossary names its concept; otherwise a comprehension is the honest
    spelling. (Ruled during ES-012 session 1; executed by the determination
    window.)

63. **A durable writer encodes the whole batch before opening the sink.**
    A record that cannot be encoded must fail loud before anything reaches
    disk — never interleave encoding with writing, or a mid-batch encode
    failure manufactures on disk the exact torn-commit shape replay treats
    as corruption. IO may stream; encoding may not. The durability policy
    (where/how bytes land) and the format (codec, envelope, batching,
    tornness) are separate homes, but this ordering invariant belongs to
    the writer whoever owns it. (Named during ES-012 session 2; pinned by
    the determination window's byte-level wire fixture.)

## From the DS1a review (`352e689` → `ac6128d`)

64. **A replay validator's rule binds the writer at its door, from one
    home.** Resume validated the begin-batch shape — one selection per
    consume/read arc, input-arc order, weight tokens each — that `begin()`
    itself never enforced, so the single writer could append a begin batch
    its own resume refuses: a crash turned an accepted live binding into a
    rejected trace (demonstrated live by the review). Convention 48's
    posture — a rebuilt value is valid only if the live writer could have
    written it — has a contrapositive that is enumerated surface: the
    writer refuses at its door whatever replay would reject, and both
    sides call one shared helper (`_validate_binding_shape`) so the rule
    cannot drift apart. The consume half of the asymmetry predated the
    slice; it became a defect at the slice that added the read mirror and
    made the shape rule explicit — the slice that extends a replay
    validator owns auditing its writer-side twin (convention 10 applied
    across the write/replay pair, with convention 34's one-home for the
    rule itself).

65. **A writer-derived fallback in a caller-writable field reserves its
    namespace.** Firing begin derives `"occurrence-{id}"` when an activity
    handler supplies no correlation or idempotency, so a supplied value in
    that namespace could collide with a later derived one. When a writer mints
    fallback values into a domain callers also write, the derived form's shape
    is a reserved namespace: state the reservation where the derivation lives,
    and reject supplied values inside it at the admitting door, before
    anything is recorded, naming the reserved prefix. Convention 17's
    normalize-at-the-boundary for identity minting: the collision is created
    at the door that admits both spellings, so it is refused there — never left
    for the consumer to misread as equality. Source delivery no longer has a
    writer-derived fallback: every ingress adapter must supply its stable
    reconstructible identity.

## From the DS1b review (`f80f075` → `9bd42ce`)

66. **A payload the writer will judge by value is snapshotted canonical at
    its door.** The activity seam froze `input` and `result` as the live
    references its callers handed over — so a caller's later mutation could
    diverge the live projection from the durable record, a raw `==` was the
    wrong idempotency comparator across the durable round trip (the frozen
    tuple form and its decoded list form read as an "operational conflict"
    that never happened), and a net object could ride an invocation ruled
    Petri-agnostic. When a recorded value's EQUALITY is load-bearing for a
    writer decision (K6's acknowledge-or-conflict), the writer takes a
    canonical copy — the value's durable spelling, here a JSON round trip —
    before anything freezes or appends: the retained value IS the durable
    value, lossy shapes canonicalize exactly once, and the unencodable
    payload fails loud at the door instead of at the backend. The contrast
    is the discipline's edge: ordinary token-data doors do not canonicalize
    because no writer decision compares their data; identified source
    delivery does because acknowledge-or-conflict compares its complete token
    content. Convention 17's normalize-at-the-boundary, sharpened to WHEN it
    is owed: at the door whose later judgment reads the value back.

67. **A ruled seam contract crosses the seam whole — the carrier, not a
    projection of it.** The `Activity` callable took bare `input` while the
    ruling enumerates the worker-visible contract as the whole invocation:
    typed input, resolved policy, correlation identity, idempotency
    identity, capabilities — and a real activity spends the idempotency key
    on its provider call, so the projection under-delivered the exact field
    recoverable execution exists for. When a decision record enumerates
    what crosses a seam, the seam's callable receives that enumerated value
    itself; handing a convenient slice of it re-decides the contract by
    signature. Convention 31 (a ruling's spelled call shape is enumerated
    surface) in parameter-TYPE position, with convention 13's rule of thumb
    intact: the field that feels omittable is the discriminating one.

## From the DS2 review (`77c47b2` → `f5d3839`)

68. **A new fold owns its divergence rules.** `replay_terminal_activity`
    shipped as a permissive projection — a second terminal activity fact
    overwrote the first, a fact ordered after its firing's end folded
    silently — while every sibling fold (`replay_armed`,
    `replay_watermark`, `apply_movement`, the lifecycle sort) refuses what
    the live writer cannot append, and the index this one feeds is what
    the ended-acknowledgement door ANSWERS REDELIVERIES from: a corrupt
    trace would silently change which result gets acknowledged as truth.
    Convention 48/64 counted per fold: the moment a projection is written,
    the writer invariants it leans on (here: exactly one terminal activity
    fact per occurrence, frozen before the terminal boundary) become that
    fold's own loud refusals — never deferred to whole-trace auditing
    (which stays the declined validation-layer posture), and never assumed
    covered by a sibling fold that reads different records.

69. **An observation surface hands out detached views, and its actions
    speak in ids.** `Snapshot.in_flight` exposed live `FiringOccurrence`
    values (and `AcceptResult` carried one), handing every policy a
    mutation path into the writer's canonical state — an invocation's
    recorded `input` dict is the same object the durable record froze.
    Now the policy observes a frozen `InFlightView` (id, transition,
    consumed selections, purity — exactly the commissioned independence
    check's input), actions reference occurrences by id, and only the
    coordinator resolves an id back to the writer-owned occurrence at
    apply. When a seam exists so an outside component can observe and
    choose, what crosses it outward is detached evidence, never handles —
    and the detachment is scoped to that seam: token payload aliasing
    stays the repo's documented posture, stated where the view is defined,
    not "fixed" by deep-freezing the world. Convention 33's
    derived-views-speak-recorded-truth, pointed at mutation instead of
    time.

## From the DS3 review (`6579cda` → `e58158b`)

70. **An acknowledgement is not an append — memory mirrors durable truth,
    never intent.** The verify-on-conflict door acknowledged a terminal
    fact already durable at ANOTHER position, then mirrored the record
    into the in-memory history anyway: memory ahead of the table, the
    position sequence gapped, and the reloaded history minted a colliding
    identity on its next append — the backend could not continue past its
    own idempotence. An acknowledgement asserts EXISTENCE, not placement:
    what enters local state is what the durable side proved — a
    value-equal row at the expected identity fills the position and
    mirrors; a fact acknowledged elsewhere enters nothing, and identities
    derive from the position actually filled, never a raw enumerated
    offset. Convention 33's derived-views-speak-recorded-truth pointed at
    the writer's own cache: the in-memory records are a projection of the
    rows, and an append call's outcome is part of the projection's input.

71. **A transactional backend's rollback is a whole-runtime event.** The
    join-mode obligation was first written as "discard the backend
    instance and reload" — while the NetInstance over it had already
    advanced watermark, marking, occurrence counter, and in-flight on the
    facts the rollback retracted, and nothing said so. When a backend can
    retract appends (a caller-held transaction), every stateful object
    DERIVED over it shares the transaction's fate: the documented rule
    names the whole derivation chain (backend, instance, coordinator),
    the coherent continuation is ``resume`` over a freshly loaded
    history, and the rule is pinned by driving live state through a real
    rollback — not by prose alone. Convention 44's audit widened from the
    step that can fail to the commit that can be taken back; the
    ENFORCING wrapper may be deferred to the layer that owns the
    transaction, but the deferral is recorded, never implied.

## From the DS4 review (`1e27395` → `0c45a8f`)

72. **A wrapper that promises structure delivers structure.**
    `AuthoritySession` sold itself as the ENFORCING join-session — poison
    after rollback, every door refusing — while exposing `.coordinator`,
    `.adapter`, and `.instance` as public attributes: the fate rule held
    only for callers who volunteered to use the doors, and the review
    drove the writer straight through `session.coordinator.drive()` on a
    poisoned session, empirically. When a wrapper's reason to exist IS an
    invariant (one transaction fate, one writer, one lifecycle), the
    invariant must be unreachable to violate through the wrapper's own
    surface: collaborators private, observation through read-only
    accessors that themselves honor the lifecycle, and the bypass pinned
    impossible (the attributes are gone; assignment refuses). Convention
    2's enforce-don't-assert at object-composition scale — a prose
    "enforcing" over public handles rots exactly like a prose "immutable"
    over a public dict.

73. **Distinct ruled durability boundaries stay distinct under any commit
    hook.** The coordinator's joined-transaction hook fired once per
    applied action — which silently merged the ruled two-boundary
    completion (`ActivityCompleted` commits BEFORE deterministic
    projection) into one transaction: right records, right order, wrong
    atomicity — a projection crash rolled the frozen result back and
    would re-execute completed external work. When a driver grows a
    transaction-marking hook, every durability boundary a ruling
    separates inside one action gets its own hook invocation; "per
    action" is the wrong grain the moment an action spans two boundaries
    the spec keeps apart — and the right grain is pinned by crashing
    BETWEEN them on the joined backend. Convention 45's
    one-fact-one-batch counted from the other side: two facts never share
    one commit just because one hand applied them.

## From the ES-013 review (`4396992` → `0ff4fb3`)

74. **An activity's retry policy answers its mutation order.** The liaison's
    LLM activities shipped with one shared `ExecutionPolicy(attempts=2)`
    named `AUTHORED` — by their technology — and the live run demonstrated
    the miss: `adapt` revises the plan page *before* its riskiest step (the
    coder in the worktree), so its retry re-revised the page for one coder
    failure (v3 with no commit landed) — one failure, two mutations. The
    judgment a resolved policy encodes is not "is this an LLM?" but "does
    anything mutate before the failure modes?": grant retries only to
    activities whose failures precede their mutations (triage, plan-writing
    — a garbage answer costs a second try, never a double effect), keep the
    conservative one-attempt default on anything that mutates first, and
    name the policy value by that property (`RETRY_ONCE`), per convention
    37. Pin both halves where they cost (conventions 22/54): the retry that
    saves the item, and the single attempt that leaves one failure as one
    mutation. Idempotency is the eventual cure; until an activity has it,
    the policy IS the idempotency statement.

## From the ES-014 review (`cb32ec7` → `2395c74`)

75. **Admission is field-complete: the seam owns every field any later
    firing reads.** The secretary's "double validation" (closed grammar at
    parse, ids-against-digest at projection) still admitted a
    within-grammar `updated` event with no `due` — recorded durably, it
    crashed `apply_update` with a raw KeyError three firings later, on a
    token no retry protects. A validating seam is not done when the shapes
    and ids check out; it enumerates every field each downstream pure
    handler or guard will read (conventions 13/28 joined), because the seam
    is where the invocation's retry lives and downstream is where recorded
    state lives. If a pure firing can KeyError on admitted data, the
    admission was incomplete — fix the seam, never the consumer.

76. **A multi-token join must be unenableable for inputs its handler would
    refuse.** `snooze_item` validated its ruling's deadline inside the
    handler — after the firing had consumed the worry, the ruling, and the
    commitment; the raise kept the consumption and destroyed all three
    (review reproduced `Marking({})`). A terminal firing failure retains
    what it consumed, so a join's preconditions belong where they prevent
    the binding from existing: at the ingress door that records the token
    (the source handler refuses the malformed ruling) AND on the arc filter
    that admits it to the join (`kind == 'snooze' && due > 0`) — two locks,
    both cheaper than any recovery. Handler-side checks on a join guard
    nothing; by the time they run, the tokens are already spent.

77. **Permanent keyed idempotence is how a mutating activity earns its
    retry.** Convention 74 left "idempotency is the eventual cure" as a
    promise; the secretary needed the cure: `reconcile` mutates the world
    (desk asks) before its result freezes and still wants the retry its
    fallible analyst deserves. The resolution is an idempotence *key* owned
    by the callee (`Desk.ask(item, key=…)`), deduplicating forever — not
    "while unanswered", because the race that matters is a retry arriving
    after the answer. The key encodes the worry's identity (`overdue-{id}-
    {due}`), so a genuinely new worry about the same subject is honestly a
    new question. Pin both properties where they cost: the retry that asks
    once (a flaky first answer, one desk entry), and the distinct key that
    asks again (same commitment, new deadline, second question). And state
    the mutation in the prose — a docstring claiming "no world mutation"
    over an activity that asks a human is how the next reader inherits a
    false safety proof.

## From the ES-016 convergence runs (`explore/es16-convergence`)

78. **Validation lives on the retry side of the freeze.** Convention 75's
    field-complete admission sat in `project()` — and a live run showed a
    projection rejection is TERMINAL: the activity result is already
    frozen, projections never retry, so the analyst's "second chance"
    (RETRY_ONCE) never saw the semantic checks at all. The rule: any check
    that an activity's retry should get another attempt at belongs *inside
    the activity*, before it returns (the invocation input carries the
    state the check needs — that is what the digest-join put there); the
    projection re-runs the same pure check as a final assert, never as the
    first line of defense. Where a seam has two sides, know which side the
    retry lives on before deciding where the validation does.


79. **A reference on a token must route, or it is a merge bug wearing a
    docstring.** D2/D3's first cut carried "the transcript by reference"
    in prose while the activity resolved a closure-bound store — the token's
    reference was decorative, and two sessions sharing an adapter would have
    merged into one tree (D3 appended under a *global* tail). The rule: if
    a token claims to reference territory state, the reference must flow
    through the frozen invocation and resolve at the worker against a
    registry, and a test must run TWO sessions over one registry and prove
    no cross-talk. A reference nothing dereferences is worse than none: it
    reads as routing that isn't there.

80. **An invariant between inscriptions belongs to the constructor, not to
    a docstring plea.** The consultation net's first cut documented "consult
    must exclude what compact admits" and then let every caller hand-build
    both filters — and the same race it warned about was live on the close
    arc it forgot. The fix: the net constructor takes ONE fullness
    expression and mints the complementary filters itself (and the close
    path inherits the same threshold plus an inhibitor on pending work), so
    the race is unrepresentable rather than discouraged. When a module's
    own prose warns future callers to uphold an invariant, that is the
    constructor asking to own it.

81. **Pin the mechanism's signature, not a byte ratio.** Three growth tests
    asserted `first-vs-last < 2x` style bounds; one certified "bounded"
    for a design whose summaries nest and grow without bound — it passed
    at 8 turns and fails at 7 or 9, a verdict by loop-length parity. The
    replacements assert what the mechanism *does*: re-recording shows as
    strictly-increasing per-turn deltas and higher multiplicity for older
    text; leanness shows as constant multiplicity and a pinned invocation
    shape; a bounded digest shows as an entry-count ceiling on every frozen
    invocation — while the nesting growth is pinned AS the finding. Raw
    bytes stay demo evidence; envelope overhead can shift them without the
    design changing, and a shape assertion must survive that.

## From the ES-022 unit 0 review (`7834f30` → `763cc7a`; conventions 82–85 [ratified as written](../project/decisions/records/2026-07-19T1434Z-conventions-82-85-ratified.md))

82. **A parity surface must carry the outcome's semantics, not its verdict
    alone.** The first `OutcomeReport` recorded that extraction happened
    (`parse_failed`, a title, a status) but not what the user would feel —
    memory content and context, the task's prose, the proposal's merged
    text, the conversation summary. That made the hardening claim
    unfalsifiable: "parse failure still continues to the summary phase" was
    asserted in a docstring while the fixture couldn't show a summary at
    all. The rule: whatever a comparison is supposed to prove end to end
    must appear as data in the compared surface. If the report can't show
    the fallback summary next to the terminal status, the harness proves
    routing of statuses, not equivalence of behavior.

83. **Derived vectors need two identities: one for the document, one for
    the embedded text.** The first cache keyed everything off one content
    hash, so a readiness advance (frontmatter-only) re-embedded an unchanged
    memory, and swapping the embedder model silently overwrote vectors
    computed by another. The split: `document_hash` over the whole rendered
    file answers "did anything change" (re-index); `embedding_hash` over
    exactly the text the oracle embeds answers "does the vector still
    stand" — keyed with (model, version) so a model swap is a new key,
    never an overwrite, and orphaned vectors are collected, never
    accumulated. Any cache that derives expensive artifacts from a slice of
    a document needs the slice's own identity.

84. **A canned oracle must refuse prompts it does not recognize.** The
    first harvest driver answered unknown prompts with a neutral reply, so
    a drifted pin or an uncovered code path would harvest a plausible,
    silently wrong fixture. Strict dispatch — unknown prompt raises, pin
    verified before patching, patches restored after — turns missing
    coverage into a loud failure at harvest time instead of a parity bar
    that certifies the wrong behavior. The fixture's trustworthiness IS the
    experiment's floor; a stand-in that improvises is not a stand-in.

85. **A recording stand-in hands out copies in both directions.** The
    scripted intelligence deep-copied payloads on the way in but returned
    script values (and shared NEUTRAL mutables — `[]`, `{}`) by reference,
    so a caller appending to its "own" extraction list would rewrite the
    script for every later call. Evidence out, answers out, payloads in:
    all copies. An instrument that can be mutated by its subject is not
    measuring it.

## From ES-038 and CV6.TS6 History Store/Dispatch convergence

86. **Capability profiles name guarantees; implementations name substrates
    and providers.** PostgreSQL plus Absurd originally made joined publication
    look like the definition of both storage and execution. ES-038 removed the
    shared transaction and recovered every split-commit window through the
    canonical `ActivityRequested` outbox and persistent operational terminal
    reports, while also reproducing an external effect. The rule is to name
    product seams and profiles by the custody or durability boundary they
    promise (`HistoryStore`; Inline, In-Memory, Local, or Durable `Dispatch`),
    and name concrete classes by their implementation (`JsonlHistoryStore`,
    `PostgresHistoryStore`, `AbsurdDispatch`). A stronger composition such as a
    joined transaction remains a documented composition guarantee, never a
    universal protocol requirement. Tests must pin the semantic bytes and the
    weakest honest failure claim: at-least-once effects, never exactly-once.

## From Engine ingress fairness and operational-host convergence

87. **A live Instance has one public host owner: Engine; repetition belongs to
    the outer host.** A maintained operational host creates or loads one
    `Engine`, advances one normal Action per turn, reads immutable Engine views,
    and closes that Engine. It does not construct private `Coordinator`, retain
    a legacy run-to-rest `Runner`, or demand a mutable Instance/History/
    Dispatch/fence escape hatch. Re-drive loops, timer sleeps, provider waits,
    async multiplexing, multi-Engine orchestration, and Fabric remain at the
    actual host boundary because their stop, crash, and custody conditions
    differ. Repeated construction alone does not earn a factory; add an Engine
    door only when distinct maintained host shapes demonstrate one universal
    responsibility.

## From a topology rewrite

88. **Treat Activity derivability as a Petri-net design diagnostic, not a
    target metric.** When a typed Activity does not derive cleanly, first ask
    whether the topology is hiding a state, join, classification, reservation,
    or authority transfer in imperative preparation or projection code. Move
    workflow routing and token custody into the net when that makes the domain
    more truthful: Activities perform effects over typed domain values; pure
    transitions authorize, classify, and advance explicit state. Do not
    distort a genuine domain operation merely to satisfy a derivation rule,
    and do not grow the ordinary derived handler into a routing language to
    preserve an under-specified net. The topology rewrite is the concrete
    precedent: distinct review places expose the join, guarded CI transitions
    expose verdicts, and one `head.active` token makes apply/repair exclusion
    structural, allowing every Activity to use strict `DerivedActivityHandler`
    without changing Engine, Coordinator, Worker, or Dispatch protocols.

## From the canonical-Net Graphviz renderer review

89. **Expose semantic judgments before exposing an enum.** When a consumer
    only needs to ask what a value means, let the value answer in domain
    vocabulary (`arc.is_consume`, `arc.is_read`, `arc.is_inhibit`) instead of
    requiring the consumer to import an enum and reproduce comparisons. Keep
    the enum where a closed canonical representation still earns it —
    construction, serialization, exhaustive dispatch, or schema validation —
    and derive predicates from that one source of truth rather than storing
    duplicate booleans. The aim is not to ban enums; it is to prevent internal
    representation machinery from becoming the ordinary query API when an
    intention-revealing judgment is smaller and more stable.
