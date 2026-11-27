# schema

One sentence: NOVA can implement, fix, or validate JSON-LD schema markup to help search engines understand content and enable rich results, while correctly identifying Google-supported types and retired features.

## When to use

- User asks to add, fix, or validate schema markup (JSON-LD)
- User wants to know which schema type fits a page or if markup is allowed
- User questions rich result eligibility or reports Search Console errors
- Broader SEO context or AI search optimization is needed

## Workflow

1. **Identify page type** – Determine primary content (product, article, recipe, FAQ, local business, etc.) and business goals.
2. **Check existing schema** – Use `read_website` to find current JSON-LD; note errors or outdated types.
3. **Verify Google support** – Consult Google's [structured data gallery](https://developers.google.com/search/docs/appearance/structured-data/search-gallery) to confirm which features are currently supported; avoid recommending retired types (FAQ rich results removed May 2026, HowTo retired September 2023, sitelinks search box November 2024).
4. **Select schema type** – Choose from: Organization, WebSite, Article, Product, SoftwareApplication, BreadcrumbList, LocalBusiness, Event, HowTo (semantic only), FAQPage (semantic only). Use `@graph` to combine types when appropriate.
5. **Populate required properties** – Follow type-specific requirements (e.g., Product needs name, image, offers with price/availability; Article needs headline, image, datePublished, author).
6. **Validate** – Run Google Rich Results Test and Schema.org Validator; fix missing/required properties, invalid dates/URLs, and content mismatches.
7. **Deploy and monitor** – Implement JSON-LD in `<head>` or end of `<body>`; monitor Search Console enhancement reports for supported features.

## Quality bar

- [ ] Requested Google appearance is currently supported, or a separate semantic consumer is identified
- [ ] Markup validates in Schema.org Validator and passes Google Rich Results Test for supported features
- [ ] All required properties are included; recommended properties are added where relevant
- [ ] Schema accurately reflects visible page content and is updated when content changes
- [ ] No spam tactics; follows Google's structured data guidelines

## Pitfalls

- Recommending markup for retired Google features (FAQ rich results, HowTo rich results, sitelinks search box)
- Omitting required properties or using invalid values (non-ISO dates, relative URLs, wrong enumeration values)
- Marking up content that does not exist on the page
- Ignoring existing schema or failing to update it when content changes
- Treating Rich Results Test detection of retired types as a broken implementation