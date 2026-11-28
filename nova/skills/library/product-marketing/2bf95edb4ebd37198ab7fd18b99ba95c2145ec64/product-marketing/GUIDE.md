# Product Marketing Context
One sentence: NOVA builds and maintains a shared product-marketing context doc covering product, ICP, positioning, competitors, customer language, brand voice, proof points, goals, paid-ads guardrails, and learnings so every downstream marketing task starts from verified facts.

## When to use
Use before any other marketing skill on a new project, when the audience or positioning changes, or when the user asks what belongs in the context doc or whether positioning/ICP is clear enough. Also use it to log tested learnings after campaigns, copy tests, or postmortems ship.

## Workflow (numbered steps adapted to NOVA's tools)
1. Check for an existing context doc. Search the owner's workspace via save_document/search_memory and ask the user if they have a product-marketing context file. If one exists elsewhere, offer to consolidate it into the canonical workspace doc.
2. If it exists, read it with the owner, summarize captured sections, note the Document version and recent Changelog entries, then ask which sections to update. Gather only those sections.
3. If it does not exist, offer two options: auto-draft from available materials (website copy, README, pitch decks, existing docs the owner shares) or start from scratch, walking through each section one at a time. Most users prefer auto-draft.
4. Gather information section by section. For each, explain what is being captured, ask targeted questions, push for verbatim customer phrases, confirm accuracy, then move on. Never dump all questions at once.
5. Draft the full Markdown document using the section structure below. Require sources for factual claims such as metrics, competitor names, and customer quotes; mark anything unverified as [needs confirmation].
6. Show the draft to the owner and ask what needs correcting or what is missing. Iterate until satisfied.
7. Set versioning. New docs: Document version v1 and one Changelog entry. Updates: increment version (v2 → v3), update Last updated to today's ISO date (YYYY-MM-DD), and prepend a one-line Changelog entry naming sections touched and why. Typo-only fixes do not bump the version or add an entry.
8. Save the final document to the owner's workspace using save_document. Tell the owner other marketing skills will now reference this context automatically.

## Quality bar (checklist)
- Document version and Last updated (ISO date) are present
- One-liner, product category, ICP, primary use case, and jobs-to-be-done are filled
- Direct, secondary, and indirect competitors each have a "falls short because" line
- Differentiation states benefits, not just features
- Top 3 objections have responses; anti-persona is named
- Customer language includes verbatim quotes, not polished paraphrases
- Brand voice has 3–5 attributes with means/doesn't mean/example line, plus tone by context
- Proof points cite metrics, logos, or testimonials with sources
- Paid Ads section includes target CPA/ROAS, hard floor, budget, conversions that count, and agent may/may-not limits (only if ads run)
- Learnings table is empty for V1 or contains sourced, specific entries with Evidence, Applies to, and Status
- Changelog is newest first, one line per revision, never rewrites past entries
- Every factual claim has a source or is marked [needs confirmation]

## Pitfalls
- Do not invent competitor names, metrics, or customer quotes; require sources or mark unverified
- Do not skip versioning—downstream skills generate against this doc, so a dated paper trail is required
- Do not treat a single anecdote as a proven learning; log single data points as watch or leave them out
- Do not write polished copy instead of capturing verbatim customer language
- Do not include Personas for B2C products or Paid Ads if the owner does not run ads
- Do not let NOVA change ad budgets, bids, tracking, or publish ads without owner approval
- Do not overwrite past Changelog entries; prepend new ones only