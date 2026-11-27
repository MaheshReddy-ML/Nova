# Competitor Profiling
## Competitor Profiling
## Initial Assessment
1. **Competitor URLs** — the list of competitor website URLs to profile
2. **Your product** — what you do (if not in product marketing context)
3. **Depth level** — quick scan (key facts only) or deep profile (full research)
4. **Focus areas** — any specific dimensions to prioritize (e.g., pricing, positioning, SEO strength, content strategy)
## Tool Stack Selection
## Core Principles
## 1. Facts Over Opinions
- **Observed**: what a source says, with the source and date
- **Inferred**: your reading of what was observed. Label it, and say how confident you are when it would change a decision
- **Implication**: what it might mean for your product, framed as a question or option, not a conclusion
## 2. Structured and Comparable
## 3. Current Data
## 4. Honest Assessment
## 5. Untrusted Input
## Saving Raw Data
- `<competitor-slug>` is lowercase, hyphenated (e.g. `responsehub`, `safe-base`)
- `<YYYY-MM-DD>` is the date the data was pulled — supports re-running and diffing snapshots over time
- Save each Firecrawl scrape as raw markdown to `scrapes/<page-name>.md`
- Save each DataForSEO response as raw JSON to `seo/<endpoint-name>.json`
- Save each review source to `reviews/<source>.md` (cleaned text) or `.json` (raw)
- Always create the date folder fresh on a new run; never overwrite a prior date's data
## Research Process
## Phase 1: Site Scraping (Firecrawl or WebFetch)
## Step 1: Map the site
- Homepage
- Pricing page
- Features / product pages
- About / company page
- Blog (top-level, for content strategy signals)
- Customers / case studies page
- Integrations page
- Changelog / what's new (if exists)
## Step 2: Scrape key pages
## Step 3: Scrape competitor reviews (optional but high-value)
- G2 reviews page for the competitor
- Capterra reviews page
- Product Hunt launch page
- TrustRadius profile
## Phase 2: SEO & Market Data (DataForSEO or Ubersuggest)
## Domain Authority & Backlinks
- Domain rank / authority score
- Total backlinks
- Referring domains count
- Spam score
- Top referring domains (quality signals)
- Link acquisition patterns
## Keyword & Traffic Intelligence
- Total organic keywords ranking
- Keywords in top 3, top 10, top 100
- Estimated organic traffic
- Domain-level organic metrics
- Estimated traffic value
- Top keywords by traffic
- What keywords they target
- Content gaps vs. your site
## Competitive Positioning Data
- Their closest organic competitors (may reveal competitors you haven't considered)
- Market overlap data
- Their highest-traffic pages
- Content that drives the most organic value
## Phase 3: Synthesis
## Output Format
## Profile Document Structure
## Summary Document
1. **Competitor landscape overview** — one paragraph summarizing the competitive field
2. **Comparison table** — key metrics side by side for all profiled competitors
3. **Positioning map** — where each competitor sits (e.g., simple↔complex, cheap↔premium)
4. **Key takeaways** — 3-5 strategic observations from the research
5. **Gaps and opportunities** — where the market is underserved
## Quick Scan vs. Deep Profile
## Quick Scan (faster, lower cost)
- Scrape: homepage + pricing page only