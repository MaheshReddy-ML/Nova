# Third-party notices

Nova's own source code is MIT-licensed (see [LICENSE](LICENSE)). It bundles or downloads the components below, which keep their own licenses. The MIT license does not grant rights to the Nova name or logo (see "Name and logo" in the README).

## Bundled in this repository

| Component | Where | License |
| --- | --- | --- |
| Agent Skills (54 packages) | `nova/skills/library/` | Per skill, recorded in `skills.lock.json`: MIT (marketingskills, K-Dense scientific skills, agent-skills, superpowers, humanizer, emilkowalski/skills), Apache-2.0 (Anthropic skills, Impeccable). Each package includes its license file. |
| Fraunces, Inter, Instrument Serif, Manrope, Space Grotesk | `nova/sitekit/fonts/`, `nova/static/brand/` | SIL Open Font License 1.1 (`nova/sitekit/fonts/OFL.txt`) |
| axe-core | `nova/design_resources/axe.min.js` | MPL-2.0 (`nova/design_resources/LICENSE-axe.txt`) |

## Python dependencies (installed by `uv sync`)

FastAPI, Starlette, Uvicorn, httpx, pydantic, BeautifulSoup and Pillow are MIT/BSD/HPND-style licenses. The Playwright Python package is Apache-2.0 and downloads Chromium separately.
- NVIDIA Riva client: MIT.
- python-docx, python-pptx and XlsxWriter: MIT/BSD.
- onnxruntime: MIT.
- Moonshine (`fastrtc-moonshine-onnx`): MIT. Models: MIT.
- openWakeWord code: Apache-2.0.

**openWakeWord's pretrained wake-word models (for example `hey_jarvis`) are licensed CC BY-NC-SA 4.0 (non-commercial).** Nova's default wake word, `hey_nova`, uses Moonshine instead. Use the openWakeWord models only for personal, non-commercial use, or train your own.

## Voice bridge (`voice_bridge/`, separate environment)

- FastRTC: MIT.
- Kokoro TTS: Apache-2.0 weights.
- Moonshine STT: MIT.
- OpenAI Python SDK: Apache-2.0.

## Services and data

These are used at runtime under their own terms; they are not bundled:
- NVIDIA API catalogue (trial terms).
- Brave Search API.
- Google Places API.
- DuckDuckGo.
- OpenStreetMap (data © OpenStreetMap contributors, ODbL 1.0; attribution is required where map data is shown).
- Wikipedia (CC BY-SA).
- Wikidata (CC0).
- ntfy.sh.
- Groq or Gemini, used by the voice bridge.

Website concepts can include photographs from a business's own public site. These are for private pitches to that business only, and the business owns them.
