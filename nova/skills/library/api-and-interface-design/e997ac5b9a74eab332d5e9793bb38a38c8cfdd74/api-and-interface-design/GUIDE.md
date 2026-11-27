# api-and-interface-design

One sentence: Design stable, well-documented interfaces that are hard to misuse, making the right thing easy and the wrong thing hard across REST APIs, GraphQL schemas, module boundaries, and component contracts.

## When to use

- Designing new API endpoints or GraphQL schemas
- Defining module boundaries or contracts between teams
- Creating component prop interfaces or database schemas that inform API shape
- Changing existing public interfaces or adding fields
- Establishing error semantics, pagination, or filtering patterns

## Workflow (numbered steps adapted to NOVA's tools)

1. **Define the contract first** — Draft typed input/output schemas (e.g., TypeScript interfaces) before writing implementation. The contract IS the documentation.
2. **Establish consistent error semantics** — Choose one error pattern (structured `{ error: { code, message, details } }` with HTTP status mapping) and apply it to every endpoint.
3. **Validate at system boundaries only** — Accept external input (user data, third-party API responses, environment variables) and validate shape/content immediately at the edge. Never validate between internal functions that share type contracts.
4. **Prefer addition over modification** — Add new optional fields rather than changing or removing existing ones. Extend interfaces without breaking consumers (One-Version Rule).
5. **Apply predictable naming conventions** — Use plural nouns for REST endpoints, camelCase for query params and response fields, `is/has/can` prefixes for booleans, UPPER_SNAKE for enum values.
6. **Design idempotency from the start** — Accept an `Idempotency-Key` header, derive the key from immutable identifiers (e.g., `charge:v1:${orderId}`), claim it atomically via a unique constraint, and guard payload reuse. Retain keys longer than the longest retry path, including dead-letter queue replay.
7. **Review against the quality bar and red flags** — Check all checklists before marking complete.

## Quality bar (checklist)

- [ ] Every endpoint has typed input and output schemas
- [ ] Error responses follow a single consistent format (`{ error: { code, message, details } }`)
- [ ] Validation happens at system boundaries only (never between internal functions)
- [ ] List endpoints support pagination with `totalItems` and `totalPages`
- [ ] New fields are additive and optional (backward compatible)
- [ ] Naming follows consistent conventions across all endpoints
- [ ] API documentation or types are committed alongside the implementation
- [ ] State-changing endpoints either honour an idempotency key or are documented as unsafe to retry
- [ ] The key is claimed in one atomic operation, guarded by a unique constraint
- [ ] A reused key with a different payload fails loudly (422) rather than replaying the wrong response
- [ ] In-flight duplicate response is a deliberate choice (409, wait, or 202) rather than undefined behavior
- [ ] Key retention outlives the longest retry path, including dead-letter replay

## Pitfalls

- Endpoints returning different shapes depending on conditions
- Inconsistent error formats across endpoints
- Validation scattered throughout internal code instead of at boundaries
- Breaking changes to existing fields (type changes, removals)
- List endpoints without pagination
- Verbs in REST URLs (`/api/createTask`, `/api/getUsers`)
- Third-party API responses used without validation or sanitization
- A `SELECT` followed by `INSERT` for idempotency keys (TOCTOU race)
- Idempotency key derived from UUID, timestamp, or anything regenerated per attempt
- Same key accepted with a different request body, silently returning the first response
- Key retention window shorter than the longest retry path (including DLQ replay)
- Mixing error strategies (some throw, some return null, some return `{ error }`)
- Assuming internal APIs don't need contracts