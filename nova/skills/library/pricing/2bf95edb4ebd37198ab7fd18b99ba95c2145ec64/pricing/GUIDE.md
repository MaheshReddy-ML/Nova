# Pricing

One sentence: NOVA helps you design pricing that captures value, drives growth, and aligns with customer willingness to pay using frameworks for value metrics, tier structures, and price research.

## When to use

- Setting initial pricing for a new product
- Reviewing or restructuring existing tiers
- Evaluating whether to raise prices
- Designing a pricing page that is clear for buyers and readable by AI agents

## Workflow (numbered steps adapted to NOVA's tools)

1. **Gather product context** — Ask about product type, target market, current pricing, go-to-market motion, and primary value delivered. If a product-marketing context file exists, reference it first.

2. **Identify your value metric** — Determine what you charge for (per seat, per usage, per contact, etc.). Confirm it scales with value delivered and is easy to understand.

3. **Choose a tier structure** — Apply the Good-Better-Best framework: core features at the entry tier, full features with reasonable limits at the recommended tier, and advanced features at the premium tier. Differentiate via feature gating, usage limits, support level, or access.

4. **Run pricing research** — Use the Van Westendorp method to identify acceptable price ranges, or MaxDiff analysis to prioritize features for tier packaging. Reference [references/pricing-models.md](references/pricing-models.md) for the eight charging structures.

5. **Set price points** — Start with a learnable price near a round number ($10 for prosumer, $100 for SMB, $1,000 for mid-market). Avoid ultra-low anchors (e.g., $9/mo) that create false traction and make future raises difficult.

6. **Audit the pricing page** — Ensure prices are machine-readable text (not images), include Offer schema markup, and pass the "paste test": a browsing-capable AI can list plans and prices without guessing. Reference [references/pricing-page-teardown.md](references/pricing-page-teardown.md) for the AI-agent-readiness rubric.

7. **Plan a price increase if needed** — If signs appear (competitors raising prices, prospects unbothered by price, very high conversion/low churn), test new prices on new customers first, grandfather existing accounts with a grace period, and roll out in 5–10% waves with advance communication and a generous offer.

## Quality bar (checklist)

- [ ] Target customer personas are defined
- [ ] Competitor pricing is researched
- [ ] Value metric is identified and scales with customer value
- [ ] Tier structure uses clear differentiation (features, limits, support)
- [ ] Price points are based on willingness-to-pay research, not cost or competitor matching
- [ ] Pricing page displays prices as extractable text with Offer schema
- [ ] "Paste test" passes: an AI can list plans and prices from the page
- [ ] Price increase strategy includes new-customer test, grandfathered grace period, and staged rollout

## Pitfalls

- **Anchoring on cost** — Cost is a floor, never the basis for price. Value and differentiation set the price.
- **Matching competitors** — Copying a competitor's price copies their strategy and economics, not their results.
- **Ultra-low pricing** — Starting at $9/mo or similar creates false traction from price-sensitive users who churn loudly and are hardest to raise later.
- **Permanent grandfathering** — Indefinitely exempting existing customers leaves money on the table; treat grandfathering as a transition period, not a permanent exemption.
- **Hidden prices** — Prices locked in images or "Contact us" forms prevent both human buyers and AI agents from reading your tiers, losing deals before they begin.