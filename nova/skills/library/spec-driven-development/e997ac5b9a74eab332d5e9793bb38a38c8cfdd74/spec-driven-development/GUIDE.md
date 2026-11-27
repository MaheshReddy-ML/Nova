# Spec Driven Development
## Spec-Driven Development
## Overview
## When to Use
- Starting a new project or feature
- Requirements are ambiguous or incomplete
- The change touches multiple files or modules
- You're about to make an architectural decision
- The task would take more than 30 minutes to implement
## The Gated Workflow
## Phase 0: Scope Check
- The requirement names distinct capabilities with their own consumers or data (e.g. identity, billing, notifications, reporting)
- Acceptance criteria cluster into groups that could ship and be verified separately
- One capability could be cut or replaced without rewriting the others' requirements
- **Stable module ids.** Kebab-case, chosen once, never renamed mid-initiative. Specs, plans, and downstream commands select work by these ids instead of guessing which spec is active.
- **Dependency direction, no cycles.** Arrows point one way. If two modules each need the other, they are one module.
- **Interfaces live at the boundary.** The map records that `billing` depends on `identity`; the contract between them belongs in the provider module's spec (see `api-and-interface-design` for designing it).
## Phase 1: Specify
1. **Objective** — What are we building and why? Who is the user? What does success look like?
2. **Commands** — Full executable commands with flags, not just tool names.
3. **Project Structure** — Where source code lives, where tests go, where docs belong.
4. **Code Style** — One real code snippet showing your style beats three paragraphs describing it. Include naming conventions, formatting rules, and examples of good output.
5. **Testing Strategy** — What framework, where tests live, coverage expectations, which test levels for which concerns.
- **Always do:** Run tests before commits, follow naming conventions, validate inputs
- **Ask first:** Database schema changes, adding dependencies, changing CI config
- **Never do:** Commit secrets, edit vendor directories, remove failing tests without approval
1. Summarize it and list any Open Questions.
2. Ask the human to approve it or request changes.
3. **STOP YOUR TURN IMMEDIATELY.** Do NOT start Phase 2, invoke `planning-and-task-breakdown`, or write code in this turn. Planning starts only after the human approves the spec in a later turn.
## Phase 2: Plan
1. Identify the major components and their dependencies
2. Determine the implementation order (what must be built first)
3. Note risks and mitigation strategies
4. Identify what can be built in parallel vs. what must be sequential
5. Define verification checkpoints between phases
## Phase 3: Tasks
- Each task should be completable in a single focused session
- Each task has explicit acceptance criteria
- Each task includes a verification step (test, build, manual check)
- Tasks are ordered by dependency, not by perceived importance
- No task should require changing more than ~5 files
## Phase 4: Implement
## Keeping the Spec Alive
- **Update when decisions change** — If you discover the data model needs to change, update the spec first, then implement.
- **Update when scope changes** — Features added or cut should be reflected in the spec.
- **Commit the spec** — The spec belongs in version control alongside the code.