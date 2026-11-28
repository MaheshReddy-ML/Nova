import httpx
import pytest

from nova.config import Settings
from nova.domain import NovaError
from nova.gateway import PCM_PACKET, Gateway
from nova.store import Store

MODELS = {"tts": [
    {"canonical_name": "aura-2-athena-en", "languages": ["en", "en-US"], "metadata": {"tags": ["feminine", "calm"]}},
    {"canonical_name": "aura-2-zeus-en", "languages": ["en-US"], "metadata": {"tags": ["masculine"]}},
    {"canonical_name": "aura-luna-en", "languages": ["en-US"], "metadata": {"tags": ["feminine"]}},
    {"canonical_name": "aura-2-celeste-es", "languages": ["es"], "metadata": {"tags": ["feminine"]}},
]}


def make(tmp_path, handler, **options):
    settings = Settings(_env_file=None, nvidia_api_key="test-only", deepgram_api_key="dg-test",
                        database_path=tmp_path / "nova.db", workspace_path=tmp_path / "w", **options)
    store = Store(settings.database_path)
    return Gateway(settings, store, httpx.MockTransport(handler)), store


async def collect(gateway, text, voice=None):
    return [packet async for packet in gateway.stream_speech(text, voice)]


def test_provider_selection():
    assert Settings(_env_file=None).speech_provider == "nvidia"
    assert Settings(_env_file=None, deepgram_api_key="dg").speech_provider == "deepgram"
    assert Settings(_env_file=None, deepgram_api_key="dg", tts_provider="nvidia").speech_provider == "nvidia"
    with pytest.raises(ValueError):
        Settings(_env_file=None, deepgram_voice="aura-2-athena-en&model=x")


async def test_stream_is_sample_aligned_pcm(tmp_path):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        # Odd-sized network chunks must still reach the browser as whole 16-bit samples.
        return httpx.Response(200, stream=httpx.ByteStream(b"\x01" * 10001), headers={"content-type": "audio/l16"})

    gateway, store = make(tmp_path, handler)
    try:
        packets = await collect(gateway, "Hello **there**", voice="Magpie-Multilingual.EN-US.Sofia")
        assert seen["params"] == {"model": "aura-2-athena-en", "encoding": "linear16", "sample_rate": "16000",
                                  "container": "none"}
        assert seen["auth"] == "Token dg-test" and b"Hello there" in seen["body"]
        assert all(kind == "pcm" and len(data) % 2 == 0 and len(data) <= PCM_PACKET for kind, data in packets)
        assert sum(len(data) for _, data in packets) == 10000
        # The second request for the same phrase is served from cache.
        seen.clear()
        assert await collect(gateway, "Hello there") == packets and not seen
    finally:
        await gateway.close()
        store.db.close()


async def test_picked_voice_and_wav(tmp_path):
    def handler(request):
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=MODELS)
        assert request.url.params["model"] == "aura-2-hera-en"
        if request.url.params["container"] == "wav":
            return httpx.Response(200, content=b"RIFF\0\0\0\0WAVEdata")
        return httpx.Response(200, content=b"\0\0" * 4)

    gateway, store = make(tmp_path, handler)
    try:
        assert await gateway.voices() == ["aura-2-athena-en", "aura-luna-en"]
        assert (await gateway.synthesize("Hi", voice="aura-2-hera-en")).startswith(b"RIFF")
        assert await collect(gateway, "Hi", voice="aura-2-hera-en") == [("pcm", b"\0" * 8)]
    finally:
        await gateway.close()
        store.db.close()


@pytest.mark.parametrize(("status", "sticky"), [(402, True), (503, False)])
async def test_falls_back_to_magpie(tmp_path, status, sticky):
    def handler(request):
        return httpx.Response(status, json={"err_msg": "nope"})

    gateway, store = make(tmp_path, handler)
    spoken = []

    async def magpie(text, voice=None):
        spoken.append((text, voice))
        return b"RIFF"

    gateway.tts_streaming = False
    gateway.synthesize = lambda text, voice=None: magpie(text, voice)
    try:
        assert await collect(gateway, "Status please", voice="aura-2-hera-en") == [("audio", b"RIFF")]
        assert gateway.deepgram_active is not sticky
        assert spoken == [("Status please", "aura-2-hera-en")]
    finally:
        await gateway.close()
        store.db.close()


async def test_budget_errors_are_not_masked(tmp_path):
    gateway, store = make(tmp_path, lambda request: httpx.Response(200, content=b"\0\0"), max_speech_calls_hour=1)
    try:
        await collect(gateway, "one")
        with pytest.raises(NovaError) as error:
            await collect(gateway, "two")
        assert error.value.code == "speech_budget" and gateway.deepgram_active
    finally:
        await gateway.close()
        store.db.close()
