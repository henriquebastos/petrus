---
status: Decided
raised: 2026-07-19
decided: 2026-07-19
deciders:
  - Navigator
supersedes:
related:
  - ES-025
---

# Driver QA is the routine User Story acceptance surface

## Question

Must the Navigator manually execute a validation route before every User Story can move beyond its Behavior Checkpoint?

## Decision

No. The Driver owns complete User Story QA and submits a passing, evidence-bearing Experience Report. The Navigator can approve or request changes by reading that report. Manual Navigator inspection is optional and remains useful for UX exploration, product insight, or additional confidence; it is not routine QA or a prerequisite for approval.

Technical Stories remain distinct: complete internal technical evidence may verify and close a Technical Story without a User Story Experience Report.

## Rationale

Making the Navigator repeat routine QA increases cognitive load and turns human availability into global delivery WIP. The Driver can execute tests, operate the behavior, capture screenshots or videos, and organize evidence before asking for product judgment. A concise report preserves Navigator authority over acceptance while moving evidence collection to the role with the tools and execution context.

## Options Considered

- **Mandatory Navigator validation route:** rejected as routine policy because it assigns QA back to the Navigator and serializes progress on human availability.
- **Fully automatic User Story closure:** rejected because passing QA evidence does not replace Navigator product judgment.
- **Evidence-first approval:** selected; Driver QA must pass, then Navigator approves or requests changes from the report, with inspection optional.

## Consequences

- User Story Behavior Checkpoints require a concise summary, acceptance results, referenced evidence, relevant screenshots/videos, known issues, and risks.
- A report with failed acceptance behavior does not reach approval.
- The Navigator may request rework without manually reproducing the behavior.
- A checkpoint parks only the affected story passage; unrelated parents continue under their own local WIP controls.
- Optional validation routes should be framed as inspection aids, not delegated routine QA.

## Review Trigger

Revisit if reports repeatedly miss defects that mandatory manual inspection would have caught, or if report preparation costs more than the Navigator work it removes.
