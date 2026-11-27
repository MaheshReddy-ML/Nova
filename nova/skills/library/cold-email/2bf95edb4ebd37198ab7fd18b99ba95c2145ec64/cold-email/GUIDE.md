# Cold Email Writing

One sentence: NOVA can write B2B cold outbound emails that sound human, reach inboxes, and generate replies without triggering spam filters or sounding like AI.

## When to use

- User wants to reach a prospect via email for the first time
- User needs a follow-up sequence after no reply
- User asks whether their opener, value prop, or CTA will work
- User wants to verify deliverability or compliance before sending

## Workflow (numbered steps adapted to NOVA's tools)

1. **Identify the prospect and context** — Use `web_search` or `deep_research` to find the prospect's role, company, and recent signals (funding, hiring, LinkedIn posts, tech stack changes). Save key findings with `save_memory`.

2. **Define the goal and value** — Clarify: who are you writing to, what outcome you want (meeting, reply, demo), the specific problem you solve, and any proof (case study, result, credibility signal).

3. **Choose a framework** — Select from Observation→Problem→Proof→Ask, Question→Value→Ask, Trigger→Insight→Ask, or Story→Bridge→Ask. Ensure every sentence earns its place and the personalization connects to the problem.

4. **Write the email** — Draft using peer-to-peer tone, contractions, "you/your" dominance, one low-friction ask. Avoid AI tells, jargon, feature dumps, and HTML. Keep under 150 words.

5. **Check deliverability and compliance** — Verify the prospect list with `find_contacts` or external verification. Confirm sending from a secondary domain with proper SPF/DKIM/DMARC. Turn off open tracking. Include plain-text opt-out and postal address. Check EU/UK consent rules (Germany/Italy require prior consent for B2B; UK allows B2B under legitimate interest but not sole traders).

6. **Review against the quality bar** — Read aloud: does it sound human? Would YOU reply? Does every sentence serve the reader? Is personalization connected to the problem? One clear ask?

7. **Save for owner confirmation** — Use `draft_email` to create the message. Owner must confirm before sending via `whatsapp_message` or other channel.

## Quality bar (checklist)

- [ ] Sounds like a sharp human wrote it (read aloud; no AI tells: no "it's not X, it's Y" contrasts, no stock phrases like "quick question," no em dashes)
- [ ] Would I reply to this if I received it?
- [ ] Every sentence serves the reader, not the sender
- [ ] Personalization connects to the problem (remove the opening and the email still makes sense)
- [ ] One clear, low-friction ask (interest-based CTA, not meeting request)
- [ ] No jargon: "synergy," "leverage," "best-in-class," "leading provider"
- [ ] No HTML, images, or multiple links
- [ ] Subject line: 2-4 words, lowercase, no punctuation tricks, looks colleague-to-colleague
- [ ] List verified; bounces under 2%
- [ ] Sending from secondary domain; SPF/DKIM/DMARC set; mailboxes warmed 3–4 weeks
- [ ] Open and click tracking turned off
- [ ] Plain-text opt-out line and postal address included
- [ ] EU/UK compliance checked (consent requirements by country)

## Pitfalls

- Opening with "I hope this email finds you well" or "My name is X and I work at Y"
- Asking for a 30-minute call in the first touch
- "Just checking in" follow-ups that add no new value
- Feature dumps (one proof point beats ten features)
- Fake "Re:" or "Fwd:" subject lines
- Identical templates with only {{FirstName}} swapped
- HTML, images, or multiple links
- Ignoring country-specific consent rules (Germany/Italy require prior consent for B2B cold email)
- Bounce rate above 2% from un-verified lists
- Sending from primary domain without proper warmup