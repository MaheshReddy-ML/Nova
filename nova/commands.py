import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field

from .domain import Candidate, MissionInput, NovaError, StrictModel
from .gateway import Capability
from .store import encoded

URL = re.compile(r"https?://[^\s<>]+|(?<![@\w])(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|in|co|io|dev|ai|edu|gov)(?:/[^\s<>]*)?", re.I)
FOLLOW_UP = re.compile(r"^(?:it|them|this|that|this website|the site|the website|this project|the project|the business)$", re.I)
REQUEST = re.compile(r"\b(?:audit|review|make|build|create|research|investigate|inspect|check|look up|find|draft|prepare|contact|email|reach out|send|open|show|pause|resume|cancel)\b", re.I)
FILLER = {"a", "an", "us", "for", "me", "what", "which", "where", "did", "do", "you", "on", "find", "found", "know",
          "about", "this", "that", "the", "site", "website", "project", "business", "tell", "and", "is", "was",
          "audit", "review", "research", "proposal", "scope", "changes", "show", "your", "much", "how", "summary"}


def search_words(text):
    return [word for word in re.findall(r"\w+", text.casefold()) if word not in FILLER]


def spoken_match(words, name):
    spoken = "".join(words)
    return len(spoken) >= 6 and spoken in "".join(search_words(name))


class Command(StrictModel):
    action: Literal["answer", "knowledge", "research", "audit", "build", "contact", "draft", "open", "brief", "pause", "resume", "cancel"]
    target: str = Field(max_length=300)
    follow_up: Literal["none", "contact"] = "none"


@dataclass
class ActionResult:
    text: str
    task_id: str | None = None
    draft_id: str | None = None
    view: str | None = None


def classify(text):
    normalized = re.sub(r"^(?:(?:hey )?nova[, ]+|please +|(?:can|could|would) you +|go ahead and +)+", "",
                        text.strip(), flags=re.I).strip(" ?.!")
    lowered = normalized.casefold()
    if re.search(r"\b(?:what|tell me|summarize|explain|how)\b", lowered) and re.search(r"\b(?:website|project|research|findings|proposal|audit|price|find)\b", lowered):
        return Command(action="knowledge", target=normalized)
    follow_up = "none"
    match = re.search(r"\s+(?:and|then)\s+(?:contact|email|reach out to)\s+(?:them|the business)\s*$", normalized, re.I)
    if match:
        normalized = normalized[:match.start()]
        follow_up = "contact"
    patterns = {
        "contact": r"(?:contact|email|reach out to|send (?:the |an? )?(?:email|proposal) to)\s+(.+)",
        "draft": r"(?:draft|prepare|write)\s+(?:an? |the )?(?:email|outreach|introduction)(?:\s+(?:to|for|about))?\s*(.*)",
        "build": r"(?:build|create|make)\s+(?:(?:me|us)\s+)?(?:(?:a|an|new|the|this)\s+)*(?:website|site|website demo|demo website)(?:\s+(?:for|of|from|using))?\s*(.*)",
        "audit": r"(?:audit|review|check|inspect|analyze)\s+(?:the website (?:for|of)\s+)?(.+)",
        "research": r"(?:research|investigate|look up|find information (?:on|about)|find out (?:about|more about))\s+(.+)",
        "open": r"(?:open|show(?: me)?)\s+(.+)",
    }
    for action, pattern in patterns.items():
        if match := re.fullmatch(pattern, normalized, re.I):
            return Command(action=action, target=match.group(1)[:300], follow_up=follow_up)
    return None


def planned_command(text):
    if match := re.fullmatch(r"\s*(?:should we|what if we|could we)\s+(.+?)\s*\?*\s*", text, re.I):
        instruction = match[1]
        command = classify(instruction)
        if command and command.action in {"research", "audit", "build", "contact", "draft"}:
            return instruction
    return None


class Commands:
    def __init__(self, runtime):
        self.runtime = runtime
        self.store = runtime.store

    def project(self, target, active_id, *, completed=False):
        tasks = [item for item in self.store.tasks() if not completed or item["state"] == "completed"]
        target = target.strip()
        for item in tasks:
            if item["id"] == target.casefold():
                return item
        target = re.sub(r"^(?:the )?(?:website|project|audit|proposal)(?: (?:for|of|about))? +", "", target, flags=re.I)
        ordered_words = search_words(target)
        words = set(ordered_words)
        exact = re.sub(r"[^a-z0-9]+", " ", target.casefold()).strip()
        scores = []
        for item in tasks:
            if item["state"] in {"failed", "cancelled"}:
                continue
            spec = item["spec"]
            candidates = spec.get("candidates", [])
            names = [item["title"], *(row["name"] for row in candidates), *(row["url"] for row in candidates)]
            checkpoints = self.store.checkpoints(item["id"])
            proposal = checkpoints.get("proposal", {}).get("draft", {})
            verified_names = [proposal["business"], proposal["source"]] if proposal else [
                row["name"] for row in checkpoints.get("report", {}).get("sources", []) if "score" in row
            ]
            if proposal:
                names = [proposal["business"], proposal["source"]] if completed else [proposal["business"], *names]
            elif completed:
                reviewed = [row for row in checkpoints.get("report", {}).get("sources", []) if "score" in row]
                names = [reviewed[0]["name"], reviewed[0]["url"]] if len(reviewed) == 1 else []
            normalized = [re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip() for name in names]
            score = max((len(words.intersection(name.split())) for name in normalized), default=0)
            if any(spoken_match(ordered_words, name) for name in names):
                score += 8
            if any(spoken_match(ordered_words, name) for name in verified_names):
                score += 24
            if len(exact) >= 3 and any(re.search(r"(?<!\w)" + re.escape(exact) + r"(?!\w)", name) for name in normalized):
                score += 12
            if score:
                scores.append((score, item, proposal.get("source") or (candidates[0]["url"] if len(candidates) == 1 else item["id"])))
        if scores and not FOLLOW_UP.fullmatch(target):
            highest = max(row[0] for row in scores)
            best = [row for row in scores if row[0] == highest]
            if len({row[2] for row in best}) == 1:
                return best[0][1]
            if active := next((row[1] for row in best if row[1]["id"] == active_id), None):
                return active
            raise NovaError("project_ambiguous", "More than one project matches. Say the business name or open the project you mean.")
        if not words or FOLLOW_UP.fullmatch(target):
            return next((item for item in tasks if item["id"] == active_id), None)
        return None

    def summary(self, task):
        checkpoints = self.store.checkpoints(task["id"])
        if task["state"] != "completed":
            return f"{task['title']} is {task['state'].replace('_', ' ')}. {task['cursor']} steps have been saved."
        proposal = checkpoints.get("proposal", {}).get("draft")
        if proposal:
            findings = " ".join(proposal.get("observations", [])[:2])
            return (f"Here’s what the {proposal['business']} website review found. {findings} "
                    f"The verified preview is ready. The proposal estimate is {proposal['proposed_price_inr']:,} rupees.")
        report = checkpoints.get("report") or checkpoints.get("sources")
        if report and report["sources"]:
            first = next((source for source in report["sources"] if "error" not in source), None)
            if first is None:
                return "The sources could not be reviewed. Open the mission to see the recorded errors."
            if first.get("extract"):
                return f"I found {len(report['sources'])} Wikipedia sources. The first is {first['name']}. The source notes are in the mission."
            findings = " ".join(item["observation"] for item in first.get("findings", [])[:2])
            return f"I reviewed {first['name']}. {findings or 'The audit report is ready in the mission.'}"
        return f"{task['title']} is complete. The saved results are in the mission."

    async def run(self, text, active_id):
        command = classify(text)
        if not command and REQUEST.search(text) and not re.match(r"\s*(?:what|how|why|when|where)\b", text, re.I):
            command = await self.runtime.gateway.chat(Capability.FAST, [
                {"role": "system", "content": "Classify the owner's request. Use a listed action only for an explicit instruction, including polite requests. "
                 "For a question about a saved project choose knowledge. For conceptual discussion choose answer. "
                 "Copy target words exactly from the request. Use 'this project' only for an explicit pronoun or reference. "
                 "For research followed by a contact request, set follow_up to contact. No send or shell action exists."},
                {"role": "user", "content": text[:1000]},
            ], schema=Command, max_output=140)
            if command.target and command.target.casefold() not in text.casefold():
                if not (FOLLOW_UP.fullmatch(command.target) and re.search(r"\b(?:it|them|this|that)\b", text, re.I)):
                    raise NovaError("command_target", "I need the exact business, topic, or website to proceed.")
        if not command or command.action == "answer":
            return None
        action = command.action
        target = command.target.strip()
        url_match = URL.search(target)
        task = self.project(target, active_id, completed=action in {"contact", "draft"}) if not url_match or action in {"contact", "draft", "knowledge", "open"} else None
        if action in {"contact", "draft"}:
            if self.store.stopped():
                raise NovaError("stopped", "Emergency stop is active.")
            if not task:
                pending = self.project(target, active_id)
                if (pending and pending["spec"]["workflow"] in {"website", "research"}
                        and pending["state"] not in {"completed", "failed", "cancelled"}):
                    self.runtime.outreach.request_contact(pending["id"])
                    return ActionResult("I’ll prepare the draft once the website research identifies the business. Delivery stays in Communications for review.",
                                        pending["id"], view="overview")
                raise NovaError("contact_target", "Open the completed project or say the business name so I can prepare the right message.")
            draft = self.runtime.business.contact_draft(task["id"])
            return ActionResult(f"I prepared the email for {draft['business']}. Review the recipient and message in Communications.",
                                task["id"], draft["id"], "communications")
        if action in {"knowledge", "open"}:
            if not task:
                if action == "knowledge" and re.search(r"\b(?:your|this|that|my|the)\b", text, re.I):
                    raise NovaError("project_missing", "Which project should I look at? Say its name or open it in the dashboard.")
                return None
            return ActionResult(self.summary(task), task["id"], view="projects" if task["spec"]["workflow"] == "website" else "overview")
        if action in {"pause", "resume", "cancel"}:
            if not task:
                raise NovaError("task_missing", "Which mission should I change?")
            updated = self.runtime.control(task["id"], action)
            return ActionResult(f"{updated['title']} is {updated['state']}.", task["id"], view="overview")
        if not target or FOLLOW_UP.fullmatch(target):
            if not task:
                raise NovaError("command_target", "Tell me the website, business name, or topic to work on.")
        title = target if target and not FOLLOW_UP.fullmatch(target) else task["title"]
        if action == "brief":
            spec = MissionInput(title=f"Brief: {title}"[:140], workflow="brief", objective=target)
        elif action == "research" and url_match and re.search(r"\b(?:directory|listing)\b", target, re.I):
            raw = url_match[0].rstrip(".,?!);")
            parsed = urlsplit(raw if raw.lower().startswith(("http://", "https://")) else "https://" + raw)
            spec = MissionInput(title=f"Directory research: {parsed.hostname}"[:140], workflow="research",
                                directory_url=parsed._replace(query="", fragment="").geturl(),
                                prepare_contact=command.follow_up == "contact")
        elif url_match or (task and (task["spec"].get("candidates") or task["spec"].get("business_search") or task["spec"].get("directory_url"))):
            if url_match:
                raw = url_match[0].rstrip(".,?!);")
                url = raw if raw.lower().startswith(("http://", "https://")) else "https://" + raw
                parsed = urlsplit(url)
                url = parsed._replace(query="", fragment="").geturl()
                candidate = Candidate(name=parsed.hostname or raw, url=url)
                source = {"candidates": [candidate]}
            else:
                source = {key: task["spec"].get(key) for key in ("candidates", "business_search", "directory_url") if task["spec"].get(key)}
                proposal = self.store.checkpoints(task["id"]).get("proposal", {}).get("draft")
                ordered = search_words(target)
                explicit = set(ordered)
                matched = [item for item in source.get("candidates", []) if explicit and (
                    spoken_match(ordered, item["name"]) or explicit.issubset(set(search_words(item["name"]))))]
                if len(matched) == 1:
                    source = {"candidates": matched}
                elif proposal and (FOLLOW_UP.fullmatch(target) or spoken_match(ordered, proposal["business"])):
                    source = {"candidates": [Candidate(name=proposal["business"], url=proposal["source"])]}
            spec = MissionInput(title=f"{'Website concept' if action == 'build' else 'Website research'}: {title}"[:140],
                                workflow="website" if action == "build" else "research",
                                prepare_contact=command.follow_up == "contact", **source)
        elif action in {"build", "audit"} or command.follow_up == "contact":
            spec = MissionInput(title=f"{'Website concept' if action == 'build' else 'Business research'}: {title}"[:140],
                                workflow="website" if action == "build" else "research", business_search=target[:100],
                                prepare_contact=command.follow_up == "contact")
        else:
            if re.search(r"\bbusiness(?:es)?\b", target, re.I) and re.search(
                r"\b(?:without|no|don.t have|do not have|lack)\b.{0,35}\b(?:website|site)s?\b", target, re.I
            ):
                raise NovaError("command_target", "Name a business or share a public directory to check. A missing website link alone doesn’t tell me whether a business has a site.")
            spec = MissionInput(title=f"Research: {title}"[:140], workflow="topic", objective=target)
        mission, created = self.runtime.submit(spec)
        label = "I queued" if created else "I already queued"
        return ActionResult(f"{label} the mission “{mission['title']}”. I'll save the results in Missions.", mission["id"], view="overview")
