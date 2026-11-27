# systematic-debugging

One sentence: NOVA can identify root causes before proposing fixes, preventing wasted effort on symptoms and ensuring durable solutions.

## When to use

Use for ANY technical issue: test failures, bugs in production, unexpected behavior, performance problems, build failures, or integration issues. Especially when under time pressure, "quick fixes" seem obvious, multiple fixes have already failed, or the issue is not fully understood. Do not skip when the issue seems simple, you are in a hurry, or a manager demands immediate fixes—the systematic approach is faster than thrashing.

## Workflow

1. **Read error messages carefully** — do not skip past errors or warnings; read stack traces completely and note line numbers and file paths.
2. **Reproduce consistently** — determine if the issue can be triggered reliably; if not reproducible, gather more data before proceeding.
3. **Check recent changes** — examine git diffs or recent commits for new dependencies, config changes, or environmental differences.
4. **Gather evidence across components** — for multi-component systems, add diagnostic instrumentation at each boundary: log data entering and exiting each component, verify environment/config propagation, and check state at every layer. Run once to identify the failing component.
5. **Trace data flow backward** — identify where the bad value originates; keep tracing up the call stack until the source is found; fix at the source, not at the symptom.
6. **Find working examples** — locate similar working code in the same codebase and read the reference implementation completely.
7. **Compare against references** — list every difference between working and broken code, however small; do not assume "that can't matter."
8. **Identify dependencies** — determine what other components, settings, config, or environment the code needs, and what assumptions it makes.
9. **Form a single hypothesis** — state clearly: "I think X is the root cause because Y"; be specific and not vague.
10. **Test minimally** — make the smallest possible change to test the hypothesis; test one variable at a time.
11. **Verify before continuing** — if the test passes, proceed to phase 4; if not, form a new hypothesis and do not add more fixes on top.
12. **Create a failing test case** — write the simplest possible reproduction script or automated test before implementing any fix.
13. **Implement a single fix** — address only the root cause identified; make one change at a time; no "while I'm here" improvements or bundled refactoring.
14. **Verify the fix** — confirm the test passes, no other tests are broken, and the issue is actually resolved.

## Quality bar

- Root cause is identified and documented before any fix is proposed.
- Only one change is implemented at a time; no bundled fixes.
- A failing test case exists before and after the fix to confirm resolution.
- No other tests are broken by the change.
- The issue is fully resolved, not just symptom-masked.

## Pitfalls

- Proposing fixes before completing root cause investigation (violates the Iron Law).
- Skipping reproduction or gathering evidence.
- Making multiple changes at once, preventing isolation of what worked.
- Fixing symptoms instead of the source; each fix revealing a new problem in a different place after two or more attempts signals an architectural issue, not a series of failed hypotheses.
- Ignoring red flags such as "quick fix for now, investigate later" or "I don't fully understand but this might work."
- Attempting a third or subsequent fix without stepping back to question the architecture.