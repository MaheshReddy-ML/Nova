# Website design and verification benchmark

Run the five-category comparison from the project root.

```sh
uv sync --locked --python 3.12
uv run playwright install chromium
uv run python tests/design_benchmark.py
uv run python tests/design_benchmark.py --lighthouse
```

The Lighthouse option runs paired mobile-lab measurements for the restaurant fixture. It uses the published Lighthouse 13.6.0 npm package and the installed Playwright Chromium binary. The benchmark serves only the fixture files on a temporary loopback port. [Lighthouse command-line documentation](https://developer.chrome.com/docs/lighthouse/overview)

The harness renders five synthetic business briefs with the archived checkpoint renderer and the upgraded component library. The restaurant, architecture, healthcare, hospitality, and software briefs use fixture names and URLs. Each is checked at 1,440, 820, and 390 px. The benchmark compares stable rendering, interaction controls, keyboard skip links, contrast, layout shifts, asset size, and accessibility checks. [Playwright screenshots](https://playwright.dev/python/docs/screenshots) · [Deque axe-core](https://github.com/dequelabs/axe-core)

## Results

| Measurement | Checkpoint renderer | NOVA 2 renderer |
| --- | ---: | ---: |
| Projects | 5 | 5 |
| Rendered structures | 1 | 5 |
| Passing viewport checks | 15/15 | 15/15 |
| Sampled minimum control height | 26 px | 44 px |
| Working keyboard skip links | 0/15 | 15/15 |
| Axe violations | 0 | 0 |
| Median local browser first contentful paint | 16 ms | 16 ms |
| Median generated HTML, CSS and JS size | 5.1 KB | 7.4 KB |
| Restaurant Lighthouse performance score | 100/100 | 100/100 |
| Restaurant Lighthouse mobile FCP / LCP | 750 ms | 750 ms |
| Inferencing requests | 0 | 0 |

The recorded run is a local laboratory comparison. Passing viewport counts apply each version’s required browser checks. Control height and skip-link usability are shown independently. Axe checks a subset of accessibility rules, and the photographs or branding for real customer projects require owner review.

The pinned Impeccable instruction’s conservative context estimate is 12,833 units for its upstream text and 334 for the compiled guide, including compilation framing. These estimates use a byte-based upper bound. The fixture benchmark runs offline and measures component rendering independently of provider inference. The original instructions and compiled guide are versioned in the skills registry.

The run records per-viewport evidence in [benchmark.json](output/playwright/nova-2-design/benchmark.json). Example completed screenshots include the [restaurant desktop](output/playwright/nova-2-design/upgraded/000000000001/desktop.png), [architecture tablet](output/playwright/nova-2-design/upgraded/000000000002/tablet.png), [clinic mobile](output/playwright/nova-2-design/upgraded/000000000003/mobile.png), [hotel desktop](output/playwright/nova-2-design/upgraded/000000000004/desktop.png), and [software desktop](output/playwright/nova-2-design/upgraded/000000000005/desktop.png).
