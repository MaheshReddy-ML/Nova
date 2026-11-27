# Launch Strategy

One sentence: NOVA helps users plan product or feature launches that build momentum, capture attention, and convert interest into users through structured frameworks and phased execution.

## When to use

When the user wants to plan a product or feature launch, determine if it's ready, decide when to announce, or how to get noticed via Product Hunt, beta/early access, waitlists, release go-to-market, launch checklists, or release notes.

## Workflow (numbered steps adapted to NOVA's tools)

1. **Check product marketing context:** Search for `.agents/product-marketing.md` or `.claude/product-marketing.md` using read_website. Use that context before asking questions.
2. **Run the SLC readiness gate:** Ask the user five quick checks (Simple, Lovable, Complete) to prevent stealth mode or "just one more feature" failure. If they fail, cut scope until one thing is lovable and complete.
3. **Select launch phase:** Based on SLC pass, choose from five phases: Internal (recruit early users via web_search for testers), Alpha (create landing page with deep_research, capture emails), Beta (scale early access, generate buzz via web_search for influencers), Early Access (leak details via read_website, run surveys), or Full Launch (open signups via web_search for platforms).
4. **Execute phase actions:** Use web_search for platform best practices, read_website for existing assets, find_contacts for influencer outreach, draft_email to compose announcements (owner confirms), and whatsapp_message for quick alerts.
5. **Product Hunt specific prep:** If chosen, use deep_research to study successful launches, optimize listing with compelling tagline/visuals/video, build supporter relationships via find_contacts, then draft_email for launch day coordination.
6. **Post-launch momentum:** Set up automated onboarding email sequence via draft_email, publish comparison pages via programmatic-seo, create interactive demo, and gather feedback via web_search for survey tools.

## Quality bar (checklist)

- [ ] Product passes SLC gate: one clearly-defined thing, target user would choose to use it, whole experience with no glaring stubs
- [ ] Owned channels established: email list, blog, or community ready
- [ ] Landing page with clear value proposition created (read_website for existing, web_search for templates)
- [ ] Email capture/waitlist signup functional
- [ ] Launch assets: screenshots, demo video, GIFs prepared (read_website for existing assets)
- [ ] Analytics/tracking in place to monitor signups and engagement
- [ ] Product Hunt listing prepared: tagline, visuals, demo video, supporter relationships if using
- [ ] Team ready to engage and respond to feedback during and after launch
- [ ] Post-launch onboarding email sequence drafted and scheduled
- [ ] Comparison pages and interactive demo planned for ongoing momentum

## Pitfalls

- **Stealth mode:** Polishing in private without launching; never ships, nobody learns you exist.
- **"Just one more feature":** Scope creeps forever; launch never comes. Cut back to SLC.
- **Relying only on rented channels:** Social media visibility without capturing users into owned email/list results in short-lived traffic spikes.
- **Skipping readiness gate:** Launching an unloved, incomplete product damages credibility and wastes momentum.
- **Ignoring post-launch work:** Announcement live is not the end; onboarding, comparison pages, and feedback loops are required for retention.