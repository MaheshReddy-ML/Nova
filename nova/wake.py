"""Offline wake-word detection with openWakeWord.

Microphone audio stays on this machine while NOVA is on standby: 16 kHz PCM frames are scored locally
and only a detection wakes the assistant. Nothing is sent to NVIDIA until the owner speaks after the wake word.
"""
import threading
import time
import warnings

import numpy as np

CHUNK = 1280  # 80 ms at 16 kHz, the frame size openWakeWord is trained on.
_lock = threading.Lock()


def available_models():
    try:
        import openwakeword
    except ImportError:
        return []
    return sorted(openwakeword.models)


def _model(name):
    """A fresh model per session: openWakeWord keeps per-stream audio buffers inside the model object."""
    with _lock:
        import openwakeword
        from openwakeword.model import Model

        warnings.filterwarnings("ignore", message="Specified provider 'CUDAExecutionProvider'")
        if name not in openwakeword.models:
            raise ValueError(f"Unknown wake word model {name}")
        return Model(wakeword_model_paths=[openwakeword.models[name]["model_path"]])


class WakeDetector:
    def __init__(self, name="hey_jarvis", threshold=0.5, cooldown=2.0):
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown
        self.buffer = np.zeros(0, dtype=np.int16)
        self.last = 0.0
        self.model = None
        self.lock = threading.Lock()

    def load(self):
        self.model = _model(self.name)
        return self

    def reset(self):
        with self.lock:
            self.buffer = np.zeros(0, dtype=np.int16)
            if self.model is not None:
                self.model.reset()

    def feed(self, pcm: bytes):
        """Score 16 kHz mono int16 audio. Returns the confidence when the wake word fires, else None."""
        if self.model is None:
            self.load()
        with self.lock:
            self.buffer = np.concatenate([self.buffer, np.frombuffer(pcm, dtype=np.int16)])
            fired = None
            while len(self.buffer) >= CHUNK:
                frame, self.buffer = self.buffer[:CHUNK], self.buffer[CHUNK:]
                scores = self.model.predict(frame)
                score = max(scores.values()) if scores else 0.0
                if score >= self.threshold and time.monotonic() - self.last > self.cooldown:
                    self.last = time.monotonic()
                    fired = float(score)
                    self.model.reset()
                    self.buffer = np.zeros(0, dtype=np.int16)
                    break
            return fired


def phrase(name):
    return "Hey Nova" if name == "hey_nova" else name.replace("_", " ").title()


PHRASE = __import__("re").compile(r"\b(?:hey|hay|hi|hei|a|okay|ok)[\s,.!-]*(?:nova|noah|nover|novah|knova|nava|nov a|no va)\b",
                                  __import__("re").I)
_moonshine = {}


def _moonshine_model():
    with _lock:
        if "model" not in _moonshine:
            from moonshine_onnx import MoonshineOnnxModel, load_tokenizer

            warnings.filterwarnings("ignore", message="Specified provider 'CUDAExecutionProvider'")
            _moonshine["model"] = MoonshineOnnxModel(model_name="moonshine/tiny")
            _moonshine["tokenizer"] = load_tokenizer()
        return _moonshine["model"], _moonshine["tokenizer"]


class PhraseWake:
    """Custom wake phrase ("Hey Nova") with local speech recognition.

    A cheap energy gate collects short utterances; only those (≤2.5 s) are transcribed by Moonshine-tiny on this Mac
    and matched against the phrase. Nothing leaves the machine."""

    RATE = 16000

    def __init__(self, threshold=0.5, cooldown=2.0, pattern=PHRASE):
        self.pattern, self.cooldown = pattern, cooldown
        self.gate = 380 + int(400 * (threshold - 0.5))  # RMS gate; higher threshold → less sensitive
        self.buffer = np.zeros(0, dtype=np.int16)
        self.utterance = []
        self.voiced = self.silent = 0
        self.last = 0.0
        self.lock = threading.Lock()
        self.model = None
        self.heard = ""

    def load(self):
        self.model = _moonshine_model()
        return self

    def reset(self):
        with self.lock:
            self.buffer = np.zeros(0, dtype=np.int16)
            self.utterance, self.voiced, self.silent = [], 0, 0

    def transcribe(self, samples):
        model, tokenizer = self.model or self.load().model
        audio = (samples.astype(np.float32) / 32768.0)[None, :]
        tokens = model.generate(audio)
        return tokenizer.decode_batch(tokens)[0].strip()

    def feed(self, pcm: bytes):
        with self.lock:
            self.buffer = np.concatenate([self.buffer, np.frombuffer(pcm, dtype=np.int16)])
            fired = None
            frame = 480  # 30 ms
            while len(self.buffer) >= frame and fired is None:
                chunk, self.buffer = self.buffer[:frame], self.buffer[frame:]
                loud = np.sqrt(np.mean(chunk.astype(np.float32) ** 2)) > self.gate
                if loud:
                    self.voiced += 1
                    self.silent = 0
                    self.utterance.append(chunk)
                elif self.utterance:
                    self.silent += 1
                    self.utterance.append(chunk)
                length = len(self.utterance) * frame / self.RATE
                if self.utterance and (self.silent >= 12 or length >= 2.5):  # 360 ms pause or 2.5 s max
                    samples = np.concatenate(self.utterance)
                    enough = self.voiced >= 6 and length >= 0.35
                    self.utterance, self.voiced, self.silent = [], 0, 0
                    if enough and time.monotonic() - self.last > self.cooldown:
                        padded = np.concatenate([np.zeros(1600, np.int16), samples, np.zeros(1600, np.int16)])
                        self.heard = self.transcribe(padded)
                        if self.pattern.search(self.heard):
                            self.last = time.monotonic()
                            fired = 0.9
                            self.buffer = np.zeros(0, dtype=np.int16)
            return fired


def detector(name="hey_nova", threshold=0.5):
    """Factory: the custom 'Hey Nova' phrase, or any bundled openWakeWord model (hey_jarvis, alexa, hey_mycroft)."""
    if name == "hey_nova":
        return PhraseWake(threshold)
    return WakeDetector(name, threshold)
