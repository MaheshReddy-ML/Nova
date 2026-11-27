from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BOLT = "nvidia/nemotron-3.5-bolt-e4b"
SUPER = "nvidia/nemotron-3.5-super-vl-120b-a12b"
OMNI = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
EMBED = "nvidia/nemotron-3.5-embed-1b"
ASR_HOST = "https://1598d209-5e27-4d3c-8079-4751568b1081.invocation.api.nvcf.nvidia.com"
TTS_HOST = "https://877104f7-e885-42b9-8de8-f6e4c6303969.invocation.api.nvcf.nvidia.com"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_name: str = "NOVA"
    agent_version: str = "0.1.0"
    app_env: str = "development"
    nvidia_api_key: SecretStr = SecretStr("")
    nvidia_base_url: str = NVIDIA_URL
    fast_model: str = BOLT
    planner_model: str = BOLT
    reasoning_model: str = SUPER
    coding_model: str = SUPER
    vision_model: str = OMNI
    embedding_model: str = EMBED
    stt_model: str = "parakeet-ctc-1.1b-asr"
    stt_base_url: str = ASR_HOST
    tts_model: str = "magpie-tts-multilingual"
    tts_voice: str = "Magpie-Multilingual.EN-US.Sofia"
    tts_language: str = "en-US"
    tts_base_url: str = TTS_HOST
    voice_enabled: bool = True
    speech_streaming: bool = True
    max_speech_calls_hour: int = Field(36, ge=1, le=180)
    autonomous_mode: bool = False
    max_agent_steps: int = Field(25, ge=1, le=40)
    max_retries: int = Field(3, ge=0, le=5)
    max_daily_expense_inr: int = Field(0, ge=0, le=0)
    max_input_tokens: int = Field(4096, ge=512, le=8192)
    max_output_tokens: int = Field(1024, ge=64, le=4096)
    max_task_tokens: int = Field(12000, ge=64)
    max_daily_tokens: int = Field(50000, ge=64)
    max_calls_hour: int = Field(30, ge=1, le=120)
    max_task_model_calls: int = Field(6, ge=1, le=15)
    max_task_seconds: int = Field(180, ge=5, le=900)
    workers: int = Field(2, ge=1, le=4)
    require_outreach_approval: bool = True
    require_deployment_approval: bool = True
    require_payment_approval: bool = True
    database_path: Path = Path("memory/nova.db")
    workspace_path: Path = Path("workspace")
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = Field(8000, ge=1024, le=65535)

    @field_validator("host")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        if value != "127.0.0.1":
            raise ValueError("NOVA binds only to 127.0.0.1")
        return value

    @field_validator("nvidia_base_url")
    @classmethod
    def catalog_host(cls, value: str) -> str:
        if value.rstrip("/") != NVIDIA_URL:
            raise ValueError("Use the NVIDIA Build trial gateway")
        return NVIDIA_URL

    @field_validator("tts_base_url", "stt_base_url")
    @classmethod
    def speech_host(cls, value: str) -> str:
        url = urlsplit(value.rstrip("/"))
        suffix = ".invocation.api.nvcf.nvidia.com"
        try:
            function = url.netloc.removesuffix(suffix)
            valid = str(UUID(function)) == function and url.netloc == function + suffix
        except ValueError:
            valid = False
        if not valid or (url.scheme, url.path, url.query, url.fragment) != ("https", "", "", ""):
            raise ValueError("Use a documented NVIDIA NVCF HTTPS speech function URL")
        return value.rstrip("/")

    @model_validator(mode="after")
    def protect_external_actions(self):
        if not all((self.require_outreach_approval, self.require_deployment_approval, self.require_payment_approval)):
            raise ValueError("External business actions require approval")
        return self
