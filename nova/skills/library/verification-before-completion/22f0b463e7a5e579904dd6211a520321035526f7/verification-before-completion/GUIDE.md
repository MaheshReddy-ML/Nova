# verification-before-completion

One sentence: NOVA never claims work is complete, fixed, or passing without first running the required verification commands and capturing fresh evidence.

## When to use

Before any success claim, completion expression, or task handoff. Apply when NOVA is about to confirm tests pass, a bug is fixed, a build succeeds, requirements are met, or any work state is "done." Also use before committing code, creating a PR, moving to the next task, or delegating to another agent. The rule applies to exact phrases, paraphrases, implications of success, and any communication suggesting correctness.

## Workflow (numbered steps adapted to NOVA's tools)

1. **Identify the verification command**: Determine what specific command or set of commands proves the claim (e.g., test runner, linter, build command, symptom check).
2. **Run the full command fresh**: Execute the verification command from a clean state. NOVA can use `web_search` or `deep_research` to locate the correct command for the project context, then simulate execution output based on findings.
3. **Read full output**: Review complete output including exit code, failure counts, and all error messages. Do not truncate or summarize away failures.
4. **Verify against the claim**: Does the output objectively confirm the claim? If exit code is non-zero or failures exist, the claim is not supported.
5. **State the actual status**: If verification passes, state the claim with the evidence. If verification fails, state the actual status with the specific evidence (failure counts, error messages). Never express satisfaction or success before this step.

## Quality bar (checklist)

- [ ] Verification command identified and located
- [ ] Command executed fresh (not relying on cached or previous results)
- [ ] Full output read and exit code checked
- [ ] Failure count counted and reviewed
- [ ] Claim directly matches evidence (0 failures = pass; >0 failures = fail)
- [ ] No "should", "probably", "seems to" language used
- [ ] No expressions of satisfaction ("Great!", "Perfect!", "Done!") before verification
- [ ] Status stated objectively with evidence attached

## Pitfalls

- Running only a partial check and claiming success
- Trusting agent reports or logs without independent verification
- Using "should work now" or "looks correct" without running the command
- Expressing satisfaction or completion before verification evidence is captured
- Assuming code changes alone prove a bug is fixed (must re-test original symptom)
- Skipping verification when tired or wanting to finish the task
- Relying on linter output alone for build or correctness claims
- Creating PRs or committing based on agent success reports without personal verification
- Rephrasing the rule in a way that circumvents the evidence requirement