# 1 Engineering conventions

Implementation practice for contributors to Petrus. Read the defaults below,
then follow the topic map when a change needs a more specific rule. The
[review cases](engineering-review-cases.md) preserve the numbered conventions
and their evidence without making every contributor read the full chronology.
Prefer small APIs, immutable values where practical, and designs grounded in
current requirements.

## 1a Scope and authority

This guide and its numbered review cases own reusable implementation practice.
Keep other knowledge with its existing owner:

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

## 1b Updating conventions

Start with the topic map and operational defaults, then read the cases
relevant to the change. Each case gives the rule, failure mode, and evidence.

When a review reveals a practice worth retaining:

1. state it in imperative, domain language and name the boundary it governs;
2. record architectural choice or accepted debt in its proper home first;
3. add the smallest reusable rule to the relevant case, with review provenance;
4. promote mechanically checkable structure to `rules/*.yml` rather than
   relying on prose alone.

Do not add framework-specific ceremony before Impetus owns that framework or
surface. A future CLI, telemetry API, database adapter, or worker system earns
its detailed conventions when implementation and review provide evidence.

## 1c Topic map

Numbers refer to the [review cases](engineering-review-cases.md). Several
cases apply to more than one concern.

| Concern | Primary conventions |
| --- | --- |
| Domain vocabulary, ownership, and public API | 2, 4–7, 16, 20, 23, 29, 31, 35, 37, 40, 43, 52, 61–62, 67, 69, 72, 79–80, 87–89 |
| Boundary validation, normalization, and diagnostics | 1, 3, 10, 13, 17, 19, 24, 28, 30, 32, 36, 39, 42, 47, 51, 65–66, 75–78, 83 |
| History, durability, transactions, and replay | 28, 33–34, 38, 41, 44–49, 53, 63–73, 86 |
| Scheduling, handlers, activities, and adapters | 32–42, 50–53, 58–60, 62, 67, 69, 72–80, 88 |
| Tests, fakes, fixtures, and evidence claims | 8, 11, 18, 21–22, 25–26, 54–59, 64, 74, 77, 81–82, 84–85 |
| Documentation, decisions, deferrals, and debt | 9, 12, 14–15, 20, 27, 35, 40, 43, 46, 60 |

## 1d Operational defaults

Use these defaults for ordinary Python work. A more specific ratified
numbered convention wins where one applies.

### 1d1 Boundaries and code shape

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
- Use accepted glossary names for domain values. Keep incidental local
  data in built-in collections when that remains clear.
- Prefer direct attribute access for a known contract. Reflection and
  `getattr(...)` belong at dynamic or compatibility boundaries, not
  in defensive code that would hide a closed-union omission.
- Validate semantic invariants once, at the door that owns them and before any
  irreversible fact is recorded. Do not duplicate an already precise local
  Python failure or wrap it without adding boundary context. Contextualize an
  error when crossing a seam would otherwise lose the declaration, identity,
  or operation that failed.

### 1d2 Scripts and command-line interfaces

- Parse and canonicalize syntax, scalar shape, paths, and operator intent at
  the outer boundary; canonicalize reusable domain input before side effects so
  direct callers receive the same semantics.
- Keep parsing, operation construction, serialization, and rendering separable
  when that makes the surface testable. Inner operations return values or
  structured reports; only the outermost adapter prints, writes, or exits.
- Never silently ignore, neutralize, or overwrite an operator-provided option.
  Reject incompatible options before starting work.

### 1d3 Tests and evidence

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
- Use partial shape assertions only for fields that are dynamic and
  irrelevant to the behavior. When a record or report shape is the contract,
  assert it whole, including ordering, exact multiplicity, payload, and
  correlation where applicable.
- An architectural improvement is not a throughput claim. Performance claims
  require a named, bounded workload, concurrency and environment, timing and
  memory evidence, failures, and relevant ordering/cache caveats.
