# Performance Optimization

One sentence: NOVA can profile bottlenecks, apply structured fixes for N+1 queries and image optimization, and enforce measurable quality gates to keep applications fast and reliable.

## When to use

- Performance requirements exist in the spec (load time budgets, response time SLAs)
- Users or monitoring report slow behavior
- Core Web Vitals scores are below thresholds
- A change is suspected to have introduced a regression
- Building features that handle large datasets or high traffic

## Workflow

1. **Measure** — Establish a real-data baseline with synthetic tools (Lighthouse, DevTools Performance tab) and real-user monitoring (web-vitals library, CrUX). Profile frontend and backend separately.
2. **Identify** — Diagnose the actual bottleneck using symptom-to-cause tables (e.g., slow LCP → large images; N+1 queries → missing joins). Reference the optimization-patterns.md patterns for each category.
3. **Fix** — Address only the identified bottleneck. Apply the specific pattern (e.g., join/include for N+1, `fetchpriority="high"` + modern formats for LCP image). Do not optimize in the dark.
4. **Verify** — Re-measure the same way, under the same conditions. Compare the delta against run-to-run variance. Keep only if the improvement exceeds noise and all tests stay green; revert neutral or worse changes. Log every attempt (kept or reverted) in a PERF.md or PR description so dead ideas are not re-run.
5. **Guard** — Add a synthetic CI budget (e.g., Lighthouse CI, bundlesize) and field monitoring (RUM p75 alerts). Enforce budgets for bundle size, API response time, Core Web Vitals, and other primary metrics. If a guard fires, return to Step 1 with a fresh baseline.

## Quality bar (checklist)

- [ ] Before and after measurements exist with specific numbers
- [ ] The result was re-measured the same way as the baseline (same command, same conditions)
- [ ] The improvement exceeds run-to-run variance, not just the mean
- [ ] Changes that didn't beat the baseline were reverted, not kept as neutral
- [ ] Attempts are logged, kept and reverted alike, so a dead idea isn't re-run
- [ ] The specific bottleneck is identified and addressed
- [ ] Core Web Vitals are within "Good" thresholds (LCP ≤ 2.5s, INP ≤ 200ms, CLS ≤ 0.1)
- [ ] Bundle size hasn't increased significantly (e.g., initial load < 200KB gzipped)
- [ ] No N+1 queries in new data fetching code
- [ ] Any new index is justified by a query plan before and after, and its write cost was considered
- [ ] Any new cache states what it keys on and how it goes stale (TTL, event/invalidation strategy)
- [ ] The measured user-facing metric has a synthetic budget or field monitor that can detect regression
- [ ] Existing tests still pass (optimization didn't break behavior)

## Pitfalls

- Optimization without profiling data to justify it
- N+1 query patterns in data fetching
- An index added without a query plan before and after
- A cache key that omits an input the response depends on (tenant, locale, viewer)
- A cache with no stated staleness window and no invalidation strategy
- Connection pool size raised without finding what holds connections
- List endpoints without pagination
- Images without dimensions, lazy loading, or responsive sizes
- Bundle size growing without review
- No performance monitoring in production
- `React.memo` and `useMemo` everywhere (overusing is as bad as underusing)
- Optimizations kept without a re-measurement that justifies them
- Several optimizations bundled into one measurement, so no single change can be attributed
- A "win" that required a test to be changed, skipped, or deleted
- The same failed optimization attempted more than once because nobody recorded the first attempt