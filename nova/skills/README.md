# NOVA runtime skills

NOVA uses the [Agent Skills format](https://agentskills.io/specification) for project-local reference packages. The catalogue in [skills.lock.json](skills.lock.json) records pinned commits, file SHA-256 hashes, licenses, review dates, version labels, dependencies, and activation stages. Setup verifies bundle contents before enabling the five starter skills. SQLite persists subsequent installation, disablement, updates, rollbacks, activation outcomes, and the estimated prompt overhead of injected guidance.

| Skill | License | Pinned revision | Full source / compiled estimate |
| --- | --- | --- | ---: |
| Impeccable | Apache-2.0 | [2fc5e14](https://github.com/pbakaus/impeccable/tree/2fc5e1459efbbf06d92c7306517c286bf12490cf/.agents/skills/impeccable) | 12,833 / 323 |
| Context Engineering | MIT | [e997ac5](https://github.com/addyosmani/agent-skills/tree/e997ac5b9a74eab332d5e9793bb38a38c8cfdd74/skills/context-engineering) | 15,514 / 272 |
| Customer Research | MIT | [2bf95ed](https://github.com/coreyhaines31/marketingskills/tree/2bf95edb4ebd37198ab7fd18b99ba95c2145ec64/skills/customer-research) | 14,570 / 314 |
| Copy Editing | MIT | [2bf95ed](https://github.com/coreyhaines31/marketingskills/tree/2bf95edb4ebd37198ab7fd18b99ba95c2145ec64/skills/copy-editing) | 17,963 / 305 |
| Humanizer | MIT | [a32f244](https://github.com/blader/humanizer/tree/a32f24407364c74c812b43c15926d638bee1e072) | 33,628 / 292 |
| Animation Performance (optional) | MIT | [64eb3de](https://github.com/emilkowalski/skills/tree/64eb3deb9a5fbfa041faf783e0bc3fd635872e9c/skills/animation-performance), [f1090be](https://github.com/emilkowalski/skills/tree/f1090bec277140d02ed202440185ad9d02ac1490/skills/animation-performance) | 14,002 / 192 |

The estimate treats each UTF-8 byte as one possible token and adds framing bytes to the compiled guide. Provider usage is measured separately. The resolver filters by workflow stage, ranks matching skills locally, and loads up to three guides within the configured context budget. Upstream instructions and optional references are available in bounded excerpts for owner review. Only NOVA-authored compiled guides enter inference context. Every guide names its upstream source files in the lock, and each bundle preserves the original license and any applicable notice.

Installing a reviewed skill registers an immutable revision with local-reference access. Enabling it permits stage resolution. For an update-and-rollback example, install the older optional Animation Performance revision, enable it, update to the current revision, and then roll back from the skill details. Adding a new package requires a file and license review and a corresponding catalogue change. The registry rejects symbolic links, executable files, binary assets, undeclared tool grants, unapproved dependencies, and mismatched hashes.

Other inspected repositories remain outside the starter set. UI/UX Pro Max relies on its broader scripted database workflow. Work Humanizer overlaps the selected communication guide. Vercel's React-specific guidance does not apply to the current dashboard, and its agent-browser runtime would duplicate Playwright. Anthropic and OpenAI distribute skills with individual license terms, so they were not imported as suites. The requested TasteSkill URL did not return a public Git repository during review.

Run `uv run pytest -q tests/test_skills.py` to verify the registry and installed packages.
