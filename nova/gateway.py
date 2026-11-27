import asyncio
import hashlib
import json
import re
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import StrEnum
from urllib.parse import urlsplit

import grpc
import httpx
from pydantic import ValidationError
from riva.client.proto import riva_asr_pb2 as asr, riva_asr_pb2_grpc as asr_grpc
from riva.client.proto import riva_tts_pb2 as tts, riva_tts_pb2_grpc as tts_grpc
from riva.client.proto.riva_audio_pb2 import AudioEncoding

from .config import BOLT, EMBED, OMNI, SUPER, Settings
from .domain import NovaError
from .store import Store, encoded


class Capability(StrEnum):
    FAST = "fast"
    REASONING = "reasoning"
    PLANNING = "planning"
    CODING = "coding"
    VISION = "vision"
    EMBEDDING = "embedding"
    ASR = "speech_to_text"
    TTS = "text_to_speech"


FALLBACK = {
    Capability.FAST: BOLT,
    Capability.REASONING: SUPER,
    Capability.PLANNING: BOLT,
    Capability.CODING: SUPER,
    Capability.VISION: OMNI,
    Capability.EMBEDDING: EMBED,
}


def number(value):
    return value if type(value) is int and value >= 0 else None


class Gateway:
    def __init__(self, settings: Settings, store: Store, transport=None):
        self.settings = settings
        self.store = store
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(28, connect=8), limits=httpx.Limits(max_connections=8),
            follow_redirects=False, trust_env=False, transport=transport,
        )
        self.foreground = asyncio.Semaphore(2)
        self.background = asyncio.Semaphore(1)
        self.speech = asyncio.Semaphore(2)
        self.discovery = asyncio.Lock()
        self.cooldown = {}
        self.audio_cache = OrderedDict()
        self.channel = None
        self.asr_streaming = self.tts_streaming = settings.speech_streaming

    def headers(self):
        key = self.settings.nvidia_api_key.get_secret_value()
        if not key or key.lower() in {"your_nvidia_api_key", "your_nvidia_api_key_here", "replace_me"}:
            raise NovaError("no_credentials", "NVIDIA credentials are missing.")
        return {"Authorization": f"Bearer {key}"}

    async def close(self):
        if self.channel:
            await self.channel.close()
        await self.client.aclose()

    def speech_channel(self):
        if self.channel is None:
            self.channel = grpc.aio.secure_channel("grpc.nvcf.nvidia.com:443", grpc.ssl_channel_credentials())
        return self.channel

    def speech_metadata(self, endpoint):
        function_id = urlsplit(endpoint).hostname.split(".")[0]
        return (("function-id", function_id), ("authorization", self.headers()["Authorization"]))

    @staticmethod
    def speech_error(exc):
        code = exc.code()
        if code == grpc.StatusCode.UNIMPLEMENTED:
            return NovaError("stream_unsupported", "NVIDIA streaming is unavailable for this endpoint.")
        if code == grpc.StatusCode.UNAUTHENTICATED:
            return NovaError("invalid_credentials", "NVIDIA rejected the configured credentials.")
        if code == grpc.StatusCode.RESOURCE_EXHAUSTED:
            return NovaError("rate_limited", "NVIDIA rate limited speech.", transient=True, retry_after=5)
        if code in {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED}:
            return NovaError("speech_network", "NVIDIA could not finish the speech stream.", transient=True)
        return NovaError("speech_provider", f"NVIDIA speech returned {code.name}.")

    def check(self, response):
        status = response.status_code
        if 200 <= status < 300:
            return
        if status == 401:
            raise NovaError("invalid_credentials", "NVIDIA rejected the configured credentials.")
        if status == 402:
            raise NovaError("quota", "NVIDIA trial access or quota is unavailable.")
        if status == 403 or status == 404:
            raise NovaError("unavailable", "The NVIDIA endpoint or model is unavailable for this account.")
        if status == 429:
            delay = 5.0
            retry = response.headers.get("Retry-After")
            if retry:
                try:
                    delay = float(retry)
                except ValueError:
                    try:
                        delay = parsedate_to_datetime(retry).timestamp() - time.time()
                    except (ValueError, TypeError, OverflowError):
                        pass
            raise NovaError("rate_limited", "NVIDIA rate limited the request.", transient=True,
                            retry_after=max(1, min(delay, 3600)))
        if status >= 500:
            raise NovaError("provider_failure", f"NVIDIA returned HTTP {status}.", transient=True)
        raise NovaError("provider_request", f"NVIDIA rejected the request with HTTP {status}.")

    async def get_json(self, url):
        try:
            response = await self.client.get(url, headers=self.headers())
            self.check(response)
            return response.json()
        except httpx.HTTPError as exc:
            raise NovaError("network", "Could not connect to NVIDIA.", transient=True) from exc
        except ValueError as exc:
            raise NovaError("provider_response", "NVIDIA sent an invalid response.") from exc

    async def catalogue(self, refresh=False):
        async with self.discovery:
            cached = self.store.cached("nvidia:catalogue")
            if cached is not None and not refresh:
                return cached
            body = await self.get_json(f"{self.settings.nvidia_base_url}/models")
            if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                raise NovaError("provider_response", "NVIDIA model discovery returned an unexpected response.")
            models = sorted({item["id"] for item in body["data"]
                             if isinstance(item, dict) and isinstance(item.get("id"), str)})
            self.store.cache("nvidia:catalogue", models, 3600)
            return models

    def configured(self, capability):
        return getattr(self.settings, {
            Capability.FAST: "fast_model", Capability.PLANNING: "planner_model",
            Capability.REASONING: "reasoning_model", Capability.CODING: "coding_model",
            Capability.VISION: "vision_model", Capability.EMBEDDING: "embedding_model",
        }[capability])

    async def route(self, capability):
        models = await self.catalogue()
        configured = self.configured(capability)
        selected = next((value for value in (configured, FALLBACK[capability]) if value in models), None)
        if not selected:
            raise NovaError("model_missing", f"No NVIDIA trial model is listed for {capability.value}.")
        if selected != configured:
            key = f"nvidia:route:{capability}"
            if self.store.cached(key) != selected:
                self.store.log("model", f"{capability.value.title()} uses {selected}", configured=configured)
                self.store.cache(key, selected, 3600)
        return selected

    def reserve(self, capability, model, task_id, lane, estimated, reserved):
        db = self.store.db
        now = time.time()
        with db:
            if self.store.stopped():
                raise NovaError("stopped", "Emergency stop is active.")
            if lane == "speech":
                count = db.execute("SELECT COUNT(*) FROM usage WHERE started>? AND lane='speech'", (now - 3600,)).fetchone()[0]
                if count >= self.settings.max_speech_calls_hour:
                    raise NovaError("speech_budget", "The hourly speech budget has been reached.")
            else:
                midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
                day = db.execute("SELECT COALESCE(SUM(COALESCE(total,reserved)),0) FROM usage WHERE started>=? AND lane!='speech'",
                                 (midnight,)).fetchone()[0]
                calls = db.execute("SELECT COUNT(*) FROM usage WHERE started>? AND lane!='speech'", (now - 3600,)).fetchone()[0]
                if day + reserved > self.settings.max_daily_tokens or calls >= self.settings.max_calls_hour:
                    raise NovaError("model_budget", "The hourly call or daily token budget has been reached.")
                if task_id:
                    count, tokens = db.execute(
                        "SELECT COUNT(*), COALESCE(SUM(COALESCE(total,reserved)),0) FROM usage WHERE task_id=? AND lane!='speech'",
                        (task_id,),
                    ).fetchone()
                    if count >= self.settings.max_task_model_calls or tokens + reserved > self.settings.max_task_tokens:
                        raise NovaError("task_budget", "This mission has reached its model budget.")
            return db.execute(
                "INSERT INTO usage(started,task_id,lane,capability,model,reserved,estimate,status) VALUES (?,?,?,?,?,?,?,'pending')",
                (now, task_id, lane, capability, model, reserved, estimated),
            ).lastrowid

    @asynccontextmanager
    async def invocation(self, capability, model, task_id=None, lane="foreground", estimate=0, reserve=0):
        semaphore = {"foreground": self.foreground, "background": self.background, "speech": self.speech}[lane]
        async with semaphore:
            self.headers()
            last, delay = self.cooldown.get(model, (0.0, 0.0))
            if delay and last > time.monotonic():
                raise NovaError("provider_cooldown", "NVIDIA is in a brief cooldown.", transient=True,
                                retry_after=last - time.monotonic())
            request_id = self.reserve(capability, model, task_id, lane, estimate, reserve)
            start = time.perf_counter()
            metrics = {}
            status = "ok"
            try:
                yield metrics
                self.cooldown.pop(model, None)
            except (asyncio.CancelledError, GeneratorExit):
                status = "cancelled"
                raise
            except httpx.HTTPError as exc:
                status = "network"
                self.cooldown[model] = (time.monotonic() + 3, 3)
                raise NovaError("network", "Could not complete the NVIDIA request.", transient=True) from exc
            except NovaError as exc:
                status = exc.code
                if exc.transient:
                    delay = exc.retry_after or 3
                    self.cooldown[model] = (time.monotonic() + delay, delay)
                raise
            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
                status = "provider_response"
                raise NovaError("provider_response", "NVIDIA returned unexpected response data.") from exc
            finally:
                provider_usage = metrics.get("usage")
                usage = provider_usage if isinstance(provider_usage, dict) else {}
                prompt = number(usage.get("prompt_tokens"))
                completion = number(usage.get("completion_tokens"))
                total = number(usage.get("total_tokens"))
                details = usage.get("completion_tokens_details") or {}
                reasoning = number(details.get("reasoning_tokens")) if isinstance(details, dict) else None
                if total is None and prompt is not None and completion is not None:
                    total = prompt + completion
                with self.store.db:
                    self.store.db.execute(
                        "UPDATE usage SET status=?,prompt=?,completion=?,reasoning=?,total=?,latency_ms=?,first_ms=?,estimate=? WHERE id=?",
                        (status, prompt, completion, reasoning, total, round((time.perf_counter() - start) * 1000),
                         metrics.get("first_ms"), metrics.get("estimate", estimate), request_id),
                    )
                    self.store.event("model", f"{model} · {status}", task_id, capability=capability, lane=lane,
                                     reported_tokens=total)

    @staticmethod
    def token_estimate(messages):
        return len(encoded(messages).encode("utf-8")) + 32  # Conservative, tokenizer-independent budget.

    async def chat(self, capability, messages, *, task_id=None, lane="foreground", max_output=256, schema=None):
        model = await self.route(capability)
        max_output = min(max_output, self.settings.max_output_tokens)
        payload = {"model": model, "messages": messages, "max_tokens": max_output, "stream": False}
        if model == BOLT:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if schema is not None and model == BOLT:
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": schema.__name__, "strict": True, "schema": schema.model_json_schema(),
            }}
        estimate = self.token_estimate(messages)
        if schema:
            estimate += len(encoded(schema.model_json_schema()).encode("utf-8"))
        if estimate > self.settings.max_input_tokens:
            raise NovaError("input_budget", "The selected context exceeds the input budget.")
        async with self.invocation(capability, model, task_id, lane, estimate, estimate + max_output) as metrics:
            response = await self.client.post(f"{self.settings.nvidia_base_url}/chat/completions",
                                              headers=self.headers(), json=payload)
            self.check(response)
            body = response.json()
            metrics["usage"] = body.get("usage")
            answer = body["choices"][0]["message"].get("content")
            if not isinstance(answer, str) or not answer.strip():
                raise NovaError("empty_response", "NVIDIA returned no visible answer.")
            metrics["estimate"] = estimate + len(answer.encode())
            if schema:
                try:
                    return schema.model_validate_json(answer)
                except ValidationError as exc:
                    raise NovaError("invalid_structure", "The model response failed schema validation.") from exc
            return answer.strip()

    async def stream_chat(self, messages):
        capability = Capability.FAST
        model = await self.route(capability)
        estimate = self.token_estimate(messages)
        if estimate > self.settings.max_input_tokens:
            raise NovaError("input_budget", "The selected context exceeds the input budget.")
        output = min(256, self.settings.max_output_tokens)
        payload = {
            "model": model, "messages": messages, "max_tokens": output, "stream": True,
            "stream_options": {"include_usage": True},
        }
        if model == BOLT:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        async with self.invocation(capability, model, estimate=estimate, reserve=estimate + output) as metrics:
            started = time.perf_counter()
            async with self.client.stream("POST", f"{self.settings.nvidia_base_url}/chat/completions",
                                          headers=self.headers(), json=payload) as response:
                self.check(response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    body = json.loads(data)
                    if body.get("usage"):
                        metrics["usage"] = body["usage"]
                    choices = body.get("choices")
                    content = choices[0].get("delta", {}).get("content") if choices else None
                    if isinstance(content, str) and content:
                        metrics.setdefault("first_ms", round((time.perf_counter() - started) * 1000))
                        metrics["estimate"] = metrics.get("estimate", estimate) + len(content.encode())
                        yield content
                if "first_ms" not in metrics:
                    raise NovaError("empty_response", "NVIDIA returned no visible answer.")

    async def voices(self, refresh=False):
        async with self.discovery:
            key = f"nvidia:voices:{self.settings.tts_base_url}"
            if not refresh and (cached := self.store.cached(key)) is not None:
                return cached
            body = await self.get_json(f"{self.settings.tts_base_url}/v1/audio/list_voices")
            if not isinstance(body, dict):
                raise NovaError("provider_response", "NVIDIA returned unexpected voice data.")
            voices = sorted({voice for group in body.values() if isinstance(group, dict)
                             for voice in group.get("voices", []) if isinstance(voice, str)})
            if not voices:
                raise NovaError("speech_unavailable", "NVIDIA did not list any voices.")
            self.store.cache(key, voices, 3600)
            return voices

    async def normalize_speech(self, text, voice):
        if not self.settings.voice_enabled:
            raise NovaError("voice_disabled", "Voice is disabled in the service configuration.")
        text = re.sub(r"`[^`]*`", "", re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text))
        text = re.sub(r"[#*_~]+", "", text).strip()[:450]
        if not text:
            return "", None
        voices = await self.voices()
        supported = [item for item in voices if f".{self.settings.tts_language.upper()}." in item.upper()]
        selected = voice or self.settings.tts_voice
        if selected not in supported:
            selected = next((value for value in supported if value.casefold() == selected.casefold()), None)
        if selected is None and voice is None and "Magpie-Multilingual.EN-US.Aria" in supported:
            selected = "Magpie-Multilingual.EN-US.Aria"
        if selected is None:
            raise NovaError("voice_missing", "That voice is unavailable for the configured language.")
        return text, selected

    def audio_key(self, mode, selected, text):
        return hashlib.sha256(encoded([mode, selected, self.settings.tts_language, text]).encode()).hexdigest()

    def cache_audio(self, key, data):
        self.audio_cache[key] = data
        if len(self.audio_cache) > 12:
            self.audio_cache.popitem(last=False)

    async def synthesize(self, text, voice=None):
        text, selected = await self.normalize_speech(text, voice)
        if not text:
            return b""
        key = self.audio_key("wav", selected, text)
        if key in self.audio_cache:
            self.audio_cache.move_to_end(key)
            self.store.log("voice", "Reused cached NVIDIA audio")
            return self.audio_cache[key]
        fields = {
            "text": text, "language": self.settings.tts_language, "voice": selected,
            "encoding": "LINEAR_PCM", "sample_rate_hz": "22050",
        }
        async with self.invocation(Capability.TTS, self.settings.tts_model, lane="speech") as metrics:
            async with self.client.stream(
                "POST", f"{self.settings.tts_base_url}/v1/audio/synthesize", headers=self.headers(),
                files={name: (None, value) for name, value in fields.items()},
            ) as response:
                self.check(response)
                data = bytearray()
                began = time.perf_counter()
                async for chunk in response.aiter_bytes():
                    metrics.setdefault("first_ms", round((time.perf_counter() - began) * 1000))
                    data.extend(chunk)
                    if len(data) > 2_500_000:
                        raise NovaError("audio_limit", "NVIDIA audio exceeded the playback limit.")
            if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
                raise NovaError("audio_format", "NVIDIA did not return WAV audio.")
            self.cache_audio(key, bytes(data))
            return bytes(data)

    async def transcribe(self, wav):
        if not self.settings.voice_enabled:
            raise NovaError("voice_disabled", "Voice is disabled in the service configuration.")
        async with self.invocation(Capability.ASR, self.settings.stt_model, lane="speech"):
            response = await self.client.post(
                f"{self.settings.stt_base_url}/v1/audio/transcriptions", headers=self.headers(),
                files={"file": ("utterance.wav", wav, "audio/wav"), "language": (None, self.settings.tts_language)},
            )
            self.check(response)
            result = response.json()
            text = result.get("text")
            if isinstance(text, str):
                return text.strip()[:1400]
            transcripts = [row.get("alternatives", [{}])[0].get("transcript", "")
                           for row in result.get("results", []) if row.get("alternatives")]
            return " ".join(transcripts).strip()[:1400]

    async def stream_speech(self, text, voice=None):
        if self.tts_streaming:
            text, selected = await self.normalize_speech(text, voice)
            if not text:
                return
            key = self.audio_key("pcm", selected, text)
            if key in self.audio_cache:
                self.audio_cache.move_to_end(key)
                audio = self.audio_cache[key]
                self.store.log("voice", "Reused cached NVIDIA audio")
                for offset in range(0, len(audio), 6400):
                    yield "pcm", audio[offset:offset + 6400]
                return
            data = bytearray()
            model = self.settings.tts_model
            request = tts.SynthesizeSpeechRequest(
                text=text, voice_name=selected, language_code=self.settings.tts_language,
                encoding=AudioEncoding.LINEAR_PCM, sample_rate_hz=16000,
            )
            try:
                async with self.invocation(Capability.TTS, model, lane="speech") as metrics:
                    start = time.perf_counter()
                    stream = tts_grpc.RivaSpeechSynthesisStub(self.speech_channel()).SynthesizeOnline(
                        request, metadata=self.speech_metadata(self.settings.tts_base_url), timeout=18,
                    )
                    try:
                        async for packet in stream:
                            if not packet.audio:
                                continue
                            data.extend(packet.audio)
                            if len(data) > 1_000_000:
                                raise NovaError("audio_limit", "NVIDIA audio exceeded the playback limit.")
                            metrics.setdefault("first_ms", round((time.perf_counter() - start) * 1000))
                            for offset in range(0, len(packet.audio), 6400):
                                yield "pcm", packet.audio[offset:offset + 6400]
                    except grpc.aio.AioRpcError as exc:
                        raise self.speech_error(exc) from exc
                    finally:
                        stream.cancel()
                    if not data:
                        raise NovaError("empty_audio", "NVIDIA returned no speech audio.")
                self.cache_audio(key, bytes(data))
                return
            except NovaError as exc:
                if exc.code != "stream_unsupported" or data:
                    raise
                self.tts_streaming = False
                self.store.log("voice", "Magpie switched to utterance HTTP")
        audio = await self.synthesize(text, voice)
        if audio:
            yield "audio", audio

    async def recognize_stream(self, frames, on_partial):
        if not self.settings.voice_enabled or not self.asr_streaming:
            raise NovaError("stream_unsupported", "NVIDIA streaming speech recognition is disabled.")

        async def requests():
            config = asr.RecognitionConfig(
                encoding=AudioEncoding.LINEAR_PCM, sample_rate_hertz=16000,
                language_code=self.settings.tts_language, audio_channel_count=1,
                enable_automatic_punctuation=True,
            )
            yield asr.StreamingRecognizeRequest(
                streaming_config=asr.StreamingRecognitionConfig(config=config, interim_results=True),
            )
            while (frame := await frames.get()) is not None:
                yield asr.StreamingRecognizeRequest(audio_content=frame)

        async with self.invocation(Capability.ASR, self.settings.stt_model, lane="speech") as metrics:
            started = time.perf_counter()
            stream = asr_grpc.RivaSpeechRecognitionStub(self.speech_channel()).StreamingRecognize(
                requests(), metadata=self.speech_metadata(self.settings.stt_base_url), timeout=18,
            )
            final = []
            try:
                async for response in stream:
                    draft = []
                    for result in response.results:
                        if not result.alternatives:
                            continue
                        phrase = result.alternatives[0].transcript.strip()
                        if not phrase:
                            continue
                        metrics.setdefault("first_ms", round((time.perf_counter() - started) * 1000))
                        if result.is_final:
                            final.append(phrase)
                        else:
                            draft.append(phrase)
                    if final or draft:
                        await on_partial(" ".join(final + draft)[:1400])
            except grpc.aio.AioRpcError as exc:
                error = self.speech_error(exc)
                if error.code == "stream_unsupported":
                    self.asr_streaming = False
                    self.store.log("voice", "Parakeet switched to utterance HTTP")
                raise error from exc
            finally:
                stream.cancel()
            return " ".join(final).strip()[:1400]
