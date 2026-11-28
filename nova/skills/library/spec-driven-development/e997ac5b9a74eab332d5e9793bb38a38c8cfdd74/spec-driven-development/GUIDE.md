# Spec-Driven Development

One sentence: This skill makes NOVA better at writing structured specifications before any implementation begins, ensuring requirements are concrete, testable, and human-approved before work proceeds.

## When to use

Use this skill when starting a new project, feature, or significant change with no existing specification; when drafting a PRD or requirements document with objectives and scope; when requirements are unclear, ambiguous, or only exist as a vague idea; when a single requirement spans several independently testable capabilities and needs decomposing into a capability map of modules before specifying; or when evolving a shipped spec — scoping a V1, deferring ideas to a V2 backlog, or writing a follow-up spec for a change to an existing feature.

Do not use it for single-line fixes, typo corrections, or changes where requirements are unambiguous and self-contained.

## Workflow

1. **Scope check.** Determine if the request bundles several independently testable capabilities. If yes, propose a capability map before writing any spec: a module table with module id, responsibility, and dependencies, plus a build order. Use kebab-case module ids chosen once and never renamed mid-initiative. Ensure dependency direction has no cycles; if two modules each need the other, they are one module. Get the human to review module boundaries, dependency direction, and build order before any module spec is written. Save the approved map as `spec/capability-map.md` and each module spec alongside it in `spec/`, named by module id (for example `spec/SPEC-identity.md`). Then recurse through the remaining steps for each module in dependency order.

2. **Surface assumptions.** Before writing spec content, list what you are assuming (platform, auth mechanism, database, browser targets, etc.) and ask the human to correct them. Never silently fill in ambiguous requirements.

3. **Write the spec.** Create a document covering these six core areas:
   - **Objective:** What we are building and why, who the user is, and what success looks like.

## Quality bar

- [ ] The spec covers all six core areas (a delta spec covers at minimum objective, success criteria, and boundary deltas, inheriting the rest from the original).
- [ ] The human has reviewed and approved the spec.
- [ ] The turn ended after saving the spec; approval came in a later turn.
- [ ] Success criteria are specific and testable, not vague adjectives.
- [ ] Boundaries (Always / Ask first / Never) are defined.
- [ ] The spec is saved to a file in the repository.
- [ ] Ideas cut from this version are captured under Out of Scope (Deferred), not silently dropped or included.
- [ ] If this is a change to a shipped spec, it is a delta spec referencing the original, not a rewrite of it.
- [ ] If the request bundles several independently testable capabilities, a capability map (module ids, dependency direction, build order) was approved before any module spec was written.
- [ ] Every module spec traces to a module id in the approved map.

## Pitfalls

- Starting to write code without any written requirements.
- Asking "should I just start building?" before clarifying what "done" means.
- Implementing features not mentioned in any spec or task list.
- Making architectural decisions without documenting them.
- Skipping the spec because "it's obvious what to build."
- Letting V1 requirements grow mid-implementation as new ideas get written straight into the spec.
- Changing a shipped feature with no spec for the change because "the feature already has one."
- Writing the spec and starting the plan or code in the same turn.
- One spec whose requirements span several independently testable capabilities without an approved capability map.
- Deciding module boundaries or build order implicitly during implementation instead of up front.