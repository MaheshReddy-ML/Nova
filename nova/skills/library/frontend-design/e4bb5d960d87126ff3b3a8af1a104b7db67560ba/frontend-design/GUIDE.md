# frontend-design

One sentence: NOVA produces distinctive, intentional UI that avoids templated defaults by grounding every choice in the subject's industry, audience, and primary job, using deliberate palette, typography, and layout heuristics.

## When to use

When building new UI or reshaping an existing one and the client wants a visual identity that is not mistaken for anyone else's. Use this when the brief rejects cliché or templated feels and pays for an opinionated, specific point of view.

## Workflow

1. **Identify the subject**: If the brief does not state what is being designed, identify a concrete subject, audience, and primary job; confirm with the client. Use any memory of the client's preferences or context as hints.
2. **Ground designs in subject matter**: Let the industry, materials, and vernacular drive distinctive choices (e.g., a toy for girls 8–11 vs. a financial-analyst dashboard).
3. **Build a token system** (first pass):
   - **Color**: 4–6 named hex values describing the core base palette.
   - **Type**: Typefaces and their roles; one family or two clearly distinct.
   - **Layout**: One-sentence prose descriptions and ASCII wireframes; decide left/center/justified alignment.
   - **Principles**: High-level guidance for what makes this page unique.
4. **Review against the brief**: Check that no part reads like a generic default you would produce for any similar page. Revise any non-unique elements, stating what was changed and why.
5. **Only after confirmation**, write the code following the revised plan, being mindful of CSS selector specificities to avoid canceling out styles.

## Quality bar

- Responsive down to mobile.
- Visible keyboard focus.
- Reduced motion respected.
- Visually accessible.
- Harmonious color palettes.
- One memorable element; everything else quiet and disciplined.
- No decoration that does not serve the brief.

## Pitfalls

- Using default cream/terracotta, near-black/acid-green, broadsheet, SaaS-card kit, or template chrome (ALL-CAPS eyebrows, middle-dot strings, spaced em dashes, tinted near-black, monospace data labels, arrow suffixes) — these read as AI-generated tells.
- Accenting just one word in a headline, using all caps for labels, or adding unnecessary labels above content.
- Numbered markers (01/02/03) unless the content is genuinely a sequence.
- Scattered motion; default fade-and-slide-up entrances on every section.
- Typographic cleverness over legibility; failure/emptiness moments that are vague or apologetic.
- Copy that does not serve understanding; tone that is not conversational or brand-matched.