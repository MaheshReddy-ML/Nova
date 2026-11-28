from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from yaml.tokens import AliasToken, AnchorToken

from ..domain import NovaError

NAME = r"[a-z0-9]+(?:-[a-z0-9]+)*"
SHA = r"^[0-9a-f]{40}$"
ROLE = r"^[a-z]+:[a-z_]+$"
LICENSE_MARKERS = {
    "MIT": ("Permission is hereby granted, free of charge", "The above copyright notice"),
    "Apache-2.0": ("Apache License", "Version 2.0, January 2004"),
    "BSD-3-Clause": ("Redistribution and use in source and binary forms", "Neither the name"),
    "CC0-1.0": ("CC0 1.0 Universal", "Waiver"),
}
TEXT_TYPES = {".md", ".txt", ".csv", ".json", ".yaml", ".yml"}
FILE_LIMIT = 256_000
FRONTMATTER_LIMIT = 12_000
MAX_REFERENCE_BYTES = 2400
PRIVILEGE_OVERRIDE = re.compile(
    r"(?i)ignore (?:all |any |the )?(?:previous|prior|system) (?:instructions|rules)"
    r"|(?:reveal|exfiltrate) (?:all |the |any )?(?:credentials|system prompt)"
    r"|(?:disable|bypass) (?:permission checks|security policies|security controls)"
    r"|<\s*/?\s*(?:system|developer)\s*>"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS installed_skills (
    skill_id TEXT PRIMARY KEY, revision TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    installed_at REAL NOT NULL, validated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_revision_history (
    id INTEGER PRIMARY KEY, skill_id TEXT NOT NULL, from_revision TEXT NOT NULL,
    to_revision TEXT NOT NULL, applied_at REAL NOT NULL, reverted_at REAL
);
CREATE TABLE IF NOT EXISTS skill_activations (
    id INTEGER PRIMARY KEY, task_id TEXT, stage TEXT NOT NULL, skill_id TEXT NOT NULL,
    revision TEXT NOT NULL, estimated_tokens INTEGER NOT NULL, injected_tokens INTEGER NOT NULL,
    activated_at REAL NOT NULL, outcome TEXT
);
CREATE INDEX IF NOT EXISTS skill_activations_task ON skill_activations(task_id, stage);
CREATE INDEX IF NOT EXISTS skill_activations_skill ON skill_activations(skill_id);
"""


def safe_parts(path):
    parts = PurePosixPath(path).parts
    if (not parts or str(PurePosixPath(path)) != path or path.startswith("/")
            or "\\" in path or any(not re.fullmatch(r"[A-Za-z0-9._-]+", part)
                                      or part in {".", ".."} for part in parts)):
        raise NovaError("skill_path", "A skill path is outside its approved package.")
    return parts


def read_bounded(root, relative, limit=FILE_LIMIT):
    """Open each directory and the leaf without following symbolic links."""
    parts = safe_parts(relative)
    try:
        directory = os.open(root, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY)
        try:
            return _read_at(directory, parts, limit)
        finally:
            os.close(directory)
    except OSError as exc:
        raise NovaError("skill_file", "An approved skill file could not be read safely.") from exc


def _read_at(root_fd, parts, limit):
    folder = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=folder)
            os.close(folder)
            folder = child
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(parts[-1], flags, dir_fd=folder), "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
                raise NovaError("skill_file", "An approved skill file is not a bounded text file.")
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise NovaError("skill_file", "An approved skill file exceeds its size limit.")
            return data
    finally:
        os.close(folder)


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileSpec(ManifestModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_path: str | None = None
    bytes: int = Field(ge=1, le=FILE_LIMIT)


class Revision(ManifestModel):
    revision: str = Field(pattern=SHA)
    version: str = Field(min_length=1, max_length=40)
    license: str
    license_file: str
    upstream_name: str = Field(pattern=f"^{NAME}$", max_length=64)
    source_path: str
    reviewed_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    files: dict[str, FileSpec] = Field(min_length=3, max_length=25)
    guide_sources: list[str] = Field(min_length=1, max_length=7)
    # Upstream Claude Code tool grants (e.g. "Read Write Bash") recorded at review time and never granted by NOVA.
    ignored_tool_grants: str | None = Field(default=None, max_length=200)
    evaluation: str = Field(min_length=1, max_length=380)


class Skill(ManifestModel):
    skill_id: str = Field(pattern=f"^{NAME}$", max_length=64)
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=260)
    source: str = Field(pattern=r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    category: str = Field(pattern=f"^{NAME}$", max_length=40)
    roles: list[str] = Field(min_length=1, max_length=12)
    keywords: list[str] = Field(default_factory=list, max_length=12)
    priority: int = Field(default=0, ge=0, le=50)
    permissions: list[str] = Field(default_factory=lambda: ["local-reference"])
    dependencies: list[str] = Field(default_factory=list)
    default_revision: str = Field(pattern=SHA)
    default_enabled: bool = False
    revisions: list[Revision] = Field(min_length=1, max_length=12)


class Manifest(ManifestModel):
    schema_version: int = Field(ge=1, le=1)
    skills: list[Skill] = Field(min_length=1, max_length=120)


class StrictYaml(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise yaml.YAMLError("Duplicate or non-string frontmatter key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def parse_frontmatter(raw, expected_name):
    try:
        markdown = raw.decode("utf-8-sig")
        lines = markdown.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("Missing frontmatter")
        end = next(index for index, line in enumerate(lines[1:120], 1) if line.strip() == "---")
        frontmatter = "\n".join(lines[1:end])
        if (len(frontmatter.encode()) > FRONTMATTER_LIMIT
                or any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(frontmatter))):
            raise ValueError("Unsupported frontmatter")
        data = yaml.load(frontmatter, Loader=StrictYaml)
    except (UnicodeError, ValueError, StopIteration, yaml.YAMLError) as exc:
        raise NovaError("skill_format", "The skill frontmatter failed validation.") from exc
    if (not isinstance(data, dict) or data.get("name") != expected_name
            or not re.fullmatch(NAME, expected_name) or len(expected_name) > 64):
        raise NovaError("skill_format", "The skill name does not match its approved directory.")
    description = data.get("description")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        raise NovaError("skill_format", "The skill description is invalid.")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict) or len(json.dumps(metadata, default=str)) > 2000:
        raise NovaError("skill_format", "Skill metadata must be a small mapping.")
    for key, maximum in (("license", 200), ("compatibility", 500), ("allowed-tools", 500)):
        if key in data and (not isinstance(data[key], str) or len(data[key]) > maximum):
            raise NovaError("skill_format", f"The skill {key} field is invalid.")
    if not "\n".join(lines[end + 1:]).strip():
        raise NovaError("skill_format", "The skill has no Markdown instructions.")
    return data, markdown


@dataclass(frozen=True)
class SkillGuide:
    skill_id: str
    title: str
    revision: str
    instructions: str
    estimated_tokens: int


class SkillRegistry:
    def __init__(self, db: sqlite3.Connection, *, context_budget=600, manifest=None, library=None):
        self.db = db
        self.context_budget = max(0, min(context_budget, 4096))
        base = Path(__file__).parent
        manifest_path = Path(manifest) if manifest is not None else base / "skills.lock.json"
        self.library = Path(library) if library is not None else base / "library"
        try:
            manifest_bytes = read_bounded(manifest_path.parent, manifest_path.name)
            catalog = Manifest.model_validate_json(manifest_bytes)
        except (ValidationError, ValueError) as exc:
            raise NovaError("skill_manifest", "The local skill catalogue is invalid.") from exc
        self.catalog = {item.skill_id: item for item in catalog.skills}
        if len(self.catalog) != len(catalog.skills):
            raise NovaError("skill_manifest", "The local catalogue contains duplicate skill identifiers.")
        self.revisions = {}
        for skill in catalog.skills:
            revisions = {item.revision: item for item in skill.revisions}
            if len(revisions) != len(skill.revisions) or skill.default_revision not in revisions:
                raise NovaError("skill_manifest", "The skill catalogue contains an invalid revision list.")
            if not all(re.fullmatch(ROLE, role) for role in skill.roles):
                raise NovaError("skill_manifest", "The local catalogue contains an invalid activation role.")
            self.revisions[skill.skill_id] = revisions
        self.cache = {}
        self.errors = {}
        self.db.executescript(SCHEMA)
        with self.db:
            self.db.execute("UPDATE skill_activations SET outcome='interrupted' WHERE outcome IS NULL")
            for skill in catalog.skills:
                if skill.default_enabled and self._installed(skill.skill_id) is None:
                    try:
                        self._set_installed(skill, skill.default_revision, True)
                    except NovaError as exc:
                        self.errors[(skill.skill_id, skill.default_revision)] = exc.code

    def _skill(self, skill_id):
        if skill_id not in self.catalog:
            raise NovaError("skill_missing", "That skill is outside NOVA's reviewed catalogue.")
        return self.catalog[skill_id]

    def _installed(self, skill_id):
        return self.db.execute("SELECT revision,enabled,installed_at,validated_at FROM installed_skills WHERE skill_id=?",
                               (skill_id,)).fetchone()

    def _revision(self, skill, revision):
        if revision not in self.revisions[skill.skill_id]:
            raise NovaError("skill_revision", "That revision is outside NOVA's reviewed catalogue.")
        return self.revisions[skill.skill_id][revision]

    def _file(self, skill, revision, path, *, limit=FILE_LIMIT):
        safe_parts(path)
        file = revision.files.get(path)
        if file is None:
            raise NovaError("skill_file", "That file is outside the reviewed skill package.")
        relative = f"{skill.skill_id}/{revision.revision}/{revision.upstream_name}/{path}"
        raw = read_bounded(self.library, relative, limit)
        if len(raw) != file.bytes or hashlib.sha256(raw).hexdigest() != file.sha256:
            raise NovaError("skill_integrity", "A skill file no longer matches its reviewed hash.")
        return raw

    def _verify(self, skill, revision):
        if revision.license not in LICENSE_MARKERS:
            raise NovaError("skill_license", "The skill license is outside the approved set.")
        if skill.permissions != ["local-reference"] or skill.dependencies:
            raise NovaError("skill_permissions", "The skill requires capabilities beyond its approved reference access.")
        if not {"SKILL.md", "GUIDE.md", revision.license_file} <= revision.files.keys():
            raise NovaError("skill_manifest", "The skill package is missing its required reviewed files.")
        if revision.files["SKILL.md"].source_path != revision.source_path:
            raise NovaError("skill_manifest", "The skill entrypoint is missing an upstream source mapping.")
        source_files = {}
        for path, entry in revision.files.items():
            parts = safe_parts(path)
            if "scripts" in parts or (Path(path).suffix.lower() not in TEXT_TYPES and path != revision.license_file):
                raise NovaError("skill_script", "Executable and binary skill files cannot be installed.")
            if entry.source_path is not None:
                safe_parts(entry.source_path)
            try:
                source_files[path] = self._file(skill, revision, path).decode("utf-8-sig")
            except UnicodeError as exc:
                raise NovaError("skill_file", "Only reviewed UTF-8 skill files can be installed.") from exc
        metadata, _ = parse_frontmatter(source_files["SKILL.md"].encode(), revision.upstream_name)
        grants = metadata.get("allowed-tools", "").strip()
        if grants and grants != (revision.ignored_tool_grants or "").strip():
            raise NovaError("skill_permissions", "Upstream tool grants require separate owner review.")
        declared = metadata.get("license", "").strip()
        if declared and declared != revision.license and not declared.startswith(revision.license + " "):
            # Some skills point at the adjacent terms rather than naming the SPDX identifier.
            if not re.search(r"(?i)license\.\w+", declared):
                raise NovaError("skill_license", "The skill frontmatter disagrees with the approved license.")
        if not all(marker in source_files[revision.license_file] for marker in LICENSE_MARKERS[revision.license]):
            raise NovaError("skill_license", "The bundled license text failed validation.")
        if any(path not in source_files or not revision.files[path].source_path for path in revision.guide_sources):
            raise NovaError("skill_manifest", "The compiled guide lacks valid source mappings.")
        approved_sources = [source_files[path] for path in revision.guide_sources]
        guide = source_files["GUIDE.md"].strip()
        if (not guide or len(guide.encode()) > 4096
                or any(PRIVILEGE_OVERRIDE.search(value) for value in [guide, *approved_sources])):
            raise NovaError("skill_untrusted", "The skill contains instructions that failed privilege review.")
        self.cache[(skill.skill_id, revision.revision)] = guide
        self.errors.pop((skill.skill_id, revision.revision), None)
        return guide

    def _validate(self, skill, revision):
        key = (skill.skill_id, revision.revision)
        try:
            return self._verify(skill, revision)
        except NovaError as exc:
            self.cache.pop(key, None)
            self.errors[key] = exc.code
            raise

    def _set_installed(self, skill, revision, enabled):
        selected = self._revision(skill, revision)
        self._validate(skill, selected)
        now = time.time()
        self.db.execute(
            """INSERT INTO installed_skills VALUES(?,?,?,?,?)
               ON CONFLICT(skill_id) DO UPDATE SET revision=excluded.revision, enabled=excluded.enabled,
               validated_at=excluded.validated_at""",
            (skill.skill_id, revision, bool(enabled), now, now),
        )

    def _summary(self, skill, stats):
        installed = self._installed(skill.skill_id)
        revision_id = installed[0] if installed else skill.default_revision
        revision = self.revisions[skill.skill_id].get(revision_id)
        # An old installed revision without packaged files stays discoverable until the owner selects a new review.
        quarantined = revision is None or (skill.skill_id, revision_id) in self.errors
        metadata = revision or self._revision(skill, skill.default_revision)
        enabled = bool(installed and installed[1] and not quarantined)
        return {
            "id": skill.skill_id, "skill_id": skill.skill_id, "title": skill.title, "name": metadata.upstream_name,
            "description": skill.description, "category": skill.category, "source": skill.source,
            "source_path": metadata.source_path, "revision": revision_id, "version": metadata.version,
            "license": metadata.license, "installed": installed is not None, "enabled": enabled,
            "installed_at": installed[2] if installed else None,
            "validated_at": installed[3] if installed else None,
            "reviewed_on": metadata.reviewed_on, "evaluation": metadata.evaluation,
            "status": "quarantined" if quarantined else "enabled" if enabled else "disabled" if installed else "available",
            "permissions": skill.permissions, "dependencies": skill.dependencies, "roles": skill.roles,
            "references": sorted(path for path in metadata.files if path.startswith(("references/", "assets/"))),
            "source_estimated_tokens": metadata.files["SKILL.md"].bytes if "SKILL.md" in metadata.files else None,
            "guide_estimated_tokens": metadata.files["GUIDE.md"].bytes + 15 if "GUIDE.md" in metadata.files else None,
            "stats": stats,
        }

    def _stats(self, skill_id=None):
        where = "WHERE skill_id=?" if skill_id is not None else ""
        arguments = (skill_id,) if skill_id is not None else ()
        return {row[0]: {
            "uses": row[1], "successes": row[2], "failures": row[3], "estimated_tokens": row[4], "latest_at": row[5],
            "success_rate": row[2] / (row[2] + row[3]) if row[2] + row[3] else None,
        } for row in self.db.execute(
            f"""SELECT skill_id,COUNT(*),SUM(CASE WHEN outcome='passed' THEN 1 ELSE 0 END),
                     SUM(CASE WHEN outcome='failed' THEN 1 ELSE 0 END),SUM(injected_tokens),MAX(activated_at)
                 FROM skill_activations {where} GROUP BY skill_id""", arguments)}

    @staticmethod
    def empty_stats():
        return {"uses": 0, "successes": 0, "failures": 0, "estimated_tokens": 0, "latest_at": None,
                "success_rate": None}

    def list(self, query=""):
        terms = query.lower().split()[:12]
        stats = self._stats()
        return [self._summary(skill, stats.get(skill.skill_id, self.empty_stats()))
                for skill in sorted(self.catalog.values(), key=lambda item: (item.category, item.title))
                if all(term in " ".join((skill.title, skill.skill_id, skill.description, skill.category,
                                         *skill.roles, *skill.keywords)).casefold() for term in terms)]

    def inspect(self, skill_id):
        skill = self._skill(skill_id)
        summary = self._summary(skill, self._stats(skill_id).get(skill_id, self.empty_stats()))
        revision = self.revisions[skill_id].get(summary["revision"])
        rollback = self.db.execute(
            """SELECT from_revision FROM skill_revision_history
               WHERE skill_id=? AND to_revision=? AND reverted_at IS NULL ORDER BY id DESC LIMIT 1""",
            (skill_id, summary["revision"]),
        ).fetchone()
        summary.update(
            available_revisions=[{"revision": item.revision, "version": item.version,
                                  "reviewed_on": item.reviewed_on} for item in skill.revisions],
            rollback_revision=rollback[0] if rollback else None,
            files={path: value.model_dump() for path, value in (revision.files.items() if revision else [])},
            guide_sources=revision.guide_sources if revision else [],
        )
        return summary

    def evaluate(self, skill_id):
        skill = self._skill(skill_id)
        installed = self._installed(skill_id)
        revision = self._revision(skill, installed[0] if installed else skill.default_revision)
        guide = self._validate(skill, revision)
        estimate = len(guide.encode()) + 16
        return {"skill_id": skill_id, "revision": revision.revision, "verification": "passed",
                "source_estimated_tokens": revision.files["SKILL.md"].bytes, "guide_estimated_tokens": estimate,
                "context_budget": self.context_budget, "fits": estimate <= self.context_budget,
                "roles": skill.roles, "evaluation": revision.evaluation}

    def mutate(self, skill_id, action, revision=None):
        skill = self._skill(skill_id)
        installed = self._installed(skill_id)
        if action not in {"install", "enable", "disable", "update", "rollback"}:
            raise NovaError("skill_action", "That skill action is unsupported.")
        if revision is not None and action not in {"install", "update"}:
            raise NovaError("skill_action", "Only installation and updates accept an explicit revision.")
        with self.db:
            if action == "install":
                if installed and revision and installed[0] != revision:
                    raise NovaError("skill_action", "Use an update to change an installed revision.")
                if installed is None:
                    self._set_installed(skill, revision or skill.default_revision, False)
            elif installed is None:
                raise NovaError("skill_install", "Install the reviewed skill before changing it.")
            elif action == "enable":
                self._set_installed(skill, installed[0], True)
            elif action == "disable":
                self.db.execute("UPDATE installed_skills SET enabled=0 WHERE skill_id=?", (skill_id,))
            elif action == "update":
                next_revision = revision or skill.default_revision
                self._set_installed(skill, next_revision, bool(installed[1]))
                if next_revision != installed[0]:
                    self.db.execute(
                        """INSERT INTO skill_revision_history(skill_id,from_revision,to_revision,applied_at)
                           VALUES(?,?,?,?)""", (skill_id, installed[0], next_revision, time.time()),
                    )
            else:
                previous = self.db.execute(
                    """SELECT id,from_revision FROM skill_revision_history
                       WHERE skill_id=? AND to_revision=? AND reverted_at IS NULL ORDER BY id DESC LIMIT 1""",
                    (skill_id, installed[0]),
                ).fetchone()
                if previous is None:
                    raise NovaError("skill_rollback", "There is no earlier installed revision to restore.")
                self._set_installed(skill, previous[1], bool(installed[1]))
                self.db.execute("UPDATE skill_revision_history SET reverted_at=? WHERE id=?", (time.time(), previous[0]))
        return self.inspect(skill_id)

    def reference(self, skill_id, path, heading=None):
        skill = self._skill(skill_id)
        safe_parts(path)
        installed = self._installed(skill_id)
        if installed is None:
            raise NovaError("skill_install", "Install this reviewed skill before reading its references.")
        revision = self._revision(skill, installed[0])
        if path not in {"SKILL.md", "GUIDE.md", revision.license_file, "NOTICE.md"} and not path.startswith(("references/", "assets/")):
            raise NovaError("skill_file", "Only approved reference and attribution files can be inspected.")
        try:
            text = self._file(skill, revision, path).decode("utf-8-sig")
        except UnicodeError as exc:
            raise NovaError("skill_file", "The skill reference is not valid UTF-8 text.") from exc
        if heading is not None:
            pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
            lines = text.splitlines()
            match = next(((index, len(heading_match.group(1))) for index, line in enumerate(lines)
                          if (heading_match := pattern.fullmatch(line))
                          and heading_match.group(2).casefold() == heading.casefold()), None)
            if match is None:
                raise NovaError("skill_heading", "The requested reference section is unavailable.")
            start, level = match
            end = next((index for index in range(start + 1, len(lines))
                        if (header := pattern.fullmatch(lines[index])) and len(header.group(1)) <= level), len(lines))
            text = "\n".join(lines[start:end])
        raw = text.encode()
        return {"skill_id": skill_id, "revision": revision.revision, "path": path,
                "text": raw[:MAX_REFERENCE_BYTES].decode(errors="ignore"), "truncated": len(raw) > MAX_REFERENCE_BYTES}

    def resolve(self, workflow, stage, objective=""):
        if stage.startswith("audit_"):
            stage = "audit"
        role = f"{workflow}:{stage}"
        normalized = objective[:600].casefold()
        ranked = sorted(
            (skill for skill in self.catalog.values() if role in skill.roles),
            key=lambda item: (-(item.priority + sum(keyword in normalized for keyword in item.keywords) * 2),
                              item.skill_id),
        )
        remaining = self.context_budget
        active = []
        for skill in ranked:
            if len(active) >= 3 or remaining <= 0:
                break
            installed = self._installed(skill.skill_id)
            if not installed or not installed[1]:
                continue
            revision_id = installed[0]
            entry = (skill.skill_id, revision_id)
            if entry in self.errors:
                continue
            try:
                guide = self.cache.get(entry)
                if guide is None:
                    guide = self._validate(skill, self._revision(skill, revision_id))
            except NovaError as exc:
                self.errors[entry] = exc.code
                continue
            estimate = len(guide.encode()) + 16  # Conservative tokenizer-independent upper bound.
            if estimate <= remaining:
                remaining -= estimate
                active.append(SkillGuide(skill.skill_id, skill.title, revision_id, guide, estimate))
        return active

    # Function words and conversational filler. Without this list, "what", "this" or "find" matched skills on their own
    # (e.g. "what's the weather" offered six marketing playbooks).
    STOPWORDS = frozenset("""
        about after again also and any are because been before being both but can could did does doing done each else
        every few find for from get give got had has have having help her here hers him his how into its just let like
        make many more most much must need now off once only other our ours out over own please really same she should
        show some such tell than that the their them then there these they this those through too under until upon very
        want was way were what when where which while who whom why will with would you your yours hey nova okay thanks
        thank something anything everything someone
    """.split())

    @classmethod
    def _stems(cls, text, minimum=3):
        stems = set()
        for word in re.findall(rf"[a-z]{{{minimum},}}", text.casefold()):
            if word in cls.STOPWORDS:
                continue
            for suffix in ("ations", "ation", "ing", "ers", "ies", "es", "ed", "er", "s"):
                if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                    word = word[: -len(suffix)] + ("y" if suffix == "ies" else "")
                    # debugging -> debugg -> debug, planning -> plann -> plan, so they meet "debug" and "plan".
                    if suffix in {"ing", "ed", "er", "ers"} and len(word) > 3 and word[-1] == word[-2] \
                            and word[-1] not in "aeiouls":
                        word = word[:-1]
                    break
            if word.endswith("e") and len(word) > 4:
                word = word[:-1]
            if word not in cls.STOPWORDS:
                stems.add(word)
        return stems

    def _agent_index(self):
        if getattr(self, "_index", None) is None:
            import math

            documents = {}
            for skill in self.catalog.values():
                if any(role.startswith("agent:") for role in skill.roles):
                    name = self._stems(skill.skill_id.replace("-", " ") + " " + skill.title)
                    body = self._stems(skill.description + " " + " ".join(skill.keywords), 4)
                    documents[skill.skill_id] = (name, body)
            frequency = {}
            for name, body in documents.values():
                for word in name | body:
                    frequency[word] = frequency.get(word, 0) + 1
            total = max(1, len(documents))
            self._index = (documents, {word: math.log(1 + total / count) for word, count in frequency.items()})
        return self._index

    def agent_catalog(self, query, limit=6):
        """Enabled agent-loadable skills ranked by IDF-weighted overlap with the request; empty when nothing is relevant."""
        words = self._stems(query or "")
        if not words:
            return []
        documents, weight = self._agent_index()
        ranked = []
        for skill_id, (name, body) in documents.items():
            installed = self._installed(skill_id)
            if not installed or not installed[1] or (skill_id, installed[0]) in self.errors:
                continue
            score = sum(3 * weight[word] for word in words & name) + sum(weight[word] for word in (words & body) - name)
            if score > 0:
                skill = self.catalog[skill_id]
                hint = re.split(r"(?<=[.;:])\s|\. Use", skill.description)[0]
                if len(hint) > 90:  # Cut at a word boundary so the system prompt never shows half a word.
                    hint = hint[:90].rsplit(" ", 1)[0] + "…"
                hint = hint.rstrip(" .,;:")
                ranked.append((score, skill.priority, skill_id, hint))
        if not ranked:
            return []
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
        cutoff = ranked[0][0] * 0.35
        return [{"id": skill_id, "hint": hint} for score, _, skill_id, hint in ranked[:limit] if score >= cutoff]

    def agent_guide(self, skill_id):
        """The validated compiled guide of one enabled skill, for on-demand loading by the agent."""
        skill = self._skill(skill_id)
        installed = self._installed(skill_id)
        if not installed or not installed[1]:
            raise NovaError("skill_disabled", f"The {skill_id} skill is not enabled. Enable it in the Skills Observatory.")
        entry = (skill_id, installed[0])
        guide = self.cache.get(entry) or self._validate(skill, self._revision(skill, installed[0]))
        return SkillGuide(skill_id, skill.title, installed[0], guide, len(guide.encode()) + 16)

    def record(self, task_id, stage, guides, *, injected=False):
        if not guides:
            return
        with self.db:
            self.db.executemany(
                """INSERT INTO skill_activations(task_id,stage,skill_id,revision,estimated_tokens,injected_tokens,activated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                [(task_id, stage, guide.skill_id, guide.revision, guide.estimated_tokens,
                  guide.estimated_tokens if injected else 0, time.time()) for guide in guides],
            )

    def finish(self, task_id, stage, outcome):
        if outcome not in {"passed", "failed", "paused", "cancelled"}:
            raise ValueError("Unsupported skill activation outcome")
        with self.db:
            self.db.execute("UPDATE skill_activations SET outcome=? WHERE task_id IS ? AND stage=? AND outcome IS NULL",
                            (outcome, task_id, stage))

    def observed(self, task_id):
        rows = self.db.execute(
            """SELECT stage,skill_id,revision,estimated_tokens,injected_tokens,activated_at,outcome
               FROM skill_activations WHERE task_id IS ? ORDER BY id""", (task_id,),
        )
        keys = ("stage", "skill_id", "revision", "estimated_tokens", "injected_tokens", "activated_at", "outcome")
        return [dict(zip(keys, row)) for row in rows]
