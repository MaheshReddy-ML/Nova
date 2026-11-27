# NOVA

NOVA is a local owner console for website research, proposal preparation, and voice-assisted task control. Its FastAPI service owns the mission queue, so a dashboard tab or voice session can disconnect while work continues.

## Run locally

```sh
uv sync --locked --python 3.12
uv run playwright install chromium
uv run nova serve
```

Open [the owner console](http://127.0.0.1:8000). The service uses the existing `.env`, stores checkpoints and events in `memory/nova.db`, and writes local projects to `workspace/`. Restart the service with the same database to recover interrupted missions. The queue runs while the local service is up and the computer is awake.

Use **New mission** to enter up to five business websites, discover linked homepages from one permitted public directory, or request a short NVIDIA planning brief. Missions can be queued for a future time and depend on an earlier mission. Use **Approvals** to review a proposal and record a decision for manual handoff.

`uv run nova first-mission` queues the sourced Hyderabad studio review. The completed run and its artifacts are visible in **Projects** on this machine.

## Voice and model access

Click **Enable microphone**, then try “What are you doing?”, “How many tokens have you used?”, or “Start website research”. Pause, resume, and cancel accept a task name or ID. Playback interruption has its own control. Enable headphone barge-in to let voice activity interrupt playback. By default NOVA ignores microphone activity while playing to avoid speaker feedback.

The gateway uses NVIDIA Build for text and NVIDIA Riva for streaming Parakeet and Magpie. If a speech endpoint explicitly reports an unsupported stream, NOVA uses its NVIDIA HTTP equivalent. Catalogue discovery selects current NVIDIA fallbacks when a configured model is absent. Local task and customer counts are deterministic. Provider-reported token usage and estimates are displayed independently. [NVIDIA text API](https://build.nvidia.com/nvidia/nemotron-3.5-bolt-e4b/apireference) · [NVIDIA Parakeet](https://build.nvidia.com/nvidia/parakeet-ctc-1_1b-asr/api) · [NVIDIA Magpie](https://build.nvidia.com/nvidia/magpie-tts-multilingual/api)

This checkout targets internal evaluation under NVIDIA’s trial terms and enforces a ₹0 application spending limit. Trial quotas depend on the model and account. Use **Refresh NVIDIA access** for catalogue and voice availability. [NVIDIA API Trial Terms](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf)

## Verification

```sh
uv run pytest -q
uv run nova benchmark
uv run python tests/browser_acceptance.py
```

The browser command expects a running service. To run a bounded live speech check and generate a reproducible browser microphone fixture, use:

```sh
uv run nova check-nvidia --voice-fixture output/playwright/microphone-fixture.wav
uv run python tests/browser_acceptance.py --voice-fixture output/playwright/microphone-fixture.wav
```

See [implementation progress](PROGRESS.md) for observed results and open scope.
