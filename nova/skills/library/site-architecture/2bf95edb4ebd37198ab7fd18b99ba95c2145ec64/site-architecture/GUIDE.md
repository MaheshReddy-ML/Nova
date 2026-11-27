# site-architecture

One sentence: NOVA helps plan intuitive website structure—page hierarchy, navigation, URL patterns, and internal linking—so sites are user-friendly and search-engine optimized.

## When to use

- User wants to plan or restructure a website
- User asks which pages are needed or where something belongs
- Need to design navigation, URL structure, or internal linking
- Not for XML sitemaps (see seo-audit) or structured data (see schema)

## Workflow (numbered steps adapted to NOVA's tools)

1. **Gather business context**: Ask about company purpose, primary audiences, top 3 site goals, current state (new or restructuring), existing URLs to preserve, platform, and site type (SaaS, content, e-commerce, docs, hybrid, small business).

2. **Conduct content inventory**: Determine planned or existing page count, most important pages by traffic/conversion/value, and planned expansions.

3. **Select site type template**: Match to one of six types (SaaS marketing, content/blog, e-commerce, documentation, hybrid SaaS+content, small business) and note typical depth, key sections, and URL patterns.

4. **Design page hierarchy**: Apply the 3-click rule; choose flat (2 levels), moderate (3 levels), or deep (4+ levels) based on site size; draft ASCII tree with L0–L3+ levels showing homepage, primary sections, section pages, and detail pages.

5. **Define navigation structure**: Limit header nav to 4–7 items with CTA rightmost; organize footer into product, resources, company, and legal columns; specify breadcrumb format mirroring URL hierarchy.

6. **Establish URL structure**: Use readable hyphenated paths reflecting hierarchy; enforce consistent trailing slash; avoid dates, IDs, query parameters, and over-nesting; ensure breadcrumb-URL alignment.

7. **Produce deliverables**: Output ASCII page hierarchy, Mermaid visual sitemap, URL map table, navigation spec, and internal linking plan with hub-and-spoke models and orphan page audit.

## Quality bar (checklist)

- [ ] Every page reachable within 3 clicks from homepage
- [ ] Header nav has 4–7 items max with CTA rightmost
- [ ] URL paths are readable, hyphenated, lowercase, and reflect hierarchy
- [ ] Consistent trailing slash policy enforced site-wide
- [ ] No orphan pages; each has at least one internal inbound link
- [ ] Anchor text is descriptive, not "click here" or "read more"
- [ ] Breadcrumb trail mirrors URL path with clickable segments
- [ ] Footer grouped into product, resources, company, legal columns
- [ ] Important pages have the most inbound internal links
- [ ] Breadcrumbs implemented on all pages

## Pitfalls

- Burying critical pages 4+ levels deep
- Using dates in blog URLs (e.g., `/blog/2024/01/15/post-title`)
- Over-nesting beyond 4 levels without justification
- Changing URLs without 301 redirects
- Including IDs in URLs (e.g., `/product/12345`)
- Mixing URL patterns (e.g., `/features/analytics` and `/product/automation`)
- Header nav exceeding 7 items causing decision paralysis
- Footer links ungrouped or exceeding 3 columns in mega menus
- Orphan pages with no internal links
- Vague anchor text like "click here" or "read more"
- Inconsistent trailing slash policy (some pages with, some without)