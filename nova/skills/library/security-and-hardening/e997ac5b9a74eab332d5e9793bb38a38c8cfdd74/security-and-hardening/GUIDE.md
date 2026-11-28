# Security and Hardening

One sentence: makes NOVA better at auditing and hardening web applications against vulnerabilities, covering input handling, authentication, data storage, external integrations, dependencies, and privacy compliance.

## When to use

Use when auditing an input handler for vulnerabilities, handling user input, authentication, data storage, or external integrations, checking a login flow against the OWASP Top Ten, building any feature that accepts untrusted data or manages sessions, auditing dependencies for known vulnerabilities, triaging package-manager audit findings, assessing supply-chain risk, or when personal data or privacy compliance (GDPR, CCPA) is involved.

## Workflow

1. Threat model first. Spend five minutes thinking like an attacker: map trust boundaries where untrusted data enters (HTTP requests, forms, file uploads, webhooks, third-party APIs, LLM output), name the assets worth stealing, run STRIDE (spoofing, tampering, repudiation, information disclosure, denial of service, elevation of privilege) over each boundary, and write abuse cases next to use cases. If you cannot name the trust boundaries, you are not ready to secure it.
2. Apply the always-do controls with no exceptions: validate all external input at the boundary; parameterize all database queries; encode output to prevent XSS; use HTTPS for all external communication; hash passwords with bcrypt, scrypt, or argon2; set security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options); use httpOnly, secure, sameSite cookies for sessions; run the native package-manager audit against the committed lockfile before every release.

## Quality bar

- Threat model completed before controls are applied
- Every external input validated at the system boundary
- All database queries parameterized; no string concatenation of user input into SQL, NoSQL, or shell commands
- Authorization checked on every request, not just authentication
- Passwords hashed with bcrypt (12+ rounds), scrypt, or argon2; no plaintext storage
- Session cookies httpOnly, secure, sameSite lax or strict, with bounded maxAge
- Security headers present on every response; CSP starts from default-src 'self'
- CORS restricted to explicit origin list; no wildcard with credentials
- Error responses generic; internal details logged server-side only
- Native package-manager audit run against committed lockfile before release; no forced remediation
- Secrets sourced from environment only; none in source code or git history
- Rate limiting on auth endpoints (~10 attempts per 15 minutes), shared store for multiple instances
- Server-side URL fetches allowlisted; private/reserved addresses rejected

## Pitfalls

- Treating security as a phase rather than a constraint on every line touching user data or external systems
- Relying on client-side validation as a security boundary
- Assuming internal tools do not need security
- Believing the framework handles security automatically
- Using in-memory rate limiters across multiple instances or serverless environments
- Applying npm audit fix --force or equivalent automatically, which can cross declared dependency ranges
- Assuming an audit passed means a dependency is safe; audits match known advisories only, not new malicious or typosquatted packages
- Collecting personal data with no stated purpose, retention limit, or deletion path
- Handling deletion requests by flipping a flag while data lingers in stores, caches, search indexes, and backups
- Placing secrets, PII, or full system prompts inside LLM context windows
- Trusting path shape checks alone for destructive operations without resolving symlinks and verifying authorization
- Skipping human approval for auth changes, new sensitive data categories, or external integrations