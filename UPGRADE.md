# NOVA 2.0 release and verification

## Runtime and controls

- The original service, database, proposals, usage, and working projects remain readable. The additive database setup creates records for skills, repeat schedules, draft reviews, a private ledger, and owner feedback. The local baseline is commit `2bf16ff`.
- Skills are selected by stage. NOVA can list, search, install, enable, disable, evaluate, update, and roll back the reviewed revisions from the console. Five starter skills are enabled. The optional animation skill has two reviewed revisions. Every installation stores file hashes and license provenance. [Skill catalogue and pinned revisions](nova/skills/README.md)
- The console shows a stage graph, dependency and schedule state, a replay of stored events, model usage, and skill contribution. The persistent voice dock shows actual microphone or playback signal and supports five conversation modes and keyboard focus.
- Website missions accept official URLs, a linked public directory, or a named business query. Wikidata candidates carry their entity source and still go through the existing URL and public website audit checks. The interactive live lookup found Taj Hotels and its official site. [Wikidata entity record](https://www.wikidata.org/wiki/Q1521893)
- The website engine has original directions for restaurant, architecture, healthcare, hospitality, software, craft, and general projects. It verifies desktop, tablet, and mobile using offline functional, accessibility, and performance checks. Owner-created variants can prioritize another verified finding and appear in the project’s revision comparison. Local HTML is served in an opaque, restricted frame.
- A mission can opt into one small-model inference to prioritize an existing audit finding. The reviewed components continue to control website rendering. An owner may request a separate, cached NVIDIA visual critique of the generated preview. Semantic search is opt-in through the local API and uses public observation notes. [NVIDIA vision API](https://build.nvidia.com/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning/apireference) · [NVIDIA embeddings API](https://build.nvidia.com/nvidia/nemotron-3.5-embed-1b/apireference)
- The communications view generates and edits evidence-backed drafts. An edit requires a fresh review. Plain-text and HTML exports, DOCX reports, XLSX estimates, and a PPTX briefing use local templates. The ledger records invoices, receipts, and expenses entered by the owner and calculates cash totals. Draft estimates remain in proposal records.
- Telegram forwarding accepts a reviewed, digest-bound message to a configured private owner chat. The regression suite exercises the transport with a mock. The demonstration used dashboard and spoken notifications.

## Controlled demonstration

| Measure | Observed result |
| --- | --- |
| Task | `21ae5c6da987` |
| Voice inputs | “Start the assisted website review.” and “What are you doing?” |
| Workflow | Seven steps, three public studio audits, 10.454 seconds, zero audit cache hits |
| Skills | Customer Research, Impeccable, Copy Editing |
| Website planning call | Nemotron Bolt E4B reported 206 tokens, including 188 input and 18 output |
| Browser speech | 11 partial captions, 133 streamed PCM packets, one proactive announcement |
| Utterance end to scheduled playback with one active background task | 1,023 ms and 505 ms in the same fixture run |
| Verification | 1,440 px desktop, 820 px tablet, and 390 px mobile |
| Separate NVIDIA checks | Vision critique reported 720 tokens. Query and passage embeddings returned 2,048 dimensions and reported 14 tokens across two calls |
| Estimate | ₹12,000 for ten hours at ₹1,200 per hour. Pending private review |

The fixture uses two synthesized commands as Chromium microphone input and exercises the same NVIDIA recognition and playback routes as the dashboard. It does not exercise the Mac’s physical audio hardware. [Recorded run data](output/playwright/nova2-demo.json)

- [Verified local website](http://127.0.0.1:8000/projects/21ae5c6da987/index.html)
- [Private proposal](http://127.0.0.1:8000/projects/21ae5c6da987/proposal.json)
- [Editable proposal](http://127.0.0.1:8000/api/tasks/21ae5c6da987/export/docx)
- [Example introduction email](http://127.0.0.1:8000/api/drafts/39ff50a1d604/export/txt)
- [Studio workspace](http://127.0.0.1:8000/#projects)
- [Verified alternate revision](http://127.0.0.1:8000/projects/21ae5c6da987/revisions/d9e302746ce9/index.html)
- [Five-category browser and Lighthouse comparison](DESIGN-BENCHMARK.md)
- [Desktop console](output/playwright/nova-2-console/console-desktop.png) and [mobile console](output/playwright/nova-2-console/console-mobile.png)

## Regression checks

All 69 automated tests passed. The suite covers checkpoint migration, repeat scheduling, skill integrity and rollback, context budgets, provider boundaries, draft approval invalidation, sandboxed preview interactions, and duplicate notification delivery. Chromium verified the console on desktop and mobile, including the embedded concept and its local enquiry form. The downloadable proposal, estimate worksheet, and five-slide briefing all reopened. The estimate workbook contains both the editable fee formula and its calculated value.

## Operating limits

Physical microphone, speaker, and acoustic barge-in require a hands-on check. The current Mac has no isolated command runner configured for arbitrary generated programs, so the creative workflow uses reviewed local components and offline browser verification. NOVA runs while its local service is open and the machine is awake. The reviewed skill catalogue accepts bundled pinned packages. New upstream packages require review before adding to the catalogue. Trial quotas and production licensing remain account-specific. [NVIDIA trial terms](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf)
