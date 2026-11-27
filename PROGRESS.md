# NOVA implementation progress

The current release is NOVA 2.0. See the [upgrade report](UPGRADE.md) for completed upgrades, measured results, and operating limits. The entries below describe the prior MVP baseline.

## Working

- Local FastAPI service, SQLite WAL checkpoints, prioritized missions, dependencies, one-shot scheduling, pause, resume, cancellation, recovery, retry limits, and emergency stop.
- NVIDIA-only gateway, live model discovery, a validated planning brief, reserved foreground inference capacity, token and request budgets, speech cache, and provider latency metrics.
- Browser microphone capture, streamed Parakeet partial and final captions, streamed Magpie Sofia audio, playback interruption, optional headphone barge-in, HTTP speech fallback, and recorded playback timing.
- Public HTML audits and directory discovery, evidence-based scoring, local website concepts, desktop and mobile Chromium verification, proposals, and a lightweight lead and approval queue.
- Owner dashboard with live event replay, projects, customer evidence, approval review, model usage, and searchable SQLite memory.

## Verified

- Apple Silicon macOS with Python 3.12.12. The existing `.env` contents were preserved, and its permissions were limited to the owner.
- NVIDIA returned 30 catalogue entries and 139 voice variants. The four configured model IDs were absent from the catalogue, so documented NVIDIA fallbacks were used. One live structured planning probe reported 94 tokens. HTTP speech synthesized a sample and transcribed it correctly. NVIDIA Riva also returned partial and final transcripts and streamed Sofia audio through the browser.
- The final Chromium microphone-fixture run produced three partial captions, one final caption, and 16 streamed PCM packets. The first text arrived 218 ms after utterance end, and the browser began scheduled playback at 927 ms. These are single-run browser measurements.
- The Hyderabad pottery studio mission audited three official websites in 6.176 seconds over seven workflow steps. It used zero model calls and zero audit cache hits. The final Claysutra review found four enquiry fields without HTML or ARIA labels and three H1 elements. The first pass missed an existing booking link, so the review was corrected against the full page markup before the final run. The local concept passed the form, navigation, layout, and console checks at 1440 px and 390 px. The ₹12,000 estimate assumes ten hours at ₹1,200 per hour and is pending owner review.
- A separate live directory test discovered and audited five linked business homepages and generated a verified concept. A local status query responded while research was waiting on a public website. [Public directory used for the check](https://cleanlabelguide.com/clean-eating/craft-workshop-venues-hyderabad)
- 13 automated tests passed. The synthetic context benchmark compared conservative request sizes of 8,973 and 143 estimated tokens and measured local status latency below 0.01 ms at P95 on the fixture.

## Scope remaining at the MVP checkpoint

- Physical microphone and speaker testing, reliable speaker-mode hands-free interruption, and repeated end-to-end latency benchmarks.
- Scheduled repeat missions, additional search and crawl providers, full CRM and finance workflows, Telegram notifications, richer model-guided design, and live vision and embedding integration.
- Arbitrary generated-code execution remains disabled on this installation because an isolated command runner is unavailable. The website workflow builds deterministic local HTML, CSS, and a small enquiry preview script.
- Documented model capability and account catalogue access were checked. Live text probes exercised the planning route. Exact account quotas and production licensing remain account-specific. Current local operation is for trial and internal evaluation.
- External outreach, public deployment, payments, and startup-on-login are outside the initial local implementation. The current proposal and demo are private.

## First mission artifacts

- [Local preview](http://127.0.0.1:8000/projects/2cea353672c5/index.html)
- [Proposal JSON](workspace/2cea353672c5/proposal.json)
- [Desktop](workspace/2cea353672c5/desktop.png) and [mobile](workspace/2cea353672c5/mobile.png) screenshots
