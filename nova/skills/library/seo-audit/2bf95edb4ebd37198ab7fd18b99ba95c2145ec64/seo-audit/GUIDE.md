# Seo Audit
## SEO Audit
## Initial Assessment
1. **Site Context**
- What type of site? (SaaS, e-commerce, blog, etc.)
- What's the primary business goal for SEO?
- What keywords/topics are priorities?
2. **Current State**
- Any known issues or concerns?
- Current organic traffic level?
- Recent changes or migrations?
3. **Scope**
- Full site audit or specific pages?
- Technical + on-page, or one focus area?
- Access to Search Console / analytics?
## Audit Framework
## Schema Markup Detection Limitation
2. **Google Rich Results Test** — https://search.google.com/test/rich-results
3. **Screaming Frog export** — if the client provides one, use it (SF renders JavaScript)
## Priority Order
1. **Crawlability & Indexation** (can Google find and index it?)
2. **Technical Foundations** (is the site fast and functional?)
3. **On-Page Optimization** (is content optimized?)
4. **Content Quality** (does it deserve to rank?)
5. **Authority & Links** (does it have credibility?)
## Technical SEO Audit
## Crawlability
- Check for unintentional blocks
- Verify important pages allowed
- Check sitemap reference
- Exists and accessible
- Submitted to Search Console
- Contains only canonical, indexable URLs
- Updated regularly
- Proper formatting
- Important pages within 3 clicks of homepage
- Logical hierarchy
- Internal linking structure
- No orphan pages
- Parameterized URLs under control
- Faceted navigation handled properly
- Infinite scroll with pagination fallback
- Session IDs not in URLs
## Indexation
- site:domain.com check
- Search Console coverage report
- Compare indexed vs. expected
- Noindex tags on important pages
- Canonicals pointing wrong direction
- Redirect chains/loops
- Soft 404s
- Duplicate content without canonicals
- All pages have canonical tags
- Self-referencing canonicals on unique pages
- HTTP → HTTPS canonicals
- www vs. non-www consistency
- Trailing slash consistency
## Site Speed & Core Web Vitals
- LCP (Largest Contentful Paint): < 2.5s
- INP (Interaction to Next Paint): < 200ms
- CLS (Cumulative Layout Shift): < 0.1
- Server response time (TTFB)
- Image optimization
- JavaScript execution
- CSS delivery
- Caching headers
- CDN usage
- Font loading
- PageSpeed Insights
- WebPageTest
- Chrome DevTools
- Search Console Core Web Vitals report
## Mobile-Friendliness
- Responsive design (not separate m. site)
- Tap target sizes
- Viewport configured
- No horizontal scroll
- Same content as desktop
- Mobile-first indexing readiness
## Security & HTTPS
- HTTPS across entire site
- Valid SSL certificate
- No mixed content
- HTTP → HTTPS redirects
- HSTS header (bonus)
## URL Structure
- Readable, descriptive URLs
- Keywords in URLs where natural
- Consistent structure
- No unnecessary parameters
- Lowercase and hyphen-separated
## International SEO & Localization
## Hreflang
- Self-referencing entry on every page (page must include itself in the hreflang set)
- Reciprocal links (if A points to B, B must point back to A -- or both are ignored)
- Valid codes: ISO 639-1 language + optional ISO 3166-1 Alpha 2 region (e.g., `en`, `en-GB` -- never `en-UK`)
- Consider `x-default` for unmatched language/region users, pointing to an appropriate fallback; it is recommended, not required for other valid annotations.