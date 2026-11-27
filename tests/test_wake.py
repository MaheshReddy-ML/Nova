import time
from types import SimpleNamespace

import pytest

from nova.briefing import briefing, collect, last_briefing, mark_briefed
from nova.config import Settings
from nova.conversation import Session, speech_chunks
from nova.domain import MissionInput
from nova.runtime import Runtime
from nova.store import Store


@pytest.fixture
def runtime(tmp_path):
    settings = Settings(_env_file=None, database_path=tmp_path / "nova.db", workspace_path=tmp_path / "work",
                        owner_name="Asha Rao", smtp_host="smtp.example.com", smtp_username="me@example.com",
                        smtp_password="x")
    store = Store(settings.database_path)
    yield Runtime(settings, store, None, None)
    store.db.close()


class Socket:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


def test_briefing_reports_news_and_waiting_email(runtime):
    task, _ = runtime.submit(MissionInput(title="Research: glaze", workflow="topic", objective="glaze"))
    with runtime.store.db:
        runtime.store.db.execute("UPDATE tasks SET state='completed', updated=? WHERE id=?", (time.time(), task["id"]))
    runtime.outbox.draft("hello@elm.example", "Hello Elm", "A short note about your website.")
    text, data = briefing(runtime, since=time.time() - 60)
    assert text.startswith("Good") and "Asha" in text
    assert "1 mission completed: glaze." in text
    assert "hello@elm.example is ready. Say send it" in text
    mark_briefed(runtime.store)
    assert last_briefing(runtime.store) > time.time() - 5
    assert not collect(runtime, last_briefing(runtime.store))["done"]


def test_quiet_briefing(runtime):
    text, _ = briefing(runtime, since=time.time() - 3600)
    assert "All quiet" in text


def test_long_replies_are_spoken_in_full():
    text = "Sentence number one is here. " * 40
    parts = speech_chunks(text)
    assert all(len(part) <= 420 for part in parts) and sum(map(len, parts)) >= len(text.strip()) - len(parts)


async def test_wake_word_triggers_a_spoken_briefing(runtime):
    socket = Socket()
    session = Session(socket, runtime)
    session.voice = False  # no audio playback in tests; text still streams
    session.standby = True
    session.detector = SimpleNamespace(feed=lambda data: 0.91, reset=lambda: None)
    await session.check_wake(b"\x00" * 2560)
    await session.active
    kinds = [item["type"] for item in socket.sent]
    assert "wake" in kinds and "done" in kinds
    spoken = next(item["text"] for item in socket.sent if item["type"] == "delta")
    assert spoken.startswith("Good")
    # A second wake with nothing new gets a short acknowledgement instead of a repeat briefing.
    socket.sent.clear()
    await session.check_wake(b"\x00" * 2560)
    await session.active
    assert next(item["text"] for item in socket.sent if item["type"] == "delta") in {"Yes?", "At your service.", "I'm listening.", "Go ahead."}


async def test_sleep_phrase_returns_to_standby(runtime):
    socket = Socket()
    session = Session(socket, runtime)
    await session.turn(session.generation, text="that's all")
    assert any(item["type"] == "sleep" for item in socket.sent)
    assert any(item.get("text") == "Very good. Standing by." for item in socket.sent)


def test_hey_nova_phrase_matching():
    from nova.wake import PHRASE, detector, phrase

    assert all(PHRASE.search(text) for text in ("Hey Nova!", "hey, nova what's new", "Hey Noah", "okay nova"))
    assert not any(PHRASE.search(text) for text in ("I read about a supernova", "Hey, now go ahead", "Hey Jarvis", "Casanova"))
    assert phrase("hey_nova") == "Hey Nova" and type(detector("hey_nova")).__name__ == "PhraseWake"
