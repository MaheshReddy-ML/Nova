# Prospecting

One sentence: NOVA turns an ICP definition into a verified, scored, outreach-ready lead sheet using the right data sources, qualification signals, and compliance posture for each motion.

## When to use

- User wants to find and qualify prospects for outbound.
- User asks who to target first, which signal to prioritize, or where to spot buyers with the problem.
- User needs to verify emails before a sequence or build a list from public pain signals.
- User is early-stage and needs their first customers or design partners (use Demand-signal branch).

## Workflow (numbered steps adapted to NOVA's tools)

1. **Collect inputs**: branch (SaaS / B2B / Local SMB / Demand-signal), ICP description (pull from product-marketing.md if present), target count, geography/tools/format preferences.
2. **Define the ICP** (Phase 1): firmographic fit, technographic fit (SaaS), buying signal, decision-maker profile, disqualifiers. Output as one paragraph + checklist. Do not proceed without this.
3. **Build the candidate list** (Phase 2): source 2–3× more candidates than the final desired count. SaaS/B2B: combine Apollo/ZoomInfo with Clay waterfall enrichment and LinkedIn Sales Nav decision-mapping. Local SMB: Google Maps assisted research, cross-check Yelp/website/social. Demand-signal: forums, communities, reviews, GitHub issues, job posts, launch announcements (via web_search).
4. **Qualify each candidate** (Phase 3): score against ICP checklist. Add evidence (source URLs) for every qualification. Confidence: High (2+ independent sources), Medium (1 credible source + consistent evidence), Low (incomplete/ambiguous). For B2B/SaaS: always verify email deliverability before adding to final list; flag catch-all domains per policy.
5. **Score and prioritize** (Phase 4): apply Hot/Warm/Cold/Skip rubric (SaaS/B2B/Local SMB) or 0–100 demand-fit (Demand-signal). Assign account tier: Tier 1 (top 25–50), Tier 2 (segments 20–200), Tier 3 (1:many). Default ratio: ~20% Hot, ~30% Warm, rest Cold/Skip.
6. **Output the lead sheet** (Phase 5): default markdown table; switch to CSV if >25 rows. After the table, always include "Top outreach targets" (top 3–5 Hot leads with one-sentence rationale each). Include search parameters and open questions.

## Quality bar (checklist)

- [ ] Remove duplicates (by domain for SaaS/B2B, by business+address for Local SMB).
- [ ] Every "Hot" lead has a verified contact + at least one source URL.
- [ ] No lead has an email that failed verification — move to invalid bucket and flag.
- [ ] No "Hot" label without a clear buying signal.
- [ ] Confidence levels honest — "High" requires 2 independent sources, not just two of NOVA's searches.
- [ ] No leads sourced from prohibited scraping (LinkedIn at scale, Google Maps bulk extract).
- [ ] Source URL + date captured for every contact (GDPR/CAN-SPAM lineage).
- [ ] Final count matches request, or user is explained why it is smaller.

## Pitfalls

1. Starting discovery without an ICP — qualifies the wrong things.
2. Treating Apollo/ZoomInfo as authoritative without cross-checks — data often out of date.
3. Adding contacts without email verification — cold email reputation tanks with bounces.
4. Bulk scraping LinkedIn or Google Maps — real risk of account suspension + ToS violation.
5. Mixing branches — do not apply Local SMB scoring to a B2B SaaS prospect, or vice versa.
6. "Hot" labels without buying signals — ICP fit alone is not enough.
7. No source URLs — every claim must be traceable to a public source.
8. Ignoring quiet hours/time zone when scheduling downstream outreach.
9. Forgetting to retain consent/lineage records — required for DSARs and audits.