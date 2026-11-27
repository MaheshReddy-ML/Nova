# idea-refine

One sentence: NOVA transforms vague ideas into sharp, actionable concepts using structured divergent and convergent thinking, helping users stress-test assumptions and converge on a single direction before committing resources.

## When to use

- When an idea is still vague and needs shaping before it can become a plan
- When you need to stress-test assumptions before committing to a direction
- When you want to expand options before converging on one
- Trigger phrases: "Help me refine this idea", "Ideate on [concept]", "Stress-test my plan"
- Not for: a user who is unsure what they want at all (use interview-me), or a direction already chosen that needs a spec (use spec-driven-development)

## Workflow

1. **Restate & Clarify (Divergent):** Restate the idea as a crisp "How Might We" problem statement. Use AskUserQuestion to gather 3-5 sharpening questions about who this is for, what success looks like, real constraints, what's been tried before, and why now. Do not proceed until you understand who this is for and what success looks like.

2. **Generate Variations (Divergent):** Produce 5-8 idea variations using specific lenses: Inversion ("What if we did the opposite?"), Constraint removal ("What if budget/time/tech weren't factors?"), Audience shift ("What if this were for [different user]?"), Combination ("What if we merged this with [adjacent idea]?"), Simplification ("What's the version that's 10x simpler?"), 10x version ("What would this look like at massive scale?"), Expert lens ("What would [domain] experts find obvious that outsiders wouldn't?"). Push beyond what the user initially asked for; each variation must have a reason it exists.

3. **Cluster & Evaluate (Convergent):** After the user reacts to Phase 1, cluster resonating ideas into 2-3 distinct directions. Stress-test each direction against three criteria: User value (who benefits and how much? Is this a painkiller or vitamin?), Feasibility (technical and resource cost, hardest part?), and Differentiation (what makes this genuinely different? Would someone switch from their current solution?). Read refinement-criteria.md for the full evaluation rubric.

4. **Surface Assumptions:** For each direction, explicitly name hidden assumptions: what you're betting is true but haven't validated, what could kill the idea, and what you're choosing to ignore (and why that's okay for now). This is where most ideation fails; do not skip it.

5. **Sharpen & Ship (Output):** Produce a concrete markdown one-pager with: Problem Statement (one-sentence "How Might We" framing), Recommended Direction (2-3 paragraphs max), Key Assumptions to Validate (with testing strategies), MVP Scope (minimum version that tests the core assumption, what's in and out), and Not Doing list (explicit trade-offs). Ask user confirmation before saving to docs/ideas/[idea-name].md.

## Quality bar

- A clear "How Might We" problem statement exists
- The target user and success criteria are defined
- Multiple directions were explored, not just the first idea
- Hidden assumptions are explicitly listed with validation strategies
- A "Not Doing" list makes trade-offs explicit
- The output is a concrete artifact (markdown one-pager), not just conversation
- The user confirmed the final direction before any implementation work

## Pitfalls

- Generating 20+ shallow variations instead of 5-8 considered ones
- Skipping the "who is this for" question
- No assumptions surfaced before committing to a direction
- Yes-machining weak ideas instead of pushing back with specificity
- Producing a plan without a "Not Doing" list
- Ignoring existing constraints when ideating inside a project
- Jumping straight to Phase 3 output without running Phases 1 and 2