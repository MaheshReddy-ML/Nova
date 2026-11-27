"""Local, versioned design directions and rendering primitives for website concepts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from html import escape
from ipaddress import ip_address
from urllib.parse import urlsplit

from .domain import NovaError

DESIGN_SYSTEM_VERSION = "2.0.0"


@dataclass(frozen=True)
class Palette:
    paper: str
    ink: str
    accent: str
    surface: str
    muted: str
    line: str
    on_accent: str = "#ffffff"


@dataclass(frozen=True)
class Direction:
    category: str
    direction: str
    composition: str
    audience: str
    conversion: str
    heading: str
    body: str
    palette: Palette
    introduction: str
    action: str
    links_heading: str
    art_description: str
    spacing: str
    motion: str = "Native navigation. Smooth scrolling when motion is allowed."


DIRECTIONS = {
    "restaurant": Direction(
        "restaurant", "The evening menu",
        "An intimate split masthead and a narrow, menu-like sequence of sections.",
        "Diners comparing where to go and how to plan a visit.", "Find current dining and booking details.",
        "Georgia, serif", "system-ui, sans-serif",
        Palette("#f4ebdc", "#282017", "#74421e", "#381e1b", "#614938", "#c7aea0"),
        "Find the restaurant’s current dining information and plan a visit.", "Plan your visit",
        "Menus and reservations", "Original CSS line work inspired by tableware.",
        "Narrow editorial measures and broad section breaks.",
    ),
    "architecture": Direction(
        "architecture", "The working drawing",
        "An asymmetric drawing-board masthead and a project-editorial split grid.",
        "Prospective clients and collaborators looking for the studio’s work and contact information.",
        "Review the practice and open an official project or enquiry channel.",
        "system-ui, sans-serif", "system-ui, sans-serif",
        Palette("#f0eee8", "#252525", "#373737", "#dbd6c9", "#555149", "#9c9486"),
        "Explore the practice and find its published project or enquiry information.", "Explore the practice",
        "Practice and projects", "An original line drawing made with CSS and proportion rules.",
        "An asymmetric column grid, ruled baselines and measured gutters.",
    ),
    "healthcare": Direction(
        "healthcare", "Clear next steps",
        "A compact guidance masthead next to a task index, followed by a single readable column.",
        "People looking for practical information before contacting a clinic.",
        "Find an official contact or appointment channel without entering health details.",
        "system-ui, sans-serif", "system-ui, sans-serif",
        Palette("#f0f6f4", "#183331", "#075b50", "#dcece7", "#3c5955", "#a4bcb4"),
        "Find the clinic’s official information before planning your visit.", "Find visit information",
        "Clinic information", "Text-led composition with a practical, prominently labeled task index.",
        "Compact header spacing, readable line lengths and generous controls.",
    ),
    "hospitality": Direction(
        "hospitality", "Arrival journal",
        "A centered title in a tall, two-tone masthead with journal-style sections beneath.",
        "Guests considering a stay and checking official property information.",
        "Open official property and reservation information.",
        "Georgia, serif", "Georgia, serif",
        Palette("#efe9dc", "#222b2a", "#23534e", "#d2ddcd", "#495e55", "#a0ac97"),
        "Explore the property’s official information and check the details for a stay.", "Explore your stay",
        "Property and stays", "An original CSS arch and horizon composition.",
        "Large masthead, slim folio, and spacious lines.",
    ),
    "software": Direction(
        "software", "The product field guide",
        "A compact split masthead with a scannable local review ledger and orderly information blocks.",
        "Prospective customers evaluating software and trying to find official product information.",
        "Find official product material and understand the next step.",
        "system-ui, sans-serif", "system-ui, sans-serif",
        Palette("#f6f5fb", "#221c36", "#50249a", "#e8e2f3", "#54476b", "#b6accb"),
        "Find the product’s official overview and decide what to explore next.", "Explore the product",
        "Product information", "A small review ledger using only evidence from the project.",
        "Dense ledger rows balanced by an open main content column.",
    ),
    "craft": Direction(
        "craft", "The maker’s notebook",
        "An open, two-column masthead and a notebook-like sequence of sections.",
        "People looking for studio offerings and the official route to book or enquire.",
        "Find official workshop and enquiry information.",
        "Georgia, serif", "system-ui, sans-serif",
        Palette("#f7eee2", "#302119", "#873f29", "#dcaa89", "#684c3a", "#ba9682"),
        "Explore the studio’s published workshops and find the official route to book or enquire.",
        "Explore workshop information", "Workshops and studio", "Original CSS rings and clay forms.",
        "Airy notebook margins, an open grid and clear section dividers.",
    ),
    "general": Direction(
        "general", "The field note",
        "An understated editorial masthead, evidence in a narrow measure and a direct official link.",
        "Visitors trying to understand the business and locate its official information.",
        "Open the official site or listed business information.",
        "Georgia, serif", "system-ui, sans-serif",
        Palette("#f7f4ed", "#25252b", "#244b66", "#dfebed", "#4e565d", "#9eacb2"),
        "Find the business’s latest information and the next step to get in touch.",
        "Find official information", "Official information", "An original typographic editorial frame.",
        "An editorial column with restrained spacing and clear rules.",
    ),
}
CATEGORY_PATTERNS = {
    "healthcare": r"\b(clinic|healthcare|dental|dentist|health\s+care|medical|physiotherapy|hospital)\b",
    "architecture": r"\b(architect(?:s|ure|ural)?|urban design|built environment|interior architecture)\b",
    "restaurant": r"\b(restaurant|dining|bistro|tasting menu|steakhouse|pizzeria|brasserie)\b",
    "software": r"\b(software|saas|developer platform|api platform|cloud platform|analytics platform)\b",
    "hospitality": r"\b(hotel|resort|boutique inn|hospitality|guesthouse|guest house|lodge)\b",
    "craft": r"\b(pottery|ceramic(?:s)?|clay|making studio|craft studio|maker space)\b",
}


def classify_category(lead: dict) -> str:
    if lead.get("category") in DIRECTIONS:
        return lead["category"]
    primary = " ".join((str(lead.get("name", "")), str(lead.get("title", ""))))
    headings = " ".join(str(heading) for heading in lead.get("headings", [])[:12])
    if re.search(CATEGORY_PATTERNS["craft"], primary, re.I):
        return "craft"
    for column in (primary, headings):
        for category, pattern in CATEGORY_PATTERNS.items():
            if re.search(pattern, column, re.I):
                return category
    return "general"


def public_link(value: str) -> str:
    try:
        split = urlsplit(value)
        hostname = split.hostname or ""
        try:
            local = not ip_address(hostname).is_global
        except ValueError:
            clean_host = hostname.rstrip(".")
            top_label = clean_host.rsplit(".", maxsplit=1)[-1]
            local = ("." not in clean_host or not any(char.isalpha() for char in top_label)
                     or clean_host.endswith((".local", ".localhost")))
        if (split.scheme in {"http", "https"} and split.hostname and not split.username
                and not split.password and not any(ord(char) <= 32 or ord(char) == 127 for char in value)
                and not local and "\\" not in value and split.port in {None, 80, 443}):
            return value
    except (TypeError, ValueError):
        pass
    raise NovaError("preview_source", "The concept needs a valid public HTTP(S) source link.")


def design_brief(lead: dict, skill_ids: tuple[str, ...] = ()) -> dict:
    direction = DIRECTIONS[classify_category(lead)]
    return {
        "version": DESIGN_SYSTEM_VERSION,
        "category": direction.category,
        "direction": direction.direction,
        "composition": direction.composition,
        "audience": direction.audience,
        "conversion": direction.conversion,
        "typography": {"heading": direction.heading, "body": direction.body},
        "palette": asdict(direction.palette),
        "spacing": direction.spacing,
        "motion": direction.motion,
        "art_direction": direction.art_description,
        "source": public_link(lead["url"]),
        "featured_source": public_link(lead.get("next_url") or lead["url"]),
        "skills": list(dict.fromkeys(skill_ids)),
        "budget": {"currency": "INR", "basis": "Planning assumption; confirm the scope before quoting."},
        "maintenance": "Static HTML, CSS and local-only demo JavaScript.",
        "accessibility": ["Keyboard access", "Visible focus", "Responsive layout", "Reduced motion"],
        "asset_provenance": [{
            "asset": "Visual motifs and CSS composition",
            "source": "Original NOVA component library",
            "notes": "Uses local system fonts. No remote imagery or copied brand assets.",
        }],
    }


def visual(direction: Direction, findings: list[dict], verified_link: bool) -> str:
    category = direction.category
    if category == "restaurant":
        return """
<aside class="art plate-art" aria-hidden="true"><span></span><span></span><span></span></aside>"""
    if category == "architecture":
        return """
<aside class="art drafting-art" aria-hidden="true"><span></span><span></span><span></span></aside>"""
    if category == "healthcare":
        return """
<aside class="art task-index" aria-label="Visit guide">
  <p>Visit guide</p><a href="#next">Find official details</a><a href="#concept">Review the website changes</a>
</aside>"""
    if category == "hospitality":
        return """
<div class="art arrival-art" aria-hidden="true"><span></span><span></span></div>"""
    if category == "software":
        rows = "".join(f"<li>{escape(item['observation'])}</li>" for item in findings[:2])
        label = "Official product details linked" if verified_link else "Official website linked"
        return f"""
<aside class="art ledger" aria-label="Website review facts">
  <p>Review ledger</p><ul><li>{label}</li>{rows}</ul>
</aside>"""
    if category == "craft":
        return """
<aside class="art craft-art" aria-hidden="true"><span></span><span></span><span></span></aside>"""
    return """
<div class="art field-art" aria-hidden="true"><span></span></div>"""


ENQUIRY = """
<section class="section enquiry" id="enquiry">
  <h2>Try the enquiry form</h2>
  <div>
    <p>Use sample information to try this interaction. The preview does not send or store entries.</p>
    <form class="demo-form">
      <label>Sample name<input placeholder="Alex" required autocomplete="off" maxlength="60"></label>
      <label>Enquiry topic<select required>
        <option value="">Choose a topic</option><option>Availability</option><option>Group enquiry</option>
      </select></label>
      <button class="action" type="submit">Test enquiry</button>
      <p role="status"></p>
    </form>
  </div>
</section>
"""


def markup(lead: dict, brief: dict) -> str:
    direction = DIRECTIONS[brief["category"]]
    name = escape(lead["name"])
    url = escape(brief["source"], quote=True)
    next_url = escape(brief["featured_source"], quote=True)
    findings = lead.get("findings", [])
    ideas = "".join(f'<li>{escape(item["change"])}</li>' for item in findings[:3])
    has_enquiry = bool(lead.get("unlabeled_fields"))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'; worker-src 'none'">
<title>{name} | Website concept</title>
<link rel="stylesheet" href="style.css">
{('<script src="demo.js" defer></script>' if has_enquiry else '')}
</head>
<body class="theme-{direction.category}">
<a class="skip" href="#top">Skip to content</a>
<header class="shell masthead"><a class="brand" href="#top">{name}</a>
  <nav aria-label="Main navigation"><a href="#concept">Concept</a><a href="#next">Official website</a></nav>
</header>
<main class="shell" id="top" tabindex="-1">
  <p class="notice">Unofficial demonstration · Prepared for private review</p>
  <div class="hero">
    <div class="hero-copy">
      <h1>{name}</h1>
      <p>{direction.introduction}</p>
      <a class="action" href="#next">{direction.action}</a>
    </div>
    {visual(direction, findings, url != next_url)}
  </div>
  <section class="section concept" id="concept">
    <h2>Design changes</h2>
    <div>{f"<ul>{ideas}</ul>" if ideas else "<p>The concept presents official information in a clear, responsive layout.</p>"}</div>
  </section>
  {ENQUIRY if has_enquiry else ""}
  <section class="section official" id="next">
    <h2>{direction.links_heading}</h2>
    <div>
      <p>Check the business’s own site for its current details and availability.</p>
      <div class="official-links">
        {f'<a class="action" href="{next_url}" rel="noopener noreferrer" target="_blank">See official offerings</a>' if next_url != url else ""}
        <a class="{'text-link' if next_url != url else 'action'}" href="{url}" rel="noopener noreferrer" target="_blank">Open official website</a>
      </div>
    </div>
  </section>
</main>
<footer><div class="shell">Private concept prepared by NOVA.</div></footer>
</body>
</html>
"""


BASE_CSS = """
:root{color-scheme:light}
*,*::before,*::after{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font:1rem/1.6 var(--body)}
.shell{width:min(1160px,calc(100% - 56px));margin-inline:auto}
p,ul,h1,h2{margin:0}
a{color:inherit;text-underline-offset:.24em}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--accent);outline-offset:4px}
.skip{position:fixed;z-index:9;top:.75rem;left:.75rem;padding:.7rem 1rem;background:var(--paper);transform:translateY(-200%)}
.skip:focus{transform:none}
.masthead{min-height:80px;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:0 1.5rem;border-bottom:1px solid var(--line)}
.brand,nav a{display:inline-flex;align-items:center;min-height:44px}
.brand{font-size:1.01rem;font-weight:740;text-decoration:none;min-width:0;overflow-wrap:anywhere}
nav{display:flex;flex-wrap:wrap;gap:0 1.2rem}
.notice{color:var(--muted);font-size:.875rem;margin:1rem 0}
.hero{display:grid;align-items:center;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:clamp(1.6rem,5vw,5rem);padding:.4rem 0 3.2rem}
.hero-copy, .section>div{min-width:0}
h1,h2{font-family:var(--head);font-weight:500;line-height:1.03;letter-spacing:-.052em;overflow-wrap:anywhere;text-wrap:balance}
h1{font-size:clamp(2.65rem,7vw,7.2rem);max-width:17ch}
h2{font-size:clamp(1.95rem,3.9vw,3.7rem)}
.hero-copy>p{color:var(--muted);font-size:clamp(1.04rem,1.25vw,1.2rem);max-width:46ch;margin-top:1.1rem}
.action{display:inline-flex;align-items:center;min-height:46px;max-width:100%;padding:.6rem 1.1rem;margin-top:1.2rem;background:var(--accent);color:var(--on-accent);font-weight:650;text-decoration:none;line-height:1.3;transition:filter .16s ease}
.action:hover{filter:brightness(1.12)}
.art{display:grid;position:relative;min-width:0;isolation:isolate;overflow:hidden}
.section{border-top:1px solid var(--line);padding:clamp(1.8rem,4.7vw,4.4rem) 0;scroll-margin-top:1rem;display:grid;grid-template-columns:minmax(0,.78fr) minmax(0,1fr);gap:1rem 3rem}
.section p,.section ul{max-width:62ch}
.section ul{padding-inline-start:1.25rem}
.section li+li{margin-top:.55rem}
.official-links{display:flex;align-items:center;gap:.6rem 1.15rem;flex-wrap:wrap;margin-top:1.2rem}
.official-links .action{margin:0}
.text-link{display:inline-flex;align-items:center;min-height:44px}
.demo-form{display:grid;gap:1rem;max-width:35rem;margin-top:1.2rem;color:var(--ink)}
.demo-form label{display:grid;gap:.28rem;font-weight:650}
.demo-form input,.demo-form select{color:var(--ink);background:var(--paper);border:1px solid var(--muted);width:100%;min-height:44px;padding:.55rem;font:inherit}
.demo-form input::placeholder{color:var(--muted)}
.demo-form button{font:inherit;font-weight:650;border:0;cursor:pointer;width:max-content;margin:0}
.demo-form [role=status]{min-height:1.5rem}
footer{border-top:1px solid var(--line);color:var(--muted);padding:1.4rem 0 2.6rem;font-size:.92rem}
@media(max-width:760px){.shell{width:calc(100% - 40px)}.hero{gap:1.7rem}.section{gap:1.2rem}}
@media(max-width:620px){.shell{width:calc(100% - 32px)}.masthead{padding:.4rem 0;min-height:58px}nav{gap:0 .9rem}.hero,.section{grid-template-columns:minmax(0,1fr)}.hero{padding-bottom:2rem}.notice{margin-top:.75rem}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*::before,*::after{transition-duration:0s!important;animation:none!important}}
"""

CATEGORY_CSS = {
    "restaurant": """
.theme-restaurant .hero{grid-template-columns:minmax(0,1fr) minmax(0,1.14fr)}
.theme-restaurant h1{font-weight:500;letter-spacing:-.065em}
.plate-art{width:100%;aspect-ratio:4/3;background:var(--surface);place-items:center}
.plate-art span{position:absolute;aspect-ratio:1;width:70%;border:1px solid #c48c67;border-radius:50%}
.plate-art span:nth-child(2){width:58%;border:1px dashed #d7ac84}
.plate-art span:nth-child(3){width:31%;border:9px double #e8c5a3;background:#653a30;rotate:-12deg;border-radius:42% 55% 43% 54%}
.theme-restaurant .section{width:min(100%,780px);margin-inline:auto;grid-template-columns:1fr;border-top:3px double var(--line);gap:.85rem}
@media(max-width:620px){.theme-restaurant .hero{grid-template-columns:minmax(0,1fr)}.plate-art{min-height:0}}
""",
    "architecture": """
.theme-architecture .masthead{border-bottom:2px solid var(--ink)}
.theme-architecture .hero{align-items:end;grid-template-columns:minmax(0,.9fr) minmax(0,1.42fr);gap:clamp(1rem,4vw,4rem)}
.theme-architecture h1{font-size:clamp(2.35rem,6vw,6.5rem);font-weight:660;letter-spacing:-.066em}
.drafting-art{height:clamp(230px,39vw,510px);background:var(--surface);border:1px solid var(--ink);background-image:repeating-linear-gradient(90deg,transparent 0 23px,#bab1a2 24px),repeating-linear-gradient(180deg,transparent 0 23px,#bab1a2 24px);place-items:center}
.drafting-art span{position:absolute;border:solid var(--ink);border-width:2px 2px 0 0;width:54%;height:55%;transform:skewY(-16deg);background:#e6e0d0}
.drafting-art span:nth-child(2){transform:translate(-23%,19%) skewY(-16deg);width:45%;height:40%;background:#b9ad96}
.drafting-art span:nth-child(3){transform:translate(40%,-6%) skewY(19deg);width:37%;height:57%;background:#d1c7b4;border-width:2px 0 0 2px}
.theme-architecture .concept{grid-template-columns:minmax(0,1fr) minmax(0,1.45fr)}
@media(max-width:620px){.theme-architecture .hero,.theme-architecture .concept{grid-template-columns:minmax(0,1fr)}}
""",
    "healthcare": """
.theme-healthcare .hero{grid-template-columns:minmax(0,1.4fr) minmax(0,.8fr);padding:1.65rem 0 2.4rem}
.theme-healthcare h1{font-size:clamp(2.55rem,5.6vw,5.1rem);font-weight:700;color:#123b36}
.task-index{background:var(--surface);padding:1.3rem 1.4rem;border-inline-start:4px solid var(--accent)}
.task-index p{font-weight:700;margin-bottom:.55rem}
.task-index a{min-height:47px;display:flex;align-items:center;border-top:1px solid var(--line)}
.theme-healthcare .section{width:min(100%,910px);margin-inline:auto}
@media(max-width:620px){.theme-healthcare .hero{grid-template-columns:minmax(0,1fr);padding-top:.4rem}}
""",
    "hospitality": """
.theme-hospitality .masthead{min-height:68px}
.theme-hospitality .hero{min-height:clamp(410px,53vw,620px);padding:3rem max(1rem,5%);margin-bottom:2.7rem;border:1px solid var(--line);background:var(--surface);grid-template-columns:1fr;text-align:center;position:relative;isolation:isolate}
.theme-hospitality .hero-copy{z-index:1;background:var(--paper);padding:clamp(1.2rem,5vw,3rem);margin-inline:auto;width:fit-content;max-width:100%;border:1px solid var(--line)}
.theme-hospitality .hero-copy h1,.theme-hospitality .hero-copy p{margin-inline:auto}
.arrival-art{position:absolute;inset:0;z-index:-1;place-items:end center}
.arrival-art span:first-child{height:120%;width:min(78%,760px);border:1px solid #718576;border-radius:50% 50% 0 0;transform:translateY(47%);background:#adbbab}
.arrival-art span:last-child{position:absolute;inset:auto 0 12%;height:18%;border-top:1px solid #829782;border-bottom:1px solid #829782}
.theme-hospitality .section{grid-template-columns:minmax(0,1fr);max-width:820px;margin-inline:auto;text-align:center}
.theme-hospitality .section p,.theme-hospitality .section ul,.theme-hospitality .demo-form{margin-inline:auto}
.theme-hospitality .section ul,.theme-hospitality .demo-form{text-align:left;width:fit-content;max-width:100%}
.theme-hospitality .official-links{justify-content:center}
""",
    "software": """
.theme-software .masthead{min-height:65px}
.theme-software .hero{grid-template-columns:minmax(0,1.23fr) minmax(0,.87fr);padding-block:1.65rem 3.2rem}
.theme-software h1{font-size:clamp(2.5rem,6.1vw,6.35rem);font-weight:700}
.ledger{background:var(--surface);border:1px solid var(--line);font-size:.92rem}
.ledger p{padding:.7rem .9rem;background:var(--accent);color:var(--on-accent);font-weight:650}
.ledger ul{padding:0;list-style:none}
.ledger li{padding:.72rem .9rem;border-top:1px solid var(--line);line-height:1.4}
.theme-software .section{padding-block:clamp(1.6rem,3.5vw,3.4rem)}
@media(max-width:620px){.theme-software .hero{grid-template-columns:minmax(0,1fr);padding-top:.45rem}}
""",
    "craft": """
.theme-craft .hero{grid-template-columns:minmax(0,1.12fr) minmax(0,.9fr)}
.craft-art{aspect-ratio:1.25;background:var(--surface);place-items:center;border:1px solid var(--line)}
.craft-art span{position:absolute;aspect-ratio:1;border-radius:47% 44% 42% 46%;width:65%;transform:rotate(-14deg);background:#c17452}
.craft-art span:nth-child(2){width:52%;border:1px solid #edb38e;outline:1px solid #834c38;outline-offset:8px;background:#ae5f43}
.craft-art span:nth-child(3){width:40%;border:1px solid #f2bd98;background:#995039}
.theme-craft .concept h2{padding-top:.1rem}
@media(max-width:620px){.theme-craft .hero{grid-template-columns:minmax(0,1fr)}}
""",
    "general": """
.theme-general .hero{grid-template-columns:minmax(0,1.7fr) minmax(0,1fr)}
.field-art{aspect-ratio:1.4;background:var(--surface);border:1px solid var(--line);place-items:center}
.field-art span{width:57%;aspect-ratio:1.3;border:3px double var(--accent);outline:1px solid var(--accent);outline-offset:13px}
@media(max-width:620px){.theme-general .hero{grid-template-columns:minmax(0,1fr)}}
""",
}


def stylesheet(brief: dict) -> str:
    direction = DIRECTIONS[brief["category"]]
    palette = asdict(direction.palette)
    properties = "".join(f"--{name.replace('_', '-')}:{value};" for name, value in palette.items())
    return f":root{{{properties}--head:{direction.heading};--body:{direction.body};}}\n{BASE_CSS}{CATEGORY_CSS[direction.category]}"
