from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class State(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING = "waiting_for_tool"
    VERIFYING = "verifying"
    RETRY = "retry_scheduled"
    PAUSED = "paused"
    COMPLETE = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = {State.COMPLETE, State.FAILED, State.CANCELLED}
ACTIVE = {State.PLANNING, State.RUNNING, State.WAITING, State.VERIFYING}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Candidate(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    url: str = Field(min_length=10, max_length=500)
    listed_by: str | None = Field(default=None, max_length=500)

    @field_validator("url", "listed_by")
    @classmethod
    def public_web_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
            raise ValueError("Provide a public HTTP(S) page URL without credentials, ports or queries")
        return value


class MissionInput(StrictModel):
    title: str = Field(min_length=3, max_length=140)
    workflow: Literal["website", "research", "topic", "brief"] = "website"
    candidates: list[Candidate] = Field(default_factory=list, max_length=5)
    directory_url: str | None = Field(default=None, min_length=10, max_length=500)
    business_search: str | None = Field(default=None, min_length=3, max_length=100)
    design_assist: bool = False
    prepare_contact: bool = False
    objective: str = Field(default="", max_length=1600)
    priority: Annotated[int, Field(ge=0, le=9)] = 5
    depends_on: str | None = Field(default=None, pattern=r"^[a-f0-9]{12}$")
    run_at: float | None = Field(default=None, ge=0, le=4102444800, allow_inf_nan=False)

    @model_validator(mode="after")
    def require_workflow_inputs(self):
        if self.workflow in {"website", "research"}:
            if sum(bool(value) for value in (self.candidates, self.directory_url, self.business_search)) != 1:
                raise ValueError("Provide one input method using a website list, a public directory, or a business search")
            if self.directory_url:
                Candidate.public_web_url(self.directory_url)
            if len({item.url.rstrip("/") for item in self.candidates}) != len(self.candidates):
                raise ValueError("Each website must be unique")
        elif not self.objective or self.candidates or self.directory_url or self.business_search or self.design_assist or self.prepare_contact:
            raise ValueError("This workflow requires an objective and accepts no website list")
        return self


class Brief(StrictModel):
    summary: str = Field(min_length=4, max_length=2000)
    assumptions: list[Annotated[str, Field(min_length=2, max_length=400)]] = Field(max_length=5)
    next_steps: list[Annotated[str, Field(min_length=2, max_length=400)]] = Field(min_length=1, max_length=5)


class DesignChoice(StrictModel):
    priority_index: int = Field(ge=0, le=2)
    focus: Literal["clarity", "readability", "next_step"]


class Control(StrictModel):
    action: Literal["pause", "resume", "cancel"]


class OwnerText(StrictModel):
    text: str = Field(min_length=1, max_length=1400)


class NovaError(Exception):
    def __init__(self, code: str, message: str, *, transient: bool = False, retry_after: float = 0):
        super().__init__(message)
        self.code = code
        self.transient = transient
        self.retry_after = retry_after
