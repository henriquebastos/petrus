# Execution territory

The temporary, isolated place where Motus runs commands: one
provider-materialized environment — a local temp directory, Docker
container, E2B VM, or Gondolin microVM — identified by an environment
lease, holding at most one workspace attachment and one active command
at a time. One independently leased territory belongs to one Episode or
host operation, never to each Activity attempt.

- Use when: naming the leased environment behind command execution;
  bare "territory" is acceptable where the Motus context is clear.
- Do not use for: a Thread, an Episode, or the workspace itself — a
  territory hosts a workspace; Threads and Episodes own or attach to
  territories.
- Related: [Episode](episode.md), [Gondolin](gondolin.md),
  [Hands](hands.md), [Thread](thread.md)
- Detail: [episode-owns-independent-execution-territory decision](../decisions/records/2026-08-09T1400Z-episode-owns-independent-execution-territory.md)
