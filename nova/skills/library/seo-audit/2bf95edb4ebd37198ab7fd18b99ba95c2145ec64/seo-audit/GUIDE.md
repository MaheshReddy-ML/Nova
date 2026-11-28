# SEO Audit
This skill makes NOVA better at diagnosing why pages won't rank, traffic dropped, or technical setups like canonicals, hreflang, and redirects are wrong.

## When to use
Use when the user says SEO is bad, traffic dropped, a page won't rank, or they need an audit of indexing, Core Web Vitals, on-page elements, titles, or local SEO. Start here for general SEO complaints; use programmatic-seo for pages at scale, schema for structured data, ai-seo for AI search, and local-seo for map pack and citation work.

## Workflow (numbered steps adapted to NOVA's tools)
1. Gather site context: site type, primary SEO goal, priority keywords, known issues, current organic traffic, recent changes or migrations, and audit scope. Ask only what is missing.
2. Check robots.txt and XML sitemap via read_website; verify important pages are allowed, sitemap is submitted, and it lists only canonical, indexable URLs.
3. Run site:domain.com checks via web_search to gauge indexation and spot unexpected pages or missing important pages.
4. Audit priority pages with read_website: titles, meta descriptions, H1s, heading hierarchy, canonical tags, noindex directives, redirects, and URL structure.
5. Check Core Web Vitals and mobile-friendliness via web_search for PageSpeed Insights guidance and Search Console reports; note LCP under 2.5s, INP under 200ms, CLS under 0.1.
6. For hreflang and canonicals on multilingual sites, inspect page source via read_website; verify self-referencing entries, reciprocal links, valid ISO codes (en-GB, never en-UK), and that canonicals never cross locales.
7. For schema markup, do not rely on read_website alone—it strips script tags. Use web_search to find Google Rich Results Test guidance or ask the owner for a Screaming Frog export; never report "no schema" based solely on static fetch.
8. Check local SEO signals if relevant: NAP consistency, Google Business Profile, location pages, and local content via web_search and find_local_businesses.
9. For competitor and backlink context, use web_search and search_papers only when scholarly evidence is needed; otherwise rely on observable page data.
10. Draft findings using the issue/impact/evidence/fix/priority format and save the full report with save_document. Keep spoken replies short.

## Quality bar (checklist)
- [ ] Indexation and crawlability checked before on-page factors
- [ ] Every issue includes evidence from an NOVA tool or owner-provided access
- [ ] Canonicals are self-referencing on unique pages and never cross-locale
- [ ] Hreflang pairs are reciprocal, use valid ISO codes, and include self-references
- [ ] Core Web Vitals thresholds cited: LCP < 2.5s, INP < 200ms, CLS < 0.1
- [ ] Titles 50–60 characters, unique, primary keyword near front
- [ ] Meta descriptions 150–160 characters, unique per page
- [ ] One H1 per page, logical heading hierarchy
- [ ] No claim made without a source or observable evidence
- [ ] Prioritized action plan separates critical fixes, high-impact improvements, quick wins, and long-term work

## Pitfalls
- Treating read_website output as proof of missing schema; it strips script tags and cannot see JS-injected JSON-LD.
- Assuming one broken hreflang annotation invalidates all others; Google processes valid bidirectional pairs independently.
- Cross-locale canonicalization (e.g., French to English), which suppresses the non-canonical locale entirely.
- Using URL parameters for language (?lang=en); subdirectories are recommended.
- Noindexing thin locale pages to save crawl budget; better to not create them or make them genuinely helpful.
- Reporting Search Console or analytics metrics without owner access; NOVA cannot log in or pull private data.
- Recommending scripts, packages, crawlers, or CI tools; NOVA cannot run them. Suggest them only as owner-provided exports.