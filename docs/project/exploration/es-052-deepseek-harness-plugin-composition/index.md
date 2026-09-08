---
code: ES-052
status: Paused
status_reason: Source grounding and a Value hypothesis are preserved; Experiment 1 is deliberately deferred and promotion evidence does not yet exist.
opened: 2026-08-13
related:
  - CV16
  - docs/project/decisions/records/2026-08-03T0430Z-installations-own-authority-agenticus-owns-machinery.md
research_source:
  - https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a
  - https://github.com/cordiverse/paper/tree/948a07b369c62adb3b12e102458be5c18dfb69b9
---

# 1 DeepSeek Harness and Cordis composition

## 1a Paused before Experiment 1

ES-052 has a candidate for owned, inspectable Agenticus installations. Source
analysis is complete. The disposable mount experiment has not run, and the
candidate has no promoted Value or production API.

The next move is to reactivate Experiment 1 through a new Plan Checkpoint.
The [execution brief](future-execution-brief.md) owns its alternatives, probes,
stop conditions, and promotion requirements. Documentation closure does not
reactivate it.

## 1b Question and conclusion

The inquiry asked what DeepSeek Harness means by making product capabilities
plugins, and which mechanisms fit Agenticus. Harness has a small privileged
bootstrap kernel and a configured component tree. Its useful mechanism is
ownership of a component's registrations, resources, dependents, and cleanup.

Agenticus already has typed compatibility, explicit installation selection,
and immutable Episode resolution. The candidate fills the gap between an exact
resolved plan and its executable host composition. This is a design inference
from the sources, not an accepted implementation choice.

```text
host selection -> Catalog -> immutable ResolutionSnapshot
                                      |
                         proposed exact-profile composer
                                      |
                             owned live incarnation
                         children, inspection, cleanup
```

## 1c Research baseline

- `[D]` DeepSeek Harness was inspected at
  [`47f9438`](https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a),
  the head of `master` on 2026-08-13. Claims below link to that revision.
- `[D]` First-party Harness code is MIT-licensed under DeepSeek's 2026
  copyright. Cordis and its Loader are vendored MIT code from Shigma/Cordiverse
  with DeepSeek modifications; copying implementation rather than independently
  reimplementing an idea requires preserving the applicable Shigma and
  DeepSeek notices. The provenance is explicit in
  [`vendor/README.md`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/README.md#L1-L50),
  the [root license](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/LICENSE),
  and the [Cordis license](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/LICENSE).
- `[D]` The upstream Cordis design paper was inspected independently at
  [`cordiverse/paper@948a07b`](https://github.com/cordiverse/paper/tree/948a07b369c62adb3b12e102458be5c18dfb69b9),
  the head of `main` on 2026-08-14. The repository contains the
  [paper](https://github.com/cordiverse/paper/blob/948a07b369c62adb3b12e102458be5c18dfb69b9/paper.pdf),
  a short [README](https://github.com/cordiverse/paper/blob/948a07b369c62adb3b12e102458be5c18dfb69b9/README.md),
  and `.gitattributes`; it contains no explicit license file at this revision.
  The README identifies the PDF as an actively revised preprint dated
  2026-08-13. This exploration may analyze and cite it, but the repository is
  not a source-reuse license. Any future use of paper text or artifacts needs
  a fresh provenance and permission review.
- `[D]` The paper is *A Programming Paradigm for Spatiotemporal
  Composability*, by Yifan Shi, Wei Zhang, and Tianyi Cui (Peking University
  and DeepSeek-AI). Page references below use PDF page numbers from that pinned
  revision. The paper does not mention Petrus; every Petrus relation below is
  this exploration's explicitly marked **Petrus reading**, not an author claim.
- `[E]` Petrus's focused Agenticus catalog, profile, and Pi A2 host suites were
  executed against the source inspected in August 2026. The
  result is recorded under Historical verification.

Evidence labels follow project house style: `[D]` marks a direct
source-verified claim and `[E]` marks observed Petrus code or executed evidence.
**Petrus reading** marks synthesis from that evidence rather than a claim made
by the paper.

## 1d Mechanisms and their limits

The following findings refer to the pinned Harness revision. `[D]` identifies
source inspection; the Agenticus implications are this exploration's inference.

| Mechanism | Source and retained finding |
| --- | --- |
| Bootstrap | [`Context`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/context.ts#L70-L83) installs reflection, registry, events, logging, and the root Fiber before plugins. `[D]` |
| Executable mounts | [`registry.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/registry.ts#L91-L185) accepts functions, constructors, or `apply` exports. Tool, route, and UI registries retain their own contribution/conflict rules. `[D]` |
| Distinct identities | [`entry.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/loader/src/config/entry.ts#L8-L22) separates package/module, executable callback, configured entry ID, and live Fiber UID. Installed packages become composition inputs through declared bundle patches, not ambient scanning. `[D]` |
| Provider identity | [`fiber.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/fiber.ts#L597-L623) derives activation from provider UIDs. Missing services leave dependents pending; appearance activates them, withdrawal unloads them, replacement reloads them. Duplicate providers within one isolation realm fail. `[D]` |
| Owned cleanup | [`fiber.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/fiber.ts#L402-L560) tracks child resources and reverses registration order, awaiting asynchronous disposal. Loader updates attempt rollback after partial failure. `[D]` |
| Real composition tests | [Postmortem 0001](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/postmortem/0001-acp-default-export-drops-inject.md) describes how 178 passing tests missed lost plugin metadata and service-topology behavior. The public Loader path needs tests of its own. `[D]` |

The paper adds qualifications that matter to the candidate. Page numbers refer
to the pinned PDF, not a later preprint:

1. Temporal composition retracts tracked local acquisitions; spatial
   composition reacts to dependency providers. Components declare dependencies,
   provisions, and effects; Fibers are live incarnations. Sections 1.1, 1.3,
   3, and 4.1 through 4.3, pages 4 to 37. `[D]`
2. Withdrawal drains dependents before providers. An asynchronous reconciliation
   step already underway finishes before provider disposal. Sections 4.3 and
   5.1.3, pages 34 to 37 and 60. `[D]`
3. External writes and sends are emissions outside the tracked context. A
   supplied inverse is an author's obligation; neither the model nor a returned
   cleanup callback proves an external action was undone. Sections 5.1.1 and
   6.1, pages 56 and 67 to 68. `[D]`
4. Progress assumes finite Fibers, bounded iterators, and acyclic precedence.
   Confluence assumes independent steps, provision-total components, quiescence,
   and no failed Fiber. These results do not prove Petrus replay, exactly-once
   effects, or recovery under failure. Sections 4.4.4 and 4.4.5, pages 47 to 53.
   The Petrus boundary is this exploration's inference. `[D]`
5. Dependency visibility is not a malicious-code sandbox. Cycles remain
   inactive; key collisions and interface/version compatibility remain open.
   Koishi supplies adoption evidence rather than quantitative evaluation;
   self-evolving agent systems are future validation. Sections 5.3, 6.3, 6.5,
   6.6, and conclusion, pages 67 to 79. `[D]`

## 1e Petrus ownership and candidate constraints

The inspected Agenticus code already separates
[descriptors](../../../../src/petrus/agenticus/catalog/descriptor.py),
[exact resolution](../../../../src/petrus/agenticus/catalog/resolution.py),
[runtime profile data](../../../../src/petrus/agenticus/runtime/profiles.py),
and [Pi A2 host construction](../../../../src/petrus/agenticus/runtime/pi_a2_host.py).
These were August observations; recheck the current implementation before an
experiment.

| Owner | Meaning to preserve |
| --- | --- |
| Installation | Security principal, enablement, explicit selection, credentials, product policy, event loop, and process lifecycle. Declared dependencies grant no authority. |
| Catalog and resolution | Portable typed descriptors and an immutable accepted snapshot. Executable factories and live collaborators remain separate. |
| Agenticus | Optional reusable composition machinery. A mount is a process-scoped operational owner, distinct from Connection, Episode, Attachment, Hands, or provider session. |
| Motus | Execution territory, Activity custody, and the evidence that a lease or provider resource was released. |
| Impetus | Canonical Petri semantics and append-only History. `LifecycleScope` is a durable workflow generation, not a host mount. |

Provider replacement may change readiness for future plans. It cannot hot-rebind
an active Episode. Composition cleanup can release owned acquisitions, leaves
borrowed collaborators open, and preserves uncertain external emissions as
uncertain. Existing domain/provider evidence determines whether cleanup is
verified. The execution brief carries these constraints into its probes.

The initial alternatives are the existing host constructor, one exact-profile
composer, a grouped bundle, and per-descriptor factories. Start the experiment
with one exact-profile composer and a small ownership tree. Keep the current
constructor as the control. Component factories need evidence of repeated
independent ownership across profiles; package discovery, HMR, config overlays,
and a general service locator remain outside the first experiment.

## 1f Historical verification

The original source review pinned Harness at `47f9438` and the Cordis paper at
`948a07b`, including its authors, assumptions, and provenance limits. The
focused Catalog, profile, and Pi A2 host suites passed 102 tests in 2.12 seconds:

```sh
uv run --frozen pytest -q \
  tests/petrus/agenticus/catalog/test_resolution.py \
  tests/petrus/agenticus/runtime/test_profiles.py \
  tests/petrus/agenticus/runtime/test_pi_a2_host.py
```

Those results supported the comparison baseline. They did not execute a mount
experiment or prove a new capability. This closure preserves the source
conclusions and one execution plan without rerunning the historical research.
