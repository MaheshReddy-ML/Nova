from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BOLT = "nvidia/nemotron-3.5-bolt-e4b"
SUPER = "nvidia/nemotron-3.5-super-vl-120b-a12b"
OMNI = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
EMBED = "nvidia/nemotron-3.5-embed-1b"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
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
    # Text to speech provider. "auto" uses Deepgram Aura when DEEPGRAM_API_KEY is set, otherwise NVIDIA Magpie.
    # If Deepgram fails mid-session (network, credits), Nova falls back to NVIDIA Magpie for that phrase.
    tts_provider: Literal["auto", "deepgram", "nvidia"] = "auto"
    deepgram_api_key: SecretStr = SecretStr("")
    deepgram_voice: str = Field("aura-2-athena-en", pattern=r"^aura(-2)?-[a-z]+-[a-z]{2}$")
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_owner_chat_id: str = ""
    wikidata_contact: str = ""
    google_places_api_key: SecretStr = SecretStr("")
    brave_search_api_key: SecretStr = SecretStr("")
    semantic_scholar_api_key: SecretStr = SecretStr("")
    # voice_bridge control API (voice_bridge/control.py): rings the owner's phone through ntfy for a live voice call.
    voice_bridge_url: str = Field("http://127.0.0.1:7861", pattern=r"^http://(127\.0\.0\.1|localhost):\d{2,5}$")
    # SMTP_* names are canonical; EMAIL_* names (Django-style) are accepted as aliases.
    smtp_host: str = Field("", validation_alias=AliasChoices("smtp_host", "email_host"))
    smtp_port: int = Field(587, ge=1, le=65535, validation_alias=AliasChoices("smtp_port", "email_port"))
    smtp_security: Literal["starttls", "ssl"] | None = None
    email_use_tls: bool | None = None
    email_use_ssl: bool | None = None
    smtp_username: str = Field("", validation_alias=AliasChoices("smtp_username", "email_user", "email_host_user"))
    smtp_password: SecretStr = Field(SecretStr(""), validation_alias=AliasChoices(
        "smtp_password", "email_pass", "email_password", "email_host_password"))
    smtp_from: str = Field("", validation_alias=AliasChoices("smtp_from", "email_from", "default_from_email"))
    admin_emails: str = ""
    owner_name: str = ""
    owner_title: str = ""
    owner_address: str = Field("", max_length=40)
    persona: Literal["jarvis", "neutral"] = "jarvis"
    wake_word: str = "hey_nova"
    wake_threshold: float = Field(0.5, ge=0.2, le=0.95)
    business_name: str = ""
    business_about: str = Field("", max_length=600)
    business_website: str = ""
    business_phone: str = ""
    # Country calling code added to 10-digit local numbers for WhatsApp links (91 = India). Digits only.
    default_country_code: str = Field("91", pattern=r"^[1-9][0-9]{0,3}$")
    brand_color: str = Field("#5b4bff", pattern=r"^#[0-9a-fA-F]{6}$")
    max_emails_hour: int = Field(10, ge=1, le=50)
    agent_model: str = SUPER
    site_builder: Literal["template", "model", "kit"] = "kit"
    site_model: str = SUPER
    site_revision_rounds: int = Field(1, ge=0, le=3)
    site_min_score: int = Field(65, ge=0, le=100)
    agent_max_steps: int = Field(5, ge=1, le=8)
    agent_input_tokens: int = Field(10000, ge=1024, le=32000)
    voice_enabled: bool = True
    speech_streaming: bool = True
    max_speech_calls_hour: int = Field(300, ge=1, le=1000)
    autonomous_mode: bool = False
    max_agent_steps: int = Field(25, ge=1, le=40)
    max_retries: int = Field(3, ge=0, le=5)
    max_daily_expense_inr: int = Field(0, ge=0, le=0)
    max_input_tokens: int = Field(4096, ge=512, le=8192)
    max_output_tokens: int = Field(1024, ge=64, le=4096)
    max_task_tokens: int = Field(200000, ge=64)
    max_daily_tokens: int = Field(3000000, ge=64)
    max_calls_hour: int = Field(600, ge=1, le=2400)
    max_task_model_calls: int = Field(20, ge=1, le=40)
    max_task_seconds: int = Field(600, ge=5, le=900)
    skill_context_budget: int = Field(550, ge=80, le=1500)
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
    def resolve_email(self):
        if self.smtp_security is None:
            if self.email_use_ssl or self.smtp_port == 465:
                self.smtp_security = "ssl"
            else:
                self.smtp_security = "starttls"
        password = self.smtp_password.get_secret_value()
        if "gmail" in self.smtp_host.lower() and " " in password:
            # Google shows app passwords in groups of four; SMTP expects them without spaces.
            self.smtp_password = SecretStr(password.replace(" ", ""))
        if "@" not in self.smtp_from and "@" in self.smtp_username:
            if self.smtp_from:
                import logging

                logging.getLogger("nova.config").warning("EMAIL_FROM is not a full email address; sending from EMAIL_USER instead")
            self.smtp_from = self.smtp_username
        return self

    @property
    def speech_provider(self) -> Literal["deepgram", "nvidia"]:
        key = self.deepgram_api_key.get_secret_value().strip()
        has_key = bool(key) and key.lower() not in {"your_deepgram_api_key", "your_deepgram_api_key_here", "replace_me"}
        if self.tts_provider == "deepgram" or (self.tts_provider == "auto" and has_key):
            return "deepgram"
        return "nvidia"

    @property
    def owner_emails(self) -> list[str]:
        return [item.strip() for item in self.admin_emails.split(",") if "@" in item.strip()][:5]

    @property
    def signature(self) -> str:
        lines = [self.owner_name.strip(), self.owner_title.strip(), self.business_name.strip(),
                 self.business_phone.strip(), self.business_website.strip()]
        lines = [line for line in lines if line]
        return "\n".join(lines) if lines else "Best regards"

    @property
    def sender_profile(self) -> str:
        """Who 'we' are, for outreach copy. Empty when the owner has not described the business."""
        parts = []
        if self.business_name:
            parts.append(f"Business: {self.business_name}")
        if self.owner_name:
            parts.append(f"Sender: {self.owner_name}" + (f", {self.owner_title}" if self.owner_title else ""))
        if self.business_about:
            parts.append(f"About us: {self.business_about}")
        if self.business_website:
            parts.append(f"Our website: {self.business_website}")
        if self.business_phone:
            parts.append(f"Our phone: {self.business_phone}")
        return "\n".join(parts)

    @model_validator(mode="after")
    def protect_external_actions(self):
        if not all((self.require_outreach_approval, self.require_deployment_approval, self.require_payment_approval)):
            raise ValueError("External business actions require approval")
        return self

    @property
    def release_version(self) -> str:
        return "2.0.0" if self.agent_version == "0.1.0" else self.agent_version
