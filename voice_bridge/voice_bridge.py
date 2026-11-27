"""voice_bridge: let an AI agent phone its owner for a live voice review.

    from voice_bridge import call_user_for_review
    feedback = call_user_for_review("Built the pricing page...", "Is the hero copy right?", "https://preview.example")

Stack (all free / open source):
  * FastRTC WebRTC voice call in the browser, local Moonshine STT and Kokoro TTS (no audio leaves this machine except the
    text sent to the LLM).
  * ntfy.sh urgent push so the phone rings (ntfy app, subscribed to NTFY_TOPIC) with a one-tap link to the call.
  * Groq llama-3.3-70b-versatile (OpenAI-compatible) for sub-second replies; Gemini Flash as an optional fallback.

The FastRTC server starts once in a daemon thread and is reused. Calls are serialised: a second call_user_for_review()
waits for the first to finish. Each call has its own session id, so audio or events from an old call never leak into a new one.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, field

import httpx
from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # reuse keys from the enclosing Nova project when present
log = logging.getLogger("voice_bridge")

GOODBYE = re.compile(r"\b(?:bye|goodbye|that'?s all|that is all|we'?re done|i'?m done|end (?:the )?call|hang up|talk later|"
                     r"go ahead and (?:build|ship|continue)|sounds good,? (?:go|ship))\b", re.I)


def _env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class _Session:
    id: str
    status_summary: str
    questions: str
    preview_url: str
    transcript: list[tuple[str, str]] = field(default_factory=list)
    joined: threading.Event = field(default_factory=threading.Event)
    ended: threading.Event = field(default_factory=threading.Event)
    last_activity: float = field(default_factory=time.monotonic)
    end_reason: str = ""

    def add(self, speaker, text):
        self.transcript.append((speaker, text.strip()))
        self.last_activity = time.monotonic()


class _Bridge:
    def __init__(self):
        self.port = int(os.getenv("VOICE_BRIDGE_PORT", "7860"))
        self.host = os.getenv("VOICE_BRIDGE_HOST", "127.0.0.1")
        self.public_url = os.getenv("PUBLIC_TUNNEL_URL", "").rstrip("/") or f"http://{self.host}:{self.port}"
        self.topic = os.getenv("NTFY_TOPIC", "").strip()
        self.ntfy_server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        self.session: _Session | None = None
        self.state_lock = threading.Lock()
        self.call_lock = threading.Lock()  # one review call at a time
        self.server_lock = threading.Lock()
        self.started = False
        self.stt = self.tts = self.tts_options = None
        self.llm = self.llm_model = None

    # ---------- lazy setup ----------
    def _models(self):
        if self.stt is None:
            from fastrtc import KokoroTTSOptions, get_stt_model, get_tts_model

            self.stt = get_stt_model(os.getenv("VOICE_BRIDGE_STT", "moonshine/base"))
            self.tts = get_tts_model("kokoro")
            self.tts_options = KokoroTTSOptions(voice=os.getenv("VOICE_BRIDGE_VOICE", "af_heart"), speed=1.05, lang="en-us")
        if self.llm is None:
            from openai import OpenAI

            if os.getenv("GROQ_API_KEY"):
                self.llm = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1")
                self.llm_model = os.getenv("VOICE_BRIDGE_MODEL", "llama-3.3-70b-versatile")
            elif os.getenv("GEMINI_API_KEY"):
                self.llm = OpenAI(api_key=os.environ["GEMINI_API_KEY"],
                                  base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
                self.llm_model = os.getenv("VOICE_BRIDGE_MODEL", "gemini-2.0-flash")
            elif os.getenv("NVIDIA_API_KEY"):
                # NVIDIA's free catalogue: Nemotron Super answers in ~0.3 s to first token, fast enough for live voice.
                self.llm = OpenAI(api_key=os.environ["NVIDIA_API_KEY"], base_url="https://integrate.api.nvidia.com/v1")
                self.llm_model = os.getenv("VOICE_BRIDGE_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b")
            else:
                raise RuntimeError("Set GROQ_API_KEY, GEMINI_API_KEY or NVIDIA_API_KEY in the environment or .env")

    def ensure_server(self):
        """Start the FastRTC call page once, in a daemon thread; later calls reuse it."""
        with self.server_lock:
            if self.started:
                return
            self._models()
            from fastrtc import ReplyOnPause, Stream

            stream = Stream(ReplyOnPause(self._reply, startup_fn=self._greet, can_interrupt=True),
                            modality="audio", mode="send-receive", concurrency_limit=1, time_limit=None)
            thread = threading.Thread(target=lambda: stream.ui.launch(server_name=self.host, server_port=self.port,
                                                                      prevent_thread_lock=True, show_error=True, quiet=True),
                                      name="voice-bridge-server", daemon=True)
            thread.start()
            thread.join(timeout=60)
            self.started = True
            log.info("Voice bridge call page on http://%s:%s (public: %s)", self.host, self.port, self.public_url)

    # ---------- conversation ----------
    def _current(self):
        with self.state_lock:
            return self.session

    def _speak(self, text):
        for chunk in self.tts.stream_tts_sync(text, self.tts_options):
            yield chunk

    def _system_prompt(self, session):
        preview = f"\nPreview link: {session.preview_url}" if session.preview_url else ""
        return ("You are the voice of an AI design agent on a live phone-style call with its owner, who is reviewing UI work "
                "while away from the desk. Speak naturally and briefly: one or two short sentences per turn, no lists, no "
                "markdown, no URLs read aloud. Get clear decisions on the open questions, confirm what you understood, and "
                "when everything is answered, say you'll get back to work and say goodbye.\n\n"
                f"What the agent just did: {session.status_summary}\nOpen questions: {session.questions}{preview}")

    def _llm(self, session, max_tokens=120, extra=()):
        messages = [{"role": "system", "content": self._system_prompt(session)}]
        for speaker, text in [*session.transcript[-16:], *extra]:
            messages.append({"role": "user" if speaker == "owner" else "assistant", "content": text})
        extra = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}} if self.llm_model.startswith("nvidia/") else {}
        response = self.llm.chat.completions.create(model=self.llm_model, messages=messages, max_tokens=max_tokens,
                                                    temperature=0.5, **extra)
        return (response.choices[0].message.content or "").strip()

    def _greet(self, *_args):
        session = self._current()
        if session is None or session.ended.is_set():
            yield from self._speak("Hi. There's no review waiting right now, so you can hang up. Talk soon.")
            return
        session.joined.set()
        session.last_activity = time.monotonic()
        try:
            greeting = self._llm(session, max_tokens=110, extra=[(
                "owner", "Hi, I've just joined. Greet me, summarise what you did in one sentence, then ask your first question.")])
        except Exception:  # noqa: BLE001 - the greeting must never fail the call
            greeting = f"Hi! Quick update: {session.status_summary[:220]}. {session.questions[:200]}"
        session.add("assistant", greeting)
        yield from self._speak(greeting)

    def _reply(self, audio):
        from fastrtc import CloseStream

        session = self._current()
        if session is None or session.ended.is_set():
            return
        text = self.stt.stt(audio).strip()
        if not text:
            return
        session.add("owner", text)
        try:
            answer = self._llm(session)
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM reply failed: %s", exc)
            answer = "Sorry, I lost that for a second. Could you say it again?"
        session.add("assistant", answer)
        yield from self._speak(answer)
        if GOODBYE.search(text) or GOODBYE.search(answer):
            session.end_reason = "owner ended the call"
            session.ended.set()
            yield CloseStream()

    # ---------- notification ----------
    def _ring(self, session):
        if not self.topic:
            log.warning("NTFY_TOPIC is not set; open %s to join the call", self.public_url)
            return False
        body = f"{session.status_summary[:300]}\n\nTap to join the voice review."
        headers = {"Title": "Your agent wants a quick voice review", "Priority": "urgent", "Tags": "telephone_receiver,rotating_light",
                   "Click": self.public_url, "Actions": f"view, Join call, {self.public_url}, clear=true"}
        if session.preview_url:
            headers["Actions"] += f"; view, Open preview, {session.preview_url}"
        try:
            response = httpx.post(f"{self.ntfy_server}/{self.topic}", content=body.encode(), headers=headers, timeout=15)
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.error("ntfy notification failed: %s", exc)
            return False

    # ---------- public entry ----------
    def call(self, status_summary, questions, preview_url="", *, join_timeout=None, call_timeout=None, idle_timeout=None):
        join_timeout = join_timeout or _env_float("VOICE_BRIDGE_JOIN_TIMEOUT", 600)
        call_timeout = call_timeout or _env_float("VOICE_BRIDGE_CALL_TIMEOUT", 900)
        idle_timeout = idle_timeout or _env_float("VOICE_BRIDGE_IDLE_TIMEOUT", 60)
        with self.call_lock:
            self.ensure_server()
            session = _Session(uuid.uuid4().hex[:8], status_summary.strip(), questions.strip(), (preview_url or "").strip())
            with self.state_lock:
                self.session = session
            rang = self._ring(session)
            try:
                if not session.joined.wait(join_timeout):
                    session.end_reason = "owner did not join"
                    return (f"[voice review {session.id}] The owner did not join the call within {int(join_timeout)} s"
                            f"{'' if rang else ' (the phone notification could not be sent)'}. No feedback was given; "
                            "continue with your best judgement or try again later.")
                deadline = time.monotonic() + call_timeout
                while not session.ended.wait(1):
                    now = time.monotonic()
                    if now > deadline:
                        session.end_reason = "call time limit reached"
                        break
                    if now - session.last_activity > idle_timeout:
                        session.end_reason = "call went quiet (owner likely hung up)"
                        break
                return self._result(session)
            finally:
                session.ended.set()
                with self.state_lock:
                    if self.session is session:
                        self.session = None

    def _result(self, session):
        lines = [f"{'OWNER' if speaker == 'owner' else 'AGENT'}: {text}" for speaker, text in session.transcript]
        transcript = "\n".join(lines) or "(no conversation)"
        summary = ""
        if any(speaker == "owner" for speaker, _ in session.transcript):
            try:
                response = self.llm.chat.completions.create(model=self.llm_model, max_tokens=300, temperature=0.2, messages=[
                    {"role": "system", "content": "Extract the owner's decisions and instructions from this review call as a short "
                     "bulleted list of concrete actions for the agent. Include only what the owner said or approved."},
                    {"role": "user", "content": transcript}])
                summary = (response.choices[0].message.content or "").strip()
            except Exception:  # noqa: BLE001
                summary = ""
        return (f"[voice review {session.id} · ended: {session.end_reason or 'completed'}]\n"
                + (f"OWNER INSTRUCTIONS:\n{summary}\n\n" if summary else "") + f"TRANSCRIPT:\n{transcript}")


_BRIDGE = _Bridge()


def call_user_for_review(status_summary: str, questions: str, preview_url: str = "") -> str:
    """Ring the owner's phone (ntfy), hold a live voice review over WebRTC and return their feedback.

    Blocks until the owner ends the call, says goodbye, goes quiet, or a timeout passes. Safe to call repeatedly;
    concurrent calls are queued. Returns the owner's instructions plus the full transcript as plain text.
    """
    return _BRIDGE.call(status_summary, questions, preview_url)


# Tool schema for function-calling agents (OpenAI / Groq / Gemini compatible).
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "call_user_for_review",
        "description": "Phone the owner for a live voice review of UI changes and return their spoken feedback. Use when a "
                       "decision or approval is needed and the owner is away from the desk.",
        "parameters": {"type": "object", "properties": {
            "status_summary": {"type": "string", "description": "What you built or changed, in 1-3 plain sentences."},
            "questions": {"type": "string", "description": "The specific decisions you need from the owner."},
            "preview_url": {"type": "string", "description": "Optional public link to the preview."}},
            "required": ["status_summary", "questions"]},
    },
}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(call_user_for_review("I redesigned the landing page hero with a bolder headline and a single call to action.",
                               "Do you prefer the dark or light hero? Should the pricing link stay in the header?",
                               os.getenv("DEMO_PREVIEW_URL", "")))
