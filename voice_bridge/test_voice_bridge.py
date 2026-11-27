"""Offline checks: real local STT/TTS round trip, and the call lifecycle with a stubbed LLM (no keys, no phone)."""
import threading
import time
from types import SimpleNamespace

import numpy as np

import voice_bridge as vb


class FakeLLM:
    def __init__(self):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, model, messages, **_):
        last = messages[-1]["content"]
        if "Extract" in messages[0]["content"]:
            text = "- Use the dark hero\n- Keep pricing in the header"
        elif "joined" in last:
            text = "Hi! I rebuilt the hero. Dark or light?"
        else:
            text = "Got it, dark hero and pricing stays. I'll get back to work, bye!"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def stub(bridge, heard):
    bridge.started = True
    bridge.stt = SimpleNamespace(stt=lambda audio: heard.pop(0) if heard else "")
    bridge.tts = SimpleNamespace(stream_tts_sync=lambda text, options: iter([(24000, np.zeros(240, dtype=np.float32))]))
    bridge.llm, bridge.llm_model = FakeLLM(), "fake"
    bridge._ring = lambda session: True


def run_call(bridge, **timeouts):
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("text", bridge.call("Rebuilt the hero.", "Dark or light?", **timeouts)))
    thread.start()
    return thread, result


def test_call_lifecycle_and_reuse():
    bridge = vb._Bridge()
    stub(bridge, ["Dark please, and keep pricing in the header. That's all, bye."])
    for _ in range(2):  # the same server/session machinery is reused for a second call
        stub(bridge, ["Dark please, and keep pricing in the header. That's all, bye."])
        thread, result = run_call(bridge, join_timeout=5, call_timeout=10, idle_timeout=5)
        while bridge._current() is None:
            time.sleep(.01)
        list(bridge._greet())                       # owner connects: greeting is spoken
        outputs = list(bridge._reply((48000, np.zeros(4800, dtype=np.int16))))
        thread.join(5)
        assert not thread.is_alive()
        assert type(outputs[-1]).__name__ == "CloseStream"
        assert "OWNER: Dark please" in result["text"] and "Use the dark hero" in result["text"]
        assert "ended: owner ended the call" in result["text"]
        assert bridge._current() is None


def test_no_show_times_out():
    bridge = vb._Bridge()
    stub(bridge, [])
    thread, result = run_call(bridge, join_timeout=0.3, call_timeout=1, idle_timeout=1)
    thread.join(3)
    assert "did not join" in result["text"]


def test_local_speech_round_trip():
    from fastrtc import KokoroTTSOptions, get_stt_model, get_tts_model

    tts, stt = get_tts_model("kokoro"), get_stt_model("moonshine/base")
    rate, audio = tts.tts("Please use the dark hero.", KokoroTTSOptions(voice="af_heart"))
    heard = stt.stt((rate, audio)).lower()
    assert "dark" in heard and "hero" in heard, heard
