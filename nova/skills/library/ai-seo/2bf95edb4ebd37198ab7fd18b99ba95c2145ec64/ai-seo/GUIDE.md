# AI SEO

One sentence: makes NOVA better at getting content cited and recommended by AI answers such as Google AI Overviews, ChatGPT, Perplexity, Claude, Gemini, and Copilot.

## When to use

Use when the user wants AI visibility, asks why AI cites a competitor, wonders whether llms.txt or a page format is worth it, or needs AEO/GEO guidance. For technical and on-page SEO, see seo-audit. For structured data, see schema.

## Workflow

1. Confirm product marketing context. Read `.agents/product-marketing.md`, `.claude/product-marketing.md`, or legacy `product-marketing-context.md` if present; ask only for information not already covered.
2. Gather context: key revenue-changing queries, current AI presence across ChatGPT, Perplexity, and Google AI Overviews, content types, domain strength, existing schema, goals, competitors, and third-party presence such as Wikipedia or review sites.
3. Check index eligibility first. Confirm priority pages appear in the index behind each engine the user cares about—Google Search Console for Google AI Overviews and Gemini, Bing Webmaster Tools for ChatGPT with search and Copilot, Brave search for Claude. Sites submitted only to Google are often missing from Bing and Brave.
4. Run an AI visibility audit. Test 10–20 important queries across platforms. Record whether the user is cited and which competitors are cited. Test problem-aware, solution-aware, product-aware, and most-aware queries written the way people type into chat boxes.
5. Analyze citation patterns. Compare content structure, authority signals, freshness, schema markup, and third-party presence. Turn findings into work: if AI states something wrong or vague, fix the page that should state that fact plainly; if absent, treat cited sources as targets for PR, review sites, and directories.

## Quality bar

- Every factual claim carries a source and date; never turn a study percentage into a client forecast without matching engine, industry, language, market, and date.
- Index eligibility is confirmed before content work begins.
- Priority pages pass the content extractability checklist: clear definition in first paragraph, self-contained answer blocks, sourced statistics, comparison tables where relevant, natural-language FAQ, schema markup, expert attribution, recent updates, and query-matched headings.
- Google work follows people-first, core Search optimization; no separate AI content or chunking for AI.
- Wildcard agent access is allowed by default unless a deliberate training opt-out is configured.
- Structural patterns support non-Google engines and do not hurt Google.

## Pitfalls

- Do not treat traditional SEO as optional; strong organic rankings remain one of the best predictors of AI visibility.
- Do not create separate content for AI; that risks scaled content abuse.
- Do not block all AI crawlers with an allowlist; named crawler groups replace wildcard rules and can silently exclude agent search APIs.
- Do not over-invest in Reddit or any single third-party surface; citation mixes shift overnight with retrieval updates.
- Do not quote vendor statistics without source, date, engine, industry, language, market, and matching context.
- Do not assume llms.txt is required for Google AI Overviews or AI Mode; Google explicitly says it is not.
- Do not rely on one page per keyword; cover full topical clusters because AI search uses query fan-out.