---
status: Decided
raised: 2026-07-16
decided: 2026-07-23
deciders:
  - henrique (Navigator)
supersedes:
  - DEC-019's unresolved proposal to commission a CrewAI economical-equivalent pass now
related:
  - docs/product/principles.md
---

# Shipping and adoption outrank premature monetization

## Question

Should Impetus commission an economical pass over CrewAI's enterprise map now,
dividing capabilities the architecture makes structurally free from genuine
operational services that could support a business, or leave the analysis as
raw prior art until a concrete public-product or hosted-service moment?

## Decision

Keep both CrewAI analyses as raw prior art and defer the economical pass until
Impetus reaches a concrete public-product or hosted-service decision.

The governing priority is to build, publish, and improve a genuinely useful
open tool that develops broad real-world adoption. A healthy enterprise
service would be welcome if it funds the tool's development and helps people
use it. It must not, however, distract the project into premature business
operation, delay shipping, or make core utility depend on enterprise gating.

If the actual choice were between a widely useful Impetus that earns nothing
and an enterprise effort that prevents the tool from shipping or being used,
choose the widely useful tool. Monetization serves the tool and its community;
the tool does not exist merely to bootstrap a business from an idea.

Do not commission the CrewAI-derived engineering questions merely because the
map exposed them. Connector catalogs, onboarding/history UX, Activity
cancellation, budget conventions, and authoring projections remain with their
concrete Impetus owners and should advance only when real work needs them.

## Rationale

CrewAI supplies encouraging evidence that an open-source runtime can coexist
with paid enterprise operations. Its map also exposes a plausible durable
boundary: history-native capabilities such as traces, durable waits, triggers,
and replay belong naturally to a fully capable open tool, while managed
compute, credential custody, hosted connectors, registries, organizational
controls, and fleet operation carry genuine service costs.

That distinction is useful evidence but not yet an Impetus business. There is
no hosted product, customer segment, measured operational cost, or imminent
packaging choice to resolve. Turning the map into strategy now would risk
optimizing an imagined enterprise surface before the tool and its community
exist. The current product principles already protect local operation,
canonical history, ordinary code seams, and a fully useful deterministic core.

## Options Considered

- **Commission the economical pass now.** Rejected for now: it would define a
  commercial boundary without a concrete service or product decision.
- **Keep the analyses raw until a public/product moment — chosen.** This
  preserves the market evidence while keeping attention on shipping and
  adoption.
- **Route selected engineering questions now while deferring monetization.**
  Rejected as a blanket action: cancellation and connector semantics already
  have bounded owners, and ES-011 remains intentionally paused. Route each
  question only when a concrete story encounters it.

## Consequences

- No economical-equivalent pass, pricing model, hosted service, or enterprise
  feature boundary is commissioned now.
- The two CrewAI files remain `status: raw` prior art.
- Broad usefulness, publication, and community adoption take precedence over
  speculative enterprise work.
- Future paid services remain welcome when they concretely improve the tool,
  fund its development, or help users operate it without withholding its core
  utility.
- ES-011 remains Paused; Activity cancellation remains later semantic work;
  and ES-013's connector idioms retain their existing observed-not-canonical
  status.

## Review Trigger

Revisit when Impetus approaches public release, a hosted or managed offering
has a concrete operator and user, users request operational help that carries
real recurring cost, or a proposed enterprise boundary would gate capability
that the open architecture already provides naturally.
