# Release Management

Release management is the Delivery handoff from completed work to a named version, channel, package, deployment, or public communication.

Ariad does not require every project to publish software releases. It does require the Driver to notice when completed Delivery has created a release boundary.

## Release boundary

A release boundary appears when completed work should be named beyond the local project history.

Common signals:

- a Delivery Story closes and produces a coherent capability;
- a Value / CV closes and reaches a major value boundary;
- a User Story, Technical Story, or maintenance fix should be shipped independently;
- public documentation, runtime behavior, package behavior, or operational reliability changed;
- users or contributors need to understand what changed without reading commits.

Release management should not begin automatically. The Driver should name the possible boundary and ask the Navigator whether to enter release work.

## Release intent

Release intent may be known at the start or emerge after work closes.

```text
Known release intent
  the version, channel, and release scope are already part of the plan

Emergent release intent
  delivery reveals that a User Story, Technical Story, Delivery Story, or Value now deserves a release boundary
```

The Driver should surface release intent during planning when known, and during Delivery Story or Value collapse when emergent.

## Default versioning policy

Ariad's default versioning policy follows the roadmap taxonomy, but projects may override it.

```text
MAJOR
  a Value / CV is completed and release-ready

MINOR
  a Delivery Story is completed and released without closing a Value / CV

PATCH
  a User Story, Technical Story, maintenance fix, or small correction is released independently
```

The version number says what level of work collapsed into a release. It does not encode which Value, Delivery Story, User Story, or Technical Story produced it. That identity belongs in the release note.

## Release note

A release note is not a changelog. It is the narrative record of a closed arc of work.

A good release note makes clear:

- where the work started;
- what changed;
- what decisions shaped the release;
- what was consciously excluded;
- what the release means now;
- what horizon is visible from here.

The release note is a collapse. It turns a set of stories, decisions, validations, and exclusions into public narrativity.

## Release candidate

A release candidate is a completed delivery arc that appears ready to release but still needs release-specific verification.

Release candidate checks may include:

- version or package metadata;
- release note exists and links correctly;
- CI or project verification passes;
- smoke validation route passes;
- controlled operation evidence, such as runtime health, backup, migration, release doctor, or update preflight;
- deployment or channel promotion plan is clear;
- rollback or recovery route is known;
- Navigator accepts the release boundary.

## Channels and promotion

Projects with multiple channels should make the channel policy explicit.

A common model:

```text
integration channel
  where completed work is merged and dogfooded

release channel
  where user-facing releases are published or promoted
```

A push, merge, or commit is not necessarily a release. A release happens when the project intentionally advances the release boundary: version, release note, validation, tag, package, deployment, channel promotion, or equivalent project-specific act.

## Handoff from Delivery

When a User Story or Technical Story closes, the Driver asks whether it closes the parent Delivery Story or creates an independent patch boundary.

When a Delivery Story closes, the Driver asks whether it suggests release management.

When a Value / CV closes, the Driver asks whether it creates a major release or public value milestone.

The handoff should be explicit:

```text
Delivery Story closed
  completed stories: 3/3
  emergent capability: mobile users can recover from address validation failures
  suggested next process: release management
  likely release boundary: minor
```

The Navigator decides whether to enter release management now, defer it, or record that no release is needed.
