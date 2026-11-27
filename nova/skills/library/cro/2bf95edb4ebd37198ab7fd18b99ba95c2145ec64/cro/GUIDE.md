# cro

One sentence: NOVA can analyze landing, pricing, and lead-form pages to diagnose why conversions are low and provide actionable recommendations on value propositions, headlines, CTAs, trust signals, and friction points.

## When to use

- User asks why a page isn't converting or wants more conversions from a specific URL
- Evaluating landing pages, pricing pages, or lead/contact forms
- Need to decide whether to add, remove, or change a field or element
- Page shared for feedback on conversion performance

## Workflow (numbered steps adapted to NOVA's tools)

1. **Collect page context**: Use `web_search` or `read_website` to fetch the target page. If a form, note its purpose (signup, demo request, contact, quote).
2. **Identify page type and conversion goal**: Determine if it is a homepage, landing, pricing, feature, or other. Clarify the primary goal (sign up, purchase, request demo, download, contact sales).
3. **Gather traffic source**: Ask or note where visitors are coming from (organic, paid, email, social) to assess message match.
4. **Run CRO analysis framework**: Evaluate the page across the seven dimensions in order of impact:
   - Value Proposition Clarity
   - Headline Effectiveness
   - CTA Placement, Copy, and Hierarchy
   - Visual Hierarchy and Scannability
   - Trust Signals and Social Proof
   - Objection Handling
   - Friction Points
5. **Reference detailed guidance**: If the page involves forms, load `references/form.md` for field and layout specifics. For experiment hypotheses, consult `references/experiments.md` organized by page type.
6. **Output recommendations**: Structure findings into Quick Wins, High-Impact Changes, Test Ideas, and Copy Alternatives as defined in the framework.
7. **Ask task-specific questions** if data is missing: current conversion rate, traffic origin, post-page flow, available analytics (heatmaps, recordings), and prior experiments.

## Quality bar (checklist)

- [ ] Page type and primary conversion goal are explicitly identified.
- [ ] Traffic source context is noted for message-match assessment.
- [ ] All seven CRO dimensions are evaluated in the prescribed order, with specific observations (not generic praise).
- [ ] Recommendations reference the relevant framework documents (form.md, experiments.md) when applicable.
- [ ] Output follows the required structure: Quick Wins, High-Impact Changes, Test Ideas, Copy Alternatives.
- [ ] Copy alternatives provide 2-3 options with rationale, grounded in the headline patterns and form guidance.
- [ ] No claims about conversion lift are made without citing observed data or benchmarks; all factual statements require sources.

## Pitfalls

- Assuming a change will improve conversions without checking traffic source relevance or message match.
- Recommending removal of form fields or elements without assessing whether they serve as trust signals or address common objections.
- Overlooking mobile experience issues when the page is primarily viewed on desktop.
- Providing vague feedback ("make it better") instead of specific, numbered observations and actionable copy alternatives.
- Skipping the value proposition clarity check; if visitors cannot state the benefit in 5 seconds, other optimizations matter less.
- Ignoring the existing product-marketing context if `.agents/product-marketing.md` (or legacy filename) is available.