# marketing-plan

One sentence: NOVA produces a comprehensive, executable 12-month marketing plan structured by AARRR, customized to the client's budget, team, stage, and capabilities, ready as a Notion-paste markdown artifact.

## When to use

Invoke this skill when a user needs a full go-to-market roadmap for a client, founder, or product — covering acquisition, activation, retention, referral, and revenue with AARRR-stage tagging, budget-aware sequencing, and cross-references to the marketing-ideas library and current-state rubric. Do not use for single-channel tactical execution (use channel-specific skills) or for unfiltered ideas without commitment (use marketing-ideas).

## Workflow (numbered steps adapted to NOVA's tools)

**Phase 1 — INIT:** NOVA reads all client materials and conducts structured intake (client overview, ICP, funnel state, funding, team, budget, active channels, in-flight work, stuck points). NOVA saves findings to `research.md` and scores Section 3 against the 17-section current-state rubric, marking data source.

**Phase 2 — REVIEW:** NOVA presents each of the 13 plan sections interactively. For each section, the owner can approve, adjust, add observations, or expand. NOVA saves each confirmed section to the progress file, making the plan resumable if interrupted.

**Phase 3 — FINALIZE:** NOVA compiles all 13 approved sections into `final_plan.md`. NOVA runs a verification pass: confirms cross-references (marketing-idea numbers, related skills, MCP integrations), checks for private paths that shouldn't ship, and validates brand voice consistency. NOVA optionally offers to publish to a private GitHub repo only with explicit client authorization; if visibility or authorization cannot be verified, the plan stays local.

## Quality bar (checklist)

- Every move names the AARRR stage it serves.
- Every recommendation is anchored in the client's actual budget, team, and current channels.
- The 90-day roadmap has assigned owners, not just actions.
- The funding-stage section explains what changes when the next round closes.
- The ops stack section names specific skills and MCPs per move.
- The idea bank shows what is not being done and why (skipped ideas with rationale).
- The executive summary can stand alone as an investor update.
- Open decisions are explicit, not glossed over (especially CAC unknown).

## Pitfalls

- Listing tactics without sequencing or AARRR-stage tagging.
- Recommending execution beyond the client's current team size or budget.
- Pretending paid budget exists before funding rounds close.
- Glossing over uncomfortable metrics like churn instead of naming them as open decisions.
- Using generic language without specific, client-moves (e.g., "improve SEO" without keyword or technical details).
- Ignoring the client's brand voice rules across all sections.
- Padding the plan with skills or ideas the client does not need.
- Failing to acknowledge work the team has already done.