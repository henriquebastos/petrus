---
status: Decided
raised: 2026-08-01
decided: 2026-08-01
deciders:
  - henrique (Navigator)
supersedes:
related:
  - CV10
  - docs/project/decisions/records/2026-07-29T2316Z-petrus-is-project-over-impetus-motus-and-arx.md
  - docs/project/decisions/records/2026-08-01T0100Z-petrus-python-namespace-owns-impetus-and-motus.md
---

# CV10 execution contracts remain private while provider axes qualify independently

## Question

What should Petrus ratify after multiple agent runtimes satisfy one integration contract
and local process, Docker, and an E2B-shaped VM adapter satisfy one execution
lifecycle, while live orb/VM evidence remains incomplete?

## Decision

CV10 keeps the execution-environment, attachment, command, artifact, and
Timeline contracts private. Their physical location under
`petrus.motus._execution` expresses the settled Motus ownership inside the one
`petrus` distribution, while the leading underscore and lack of exports keep
the provisional protocol private. CV7 owns support, version, artifact, and
release qualification rather than namespace topology.

Agent and environment substitution qualify as independent axes. The
application-local typed `AgentRunner` is enough for the current proof: Amp and
Codex are separate agent backends; local process and Docker are separate live
environment implementations; E2B is a deterministic VM adapter pending live
acceptance. A future provider-specific capability may remain explicit instead
of inflating one universal Agent or Session API.

Codex's OpenAI/OpenRouter selection is **reasoner transport inside the Codex
backend**, not another agent backend. Where Docker or a VM already supplies the
outer execution boundary, Codex may use its documented externally-sandboxed
mode rather than attempt unsupported nested sandboxing. That delegation is
permitted only when the selected environment advertises container or VM
isolation, remains overrideable, receives no GitHub credentials, and is not
described as hostile-code proof.

The host remains the sole GitHub Effect Gateway. Model-provider credentials may
enter only the selected agent attachment; GitHub credentials and publication
authority never do. Operational Timeline data remains bounded, redacted,
best-effort evidence and never becomes input to execution, replay, fences,
projection, or canonical History.

## Rationale

Two agent implementations and two live environment implementations now show
that the axes are real, but the required remote lease category is not yet
truthfully complete. Publishing a generic Motus API now would freeze names and
capabilities around Docker and a fake-SDK VM proof before an independently
leased orb and a live VM pressure-test recovery behavior. Keeping the seams
private preserves the earned architecture without converting provisional
implementation into doctrine.

OpenRouter changes who serves the model request, not who owns the Codex loop,
tools, result protocol, or continuation behavior. Counting it as another agent
would make the evidence look broader than it is. Conversely, running Codex
inside Docker is valid agent/environment composition only if nested sandbox
delegation is explicit and the outer territory remains the security boundary.

## Options Considered

- **Promote the current environment protocol publicly after local + Docker.**
  Rejected until the remote VM/orb lifecycle supplies materially different
  recovery pressure and a separate support/API ruling accepts the surface.
- **Treat OpenRouter as the second agent backend.** Rejected; Codex CLI still
  owns the agent loop and contract.
- **Require Codex's inner workspace sandbox inside every territory.** Rejected
  because nested sandboxing prevented tool execution in Docker and duplicates
  the selected outer territory's role.
- **Use `--dangerously-bypass-approvals-and-sandbox` on local execution too.**
  Rejected. Local Codex retains its own workspace sandbox; delegation is
  capability-gated to container/VM providers.
- **Put Timeline events in canonical History.** Rejected because operational
  evidence is lossy, provider-shaped, redactable, and retention-bounded.

## Consequences

- `petrus.motus._execution` remains private and unexported.
- Agent/provider capability differences remain adapter-local or explicit.
- A future public Motus contract needs live remote-provider evidence plus a
  separate acceptance/support ruling.
- Host-owned GitHub authority and fail-closed effect/result fencing remain
  invariant across every provider pairing.
- Arx may later consume Timeline data, but neither Arx nor Timeline can become
  semantic execution authority.

## Review Trigger

Revisit after a live VM agent run and a truthful independently leased orb (or a
second materially different remote environment) complete lifecycle and recovery
acceptance, or when CV7 must qualify a public Motus support/version surface.
