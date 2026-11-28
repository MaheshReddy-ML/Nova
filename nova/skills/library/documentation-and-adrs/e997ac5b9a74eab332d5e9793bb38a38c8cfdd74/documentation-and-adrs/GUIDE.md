# Documentation and ADRs

Records decisions and documentation, and detects when documentation has drifted from the code it describes.

## When to use

Use when documenting an architecture decision (ADR) or the reasoning behind a design choice, changing public APIs, shipping features, checking whether docs are stale or out of sync with the code they describe, determining which module docs are still accurate, or setting up a check so docs cannot silently go out of date again.

## Workflow

1. **Inspect for an existing convention.** Use `read_website` on the repository documentation or `deep_research` to find existing ADRs, project instructions, or ADR-related configuration (for example an `.adr-dir` file). Match the existing location, format, numbering, naming, and section headings. If evidence conflicts, surface the conflict rather than silently introducing another scheme.
2. **Decide whether to document.** Write an ADR for significant architectural decisions: choosing a framework, library, or major dependency; designing a data model or schema; selecting an authentication strategy; deciding an API architecture; choosing build tools, hosting, or infrastructure; or any decision expensive to reverse. Do not document obvious code, restate what code already says, or write docs for throwaway prototypes.
3. **Draft the ADR.** Use the default template unless a project convention overrides it:

   - **Status:** Proposed | Accepted | Superseded by ADR-XXX | Deprecated
   - **Date:** ISO date
   - **Context:** problem, requirements, constraints
   - **Decision:** the chosen approach
   - **Alternatives Considered:** pros, cons, and rejection rationale for each
   - **Consequences:** what changes, including risks and team impact

   Store ADRs in `docs/decisions/` with sequential numbering unless the project uses another location. Never delete old ADRs; when a decision changes, write a new ADR that references and supersedes the old one.
4. **Document APIs.** For public APIs, document parameters, return values, errors, and examples inline with types. For REST APIs, provide OpenAPI/Swagger specifications.
5. **Write inline comments for why, not what.** Explain non-obvious intent, known gotchas, and link to ADRs. Do not comment self-explanatory code, leave TODOs for things you should do now, or leave commented-out code.
6. **Maintain the README.** Cover project description, quick start, commands, architecture overview with links to ADRs, and contributing guidelines.

## Quality bar

- [ ] ADRs exist for all significant architectural decisions
- [ ] README covers quick start, commands, and architecture overview
- [ ] API functions have parameter, return, and error documentation
- [ ] Known gotchas are documented inline where they matter
- [ ] No commented-out code remains
- [ ] Rules files (CLAUDE.md etc.) are current and accurate
- [ ] Prose edits preserve source details, decision trade-offs, and qualifiers without adding unsupported guarantees
- [ ] Change logs were appended to rather than rewritten
- [ ] A doc whose staleness could not be determined is reported as "can't tell", not as current

## Pitfalls

- **Code is self-documenting:** Code shows what, not why, what alternatives were rejected, or what constraints apply.
- **Waiting for the API to stabilize:** APIs stabilize faster when documented; the doc is the first test of the design.
- **Rewriting the changelog:** Git holds the old text; the log holds the reasons. Rewriting destroys the only copy of the reasoning.
- **Assuming a doc is current:** Never report a doc as current when commit order between doc and code cannot be determined.
- **Commenting the what:** Comments on what get outdated; only document why and known gotchas.
- **Ignoring existing conventions:** Match the project's ADR location, format, and numbering before applying defaults.