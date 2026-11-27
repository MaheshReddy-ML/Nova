# Documentation And Adrs
## Documentation and ADRs
## Overview
## When to Use
- Making a significant architectural decision
- Choosing between competing approaches
- Adding or changing a public API
- Shipping a feature that changes user-facing behavior
- Onboarding new team members (or agents) to the project
- When you find yourself explaining the same thing repeatedly
## Architecture Decision Records (ADRs)
## When to Write an ADR
- Choosing a framework, library, or major dependency
- Designing a data model or database schema
- Selecting an authentication strategy
- Deciding on an API architecture (REST vs. GraphQL vs. tRPC)
- Choosing between build tools, hosting platforms, or infrastructure
- Any decision that would be expensive to reverse
## Match the existing convention first
- **Location and format** — e.g. `docs/adr/*.md`, `Documentation/Decisions/*.rst`, a MADR layout, or an `adr-tools` setup. Match the existing directory, file extension, and markup (Markdown vs reStructuredText).
- **Numbering and naming** — continue the existing sequence and filename pattern (`ADR-004-Title.rst`, `0004-title.md`, …); don't restart at 001 or introduce a second scheme.
- **Section headings** — reuse the project's heading set rather than imposing this template's.
## ADR Template
## ADR Lifecycle
- **Don't delete old ADRs.** They capture historical context.
- When a decision changes, write a new ADR that references and supersedes the old one.
## Inline Documentation
## When to Comment
## When NOT to Comment
## Document Known Gotchas
## API Documentation
## Inline with Types (Preferred for TypeScript)
## OpenAPI / Swagger for REST APIs
## README Structure
## Changelog Maintenance
## Documentation for Agents
- **CLAUDE.md / rules files** — Document project conventions so agents follow them
- **Spec files** — Keep specs updated so agents build the right thing
- **ADRs** — Help agents understand why past decisions were made (prevents re-deciding)
- **Inline gotchas** — Prevent agents from falling into known traps
## Prose Review
1. Mark the details that must survive the edit: names, numbers and units, commands, paths, links, conditions, trade-offs, and uncertainty. Check them against the available code and decision context; flag anything you cannot substantiate.
2. Replace stock introductions, promotional adjectives, and repeated summaries with the concrete information the reader needs. Do not replace an unsupported claim with an invented example or a stronger guarantee. Keep necessary technical repetition and the project's established terminology.
3. Compare the edited document with the original and its sources. Restore any lost qualifier or caveat, verify command and code examples still work as documented, and explain any unresolved factual question rather than polishing it away.
## Documentation Drift
## Common Rationalizations
## Red Flags
- Architectural decisions with no written rationale
- Public APIs with no documentation or types
- README that doesn't explain how to run the project
- Commented-out code instead of deletion
- TODO comments that have been there for weeks
- No ADRs in a project with significant architectural choices
- Documentation that restates the code instead of explaining intent