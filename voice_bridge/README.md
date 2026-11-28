# voice_bridge

A free, open-source tool your agent can call to **phone you for a live voice review** while you're away from your desk.

```python
from voice_bridge import call_user_for_review, TOOL_SCHEMA

feedback = call_user_for_review(
    status_summary="I rebuilt the landing hero with a bolder headline and one call to action.",
    questions="Dark or light hero? Should pricing stay in the header?",
    preview_url="https://your-preview.example",
)
# feedback = "[voice review 3fa1 · ended: owner ended the call]\nOWNER INSTRUCTIONS:\n- Use the dark hero ...\n\nTRANSCRIPT:\n..."
```

`TOOL_SCHEMA` is a ready-made function-calling definition (OpenAI, Groq and Gemini compatible) to add to your agent's tools.

## Use it from Nova

Start the bridge once (it opens a fresh Cloudflare tunnel each time, so you never edit `PUBLIC_TUNNEL_URL`):

```sh
cd voice_bridge && .venv/bin/python control.py
```

Then say or type to Nova: **"call me"**, "ring me about the Regal Muse concept", or "you need something from me, phone me".
Nova's `call_owner` tool rings your phone through ntfy and replies at once. When the call ends, your instructions and the
transcript are saved in **Memory** and announced in the dashboard's live activity. Nova only calls you, never other numbers,
and only when you ask for a call. Calling real phone numbers would need a paid telephony provider such as Twilio.

## How a call works

1. NOVA sends an **urgent ntfy push** to your topic. The ntfy app rings and shows **Join call** and **Open preview** buttons.
2. Tap **Join call** to open the FastRTC page and start the call. The assistant greets you, summarises the work in one sentence and asks its first question.
3. Talk normally. Speech-to-text (Moonshine) and text-to-speech (Kokoro) run **locally**. Only the text goes to Groq (or Gemini) for replies of one or two sentences.
4. Say "that's all", "bye" or "go ahead and ship it" to end the call, or just hang up; the call ends after `VOICE_BRIDGE_IDLE_TIMEOUT` seconds of silence.
5. `call_user_for_review` returns your instructions as bullet points, followed by the full transcript.

The function blocks until the call ends. Calls are queued, so two triggers never talk over each other. The server starts once in a daemon thread and is reused.

## Setup

```sh
cd voice_bridge
uv venv --python 3.12 && uv pip install -r requirements.txt   # or: python -m venv .venv && pip install -r requirements.txt
cp .env.example .env                                         # add GROQ_API_KEY and NTFY_TOPIC
cloudflared tunnel --url http://127.0.0.1:7860               # put the https URL it prints in PUBLIC_TUNNEL_URL
python voice_bridge.py                                       # places a demo call
```

- **Phone ringing.** Install the ntfy app (Android or iOS), subscribe to your `NTFY_TOPIC`, and allow urgent or high-priority notifications to break through Do Not Disturb. ntfy rings through the app, not through a phone number. Placing a real call to a phone number would need a paid telephony provider such as Twilio.
- **Topic privacy.** Use a long, random topic name, because anyone who knows it can notify you. For a private alternative, self-host ntfy and set `NTFY_SERVER`.
- **Tunnel.** WebRTC needs HTTPS on your phone, so use a Cloudflare quick tunnel or ngrok. If your network blocks peer-to-peer media, configure a TURN server in FastRTC's `rtc_configuration`.

## Verified locally

`pytest test_voice_bridge.py` covers three things:
- A real Kokoro → Moonshine round trip ("Please use the dark hero" was transcribed correctly).
- The full call lifecycle with a stubbed LLM: join, greeting, reply, goodbye, the returned transcript and a second call in the same process.
- The no-show timeout.

The call page was also launched in a background thread and served over HTTP. Live Groq replies, ntfy delivery to your phone and the tunnel need your keys and device, so they weren't exercised here.
