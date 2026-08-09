# Explicit Policies

Ariad borrows from Kanban the idea that important operating rules should be visible enough to guide decisions before the pressure of the moment arrives.

An explicit policy is not a bureaucratic rule. It is a written answer to a recurring question that would otherwise be improvised by the Driver in each session.

Explicit policies belong in the layer that has the right authority:

- method-wide policies belong in Ariad;
- repository policies belong in the project contract;
- local operating preferences belong in Navigator preferences or workspace overlays.

When a policy differs by project, the project contract wins. Ariad provides the default posture that protects coherence when no better local answer exists.

## Coherent update policy

Updating a software system is not automatically a small maintenance action.

Sometimes an update is trivial: a documentation correction, a dependency bump with no runtime effect, or a local template comparison that writes nothing. Sometimes it is operational: it touches the runtime, migrations, extensions, local data, credentials, installation layout, or the method a future Driver will follow. Sometimes it is product work: it changes behavior that users can see or depend on.

Ariad treats an update as a story when the update can change the project's operational state.

Pulling latest code is not a policy. It is only a mechanism. A coherent update names the state before the change, the path through the change, and the evidence that the system still works after the change.

## Update classes

A **trivial update** is low-risk and easy to inspect. It does not affect runtime behavior, local data, migrations, external services, user-visible behavior, or the instructions future agents rely on. Trivial updates may use compressed checkpoints when the Navigator or project allows it.

An **operational update** changes how the system is installed, started, migrated, configured, extended, or recovered. Examples include runtime updates, database migrations, extension installation, local environment changes, generated skill updates, release upgrades, and template adoption that changes the agent's operating surface.

A **product update** changes behavior for the people who use the system. It follows the normal Delivery Story lifecycle and needs product validation, not only technical checks.

When in doubt, treat the update as operational. The cost of naming the route is smaller than the cost of recovering from an invisible state change.

## Minimum route for operational updates

For an operational update, the Driver should make these things visible before treating the work as done:

- current state: version, branch, dirty tree, installed components, database path, relevant configuration, or whatever state the update depends on;
- intended target: the version, commit, release, template state, or installation state being moved toward;
- plan: what will change and what will not change;
- backup or recovery route: required when local data, migrations, generated runtime files, or installed extension state are at risk;
- execution: the smallest safe change that advances the update;
- validation: automated checks, health checks, command output, manual inspection route, or user-visible verification appropriate to the update class;
- rollback or repair route: how to recover if the update fails or leaves the system incoherent;
- history: a record of why the update happened and what evidence showed it was safe enough to accept.

This is not a checklist for ceremony. It is the minimum memory surface needed for future sessions to understand what changed.

## Backup and recovery

If an update can affect local data, the Driver should not proceed without naming the backup or recovery route.

For database-backed systems, this usually means backing up the database before migrations or destructive changes. For extension systems, it may mean preserving the previous installed extension directory or making reinstall instructions explicit. For generated runtime surfaces, it may mean knowing how to regenerate them from source.

A rollback route does not need to be perfect. But the absence of any recovery route is a fact the Navigator should see before the update proceeds.

## Validation after updates

Operational updates need validation that matches the risk.

A successful command exit is useful, but it is not always enough. If the update changes a runtime, the Driver should run a runtime health check. If it changes migrations, the Driver should verify migration state. If it changes an extension, the Driver should verify installation, loading, migrations, and at least one representative command. If it changes templates or method docs, the Driver should verify documentation builds and update or drift reports.

The validation route should be concrete enough that the Navigator can repeat or inspect it.

## Follow-up work

Updates often reveal adjacent work: stale files, missing status commands, unclear installation docs, version drift, or release process gaps.

Ariad's policy is to capture adjacent work instead of silently expanding the update. If the adjacent work blocks correctness or recovery, it belongs in the current story. If it improves future coherence but does not block the update, record it as follow-up in the appropriate journey, roadmap, worklog, or issue tracker.

## Relationship to Driver and Navigator

The Driver owns operational visibility. It should surface the state, plan, validation, and recovery route.

The Navigator owns acceptance. It decides whether the risk is acceptable, whether the recovery route is sufficient, and whether the update should proceed now.

A coherent update preserves this relationship. The agent may execute the mechanism, but it should not silently own the risk.
