# Brainstorming

One sentence: NOVA discovers the real intent and "why" behind any request before any work begins, preventing misaligned builds and rework.

## When to use

- Before any creative work: features, components, functionality, behavior changes, or planning (software or not).
- When a request is vague, open-ended, or seems to miss the actual goal.
- When starting a new business, talk, renovation, or any project where the destination isn't clear.

## Workflow (numbered steps adapted to NOVA's tools)

1. **Ground to context.** If an existing project or context is provided, read referenced specs, plans, or files. Explain how relevant parts work today and what the change would touch. Never reopen what has already been decided.
2. **Clarify the request.** Echo the request back in your own words: what is wanted, who it is for, and why (as far as stated). Note any constraints, conflicts, or cheaper paths found.
3. **Ask the pivotal question.** If the "why" is unsaid or unsettled, pose one open question in the user's own terms. Explain what the answer would change about the build.
4. **Lay out approaches.** Present 2–3 real alternatives as a message of their own. Sketch each concretely, grounded in the project, with trade-offs. Recommend one and ask which way to go. If only one sensible way exists, state why others don't fit and include a short design for approval.
5. **Size the work.** Report the effort in plain words (small change vs. project). Note that a design doc (short or full) is required before any building.
6. **Obtain approval.** For a small change, a short design doc; for a project, the full written design. No building occurs until approval is given.
7. **Proceed to planning.** After approval, invoke the writing-plans skill (or equivalent) to create the implementation plan.

## Quality bar (checklist)

- [ ] The user's actual goal and "why" are clearly stated, not just the requested feature.
- [ ] Constraints, non-goals, and anti-goals are identified.
- [ ] At least two real building approaches are sketched with trade-offs.
- [ ] A design doc (short or full) has been written and approved.
- [ ] The user has been asked about success criteria and any prior art they love or hate.
- [ ] No code, scaffolding, or implementation has started before approval.

## Pitfalls

- **Assuming the request is complete.** The spoken need often differs from the actual goal; asking "why" prevents building the wrong thing.
- **Offering menus of options too early.** Options steer; the user must describe the thing first.
- **Filling in "sensible defaults" without stating them.** A default the user never hears is one they cannot reject.
- **Writing the design doc before laying out approaches.** Approaches must be presented and chosen in conversation first.
- **Starting to build after a vague "sounds good."** Approval covers only the written design, not casual affirmations.
- **Ignoring prior art or constraints found in recon.** Always check existing work, code, or web sources before proposing approaches.