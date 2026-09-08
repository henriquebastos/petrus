# 1 Read the Petrus documentation

Start with the [runnable example](../README.md#1b-run-a-small-net) to see a net
move a token. The documentation then separates using the runtime, contributing
to it, and understanding how its design developed.

## 1a Using Petrus

| Question | Owner |
| --- | --- |
| How does the runtime fit together? | [Specification overview](../spec/OVERVIEW.md) |
| How do I use the Python APIs and optional providers? | [Runtime guide](runtime-guide.md) |
| What does a domain term mean? | [Glossary](project/glossary/index.md) |
| What must an implementation or external tool preserve? | [Specification index](../spec/README.md) |
| How do I test failures and replay? | [Deterministic simulation testing](process/deterministic-simulation-testing.md) |

## 1b Contributing

Read the [project briefing](project/briefing.md) for current direction, then
the [development guide](process/development-guide.md) for commands and the
contribution process. [Engineering conventions](process/engineering-conventions.md)
hold implementation practice; [product principles](product/principles.md)
explain the constraints behind design choices.

Petrus uses Ariad to keep project knowledge discoverable when people and
coding agents work together. The human chooses direction and trade-offs;
the agent implements, verifies, and records the work. You can use Petrus
without adopting Ariad. Contributors can start at the
[local Ariad guide](ariad/index.md).

## 1c Reading the history

Current specifications and glossary entries describe the present contract.
Older records explain how it developed. Read their dates, status, and later
review notes before treating a historical statement as current guidance.

| Record | What it preserves |
| --- | --- |
| [Decisions](project/decisions/index.md) | Accepted choices, alternatives, and supersession |
| [Roadmap](project/roadmap/index.md) | Delivery intent, status, and acceptance evidence |
| [Explorations](project/exploration/index.md) | Questions, experiments, and the disposition of candidates |
| [Debt](project/debt/index.md) | Known limitations and conditions for revisiting them |
| [Worklog](process/worklog/index.md) | Dated milestones and the validation performed at the time |

Identifiers such as `CV20.DS3.TS2` locate a Value, Delivery Story, and Technical
Story. `ES-062` identifies an Exploratory Story. These are stable record
identifiers; they are not software versions or a required reading sequence.

Early records mention Hermes, a predecessor design notebook, or `CONTEXT.md`,
the glossary's former location. Some exploratory references were never retained
in this source tree. The exploration index explains the reserved identifiers;
missing notebooks are not setup prerequisites. Retained decisions and specs
must carry the rationale needed to understand the current project.

Application names in acceptance reports identify the systems used to exercise
Petrus. An application-specific demonstration is evidence for its stated
boundary, not a general support claim. Likewise, an old passing test count
describes that run; it does not certify the current checkout.

## 1d Maintaining project memory

Keep current behavior in its specification or usage guide, accepted terminology
in the glossary, and work status in its owning record. Link to those owners
instead of copying their contents into every overview. Preserve the reasons for
consequential choices in decisions and meaningful milestones in the worklog.

When a document becomes stale, update it through an ordinary commit. Git
retains the previous text. Historical records can receive dated corrections or
supersession links without pretending that the earlier conclusion never existed.
The installed Ariad [Memory Closure protocol](../.agents/skills/using-ariad/references/method/memory-closure.md)
describes this process in detail.
