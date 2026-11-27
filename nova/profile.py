"""The owner's profile: who NOVA works for. Stored locally in memory/profile.json (gitignored).

A compact version goes into every agent prompt so research, insights and outreach build on the owner's
current status, publications and goals. Contact details (phone, email) never enter model prompts.
"""
import json
from pathlib import Path

from pydantic import Field

from .domain import NovaError, StrictModel


class Link(StrictModel):
    label: str = Field(max_length=60)
    url: str = Field(max_length=300)


class Role(StrictModel):
    role: str = Field(max_length=140)
    org: str = Field(default="", max_length=140)
    period: str = Field(default="", max_length=60)
    points: list[str] = Field(default_factory=list, max_length=8)


class Publication(StrictModel):
    title: str = Field(max_length=240)
    venue: str = Field(default="", max_length=120)
    year: str = Field(default="", max_length=10)
    doi: str = Field(default="", max_length=120)


class Project(StrictModel):
    name: str = Field(max_length=120)
    summary: str = Field(default="", max_length=400)
    tech: list[str] = Field(default_factory=list, max_length=12)
    url: str = Field(default="", max_length=300)


class Profile(StrictModel):
    name: str = Field(default="", max_length=80)
    headline: str = Field(default="", max_length=160)
    location: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=40)
    links: list[Link] = Field(default_factory=list, max_length=8)
    summary: str = Field(default="", max_length=1500)
    status: str = Field(default="", max_length=600)
    focus: list[str] = Field(default_factory=list, max_length=12)
    experience: list[Role] = Field(default_factory=list, max_length=8)
    education: list[Role] = Field(default_factory=list, max_length=4)
    publications: list[Publication] = Field(default_factory=list, max_length=12)
    projects: list[Project] = Field(default_factory=list, max_length=12)
    skills: dict[str, list[str]] = Field(default_factory=dict)
    achievements: list[str] = Field(default_factory=list, max_length=10)
    goals: list[str] = Field(default_factory=list, max_length=10)
    agent_rules: list[str] = Field(default_factory=list, max_length=10)
    updated: float = 0


class Profiles:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Profile:
        if not self.path.is_file():
            return Profile()
        try:
            return Profile.model_validate_json(self.path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise NovaError("profile_invalid", "memory/profile.json could not be read. Fix or remove it.") from exc

    def save(self, profile: Profile) -> Profile:
        import time

        profile.updated = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self.path)
        return profile


def compact(profile: Profile, limit=1800) -> str:
    """Prompt-sized summary, most important first. Excludes phone and email."""
    if not profile.name:
        return ""
    lines = [f"Owner: {profile.name} — {profile.headline}" + (f" ({profile.location})" if profile.location else "")]
    if profile.agent_rules:
        lines.append("How to work for them: " + " ".join(profile.agent_rules))
    if profile.status:
        lines.append(f"Current status: {profile.status}")
    if profile.goals:
        lines.append("Goals: " + "; ".join(profile.goals))
    if profile.publications:
        lines.append("Publications: " + "; ".join(item.title.split(":")[0] for item in profile.publications[:4]))
    if profile.projects:
        lines.append("Key projects: " + ", ".join(item.name for item in profile.projects[:6]))
    if profile.focus:
        lines.append("Focus areas: " + ", ".join(profile.focus))
    return "\n".join(lines)[:limit]


def detail(profile: Profile) -> dict:
    """Full profile for the agent's get_owner_profile tool, without phone number."""
    data = profile.model_dump(exclude={"phone", "updated"})
    return data
