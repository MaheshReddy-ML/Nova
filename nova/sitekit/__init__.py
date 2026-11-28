"""NOVA site kit: model-planned content rendered through a hand-crafted design system.

Small models are good at choosing a direction and writing specific copy, and weak at inventing polished layout CSS.
The kit splits the job: the model returns a validated SitePlan (theme, accent, copy, sections) and this module renders it
with professionally designed, accessible components, bundled fonts and the business's own photographs.
"""
import re
from html import escape
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from ..domain import StrictModel

KIT = Path(__file__).parent
FONTS = sorted((KIT / "fonts").glob("*.woff2"))
THEMES = ("editorial", "modern", "noir", "fresh")
THEME_INK = {"editorial": "#1f1b16", "modern": "#0e1628", "noir": "#15120c", "fresh": "#ffffff"}
THEME_BG = {"editorial": "#f5efe4", "modern": "#f7f8fb", "noir": "#0e0d0b", "fresh": "#fffaf0"}
ASSET = re.compile(r"^(?:img-\d{1,2}\.jpg|font-[a-z0-9-]+\.woff2)$")
T = lambda limit: Field(default="", max_length=limit)  # noqa: E731


class Item(StrictModel):
    title: str = Field(max_length=70)
    text: str = T(320)
    meta: str = T(60)


class SitePlan(StrictModel):
    theme: Literal["editorial", "modern", "noir", "fresh"]
    accent: str = Field(default="", max_length=7)
    brand: str = Field(max_length=60)
    tagline: str = T(100)
    hero_eyebrow: str = T(60)
    hero_headline: str = Field(max_length=100)
    hero_subhead: str = T(260)
    primary_cta: str = Field(default="Enquire now", max_length=36)
    secondary_cta: str = Field(default="Explore", max_length=36)
    highlights: list[Item] = Field(default_factory=list, max_length=4)
    offer_title: str = T(70)
    offer_intro: str = T(240)
    offerings: list[Item] = Field(default_factory=list, max_length=6)
    story_title: str = T(80)
    story_text: str = T(700)
    story_quote: str = T(180)
    process_title: str = T(70)
    steps: list[Item] = Field(default_factory=list, max_length=4)
    visit_title: str = T(70)
    locations: list[Item] = Field(default_factory=list, max_length=3)
    faq: list[Item] = Field(default_factory=list, max_length=5)
    closing_headline: str = T(100)
    closing_text: str = T(220)
    enquiry_title: str = T(70)
    enquiry_text: str = T(240)
    enquiry_topics: list[str] = Field(default_factory=list, max_length=6)
    photo_subjects: list[str] = Field(default_factory=list, max_length=6)
    lead_photo: int = Field(default=0, ge=0, le=12)  # 1-based number of the business photo to lead the hero; 0 = auto

    @field_validator("accent")
    @classmethod
    def hex_colour(cls, value):
        return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value or "") else ""


def luminance(colour):
    channels = [int(colour[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
    return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + .05) / (low + .05)


def accent_tokens(plan):
    """Accept the model's accent only when buttons and accent text stay WCAG AA readable on this theme."""
    colour = plan.accent
    if not colour:
        return ""
    ink = "#ffffff" if contrast(colour, "#ffffff") >= contrast(colour, "#111111") else "#111111"
    if contrast(colour, ink) < 4.5 or contrast(colour, THEME_BG[plan.theme]) < 3:
        return ""
    return f"--accent: {colour}; --accent-ink: {ink}; --accent-soft: color-mix(in srgb, {colour} 22%, var(--bg));"


def e(value):
    return escape(value or "", quote=True)


def initials(name):
    return "".join(part[0] for part in re.findall(r"[A-Za-z0-9]+", name)[:2]).upper() or "•"


def paragraphs(text):
    return "".join(f"<p>{e(block)}</p>" for block in re.split(r"\n\s*\n|\n", text or "") if block.strip())


def rank_photos(images):
    """Hero first: favour large, near-portrait photographs; push 1200x630-style social cards to the back."""
    def score(item):
        width, height = item[1], item[2]
        ratio = width / max(1, height)
        social_card = abs(ratio - 1.9) < .1
        shape = 1.0 if .62 <= ratio <= 1.4 else .7 if ratio < .62 else .55
        return width * height * shape * (.25 if social_card else 1)
    return sorted(images, key=score, reverse=True)


def meta_of(item):
    return item[3] if item is not None and len(item) > 3 and isinstance(item[3], dict) else {}


def credit_of(item):
    """Attribution of a representative stock photo; None for the business's own photos."""
    meta = meta_of(item)
    return meta if meta.get("license") else None


def describe(item):
    """What a photo shows: the vision caption when there is one, else the page's alt text."""
    meta = meta_of(item)
    return meta.get("caption") or meta.get("alt") or ""


def words(text):
    return {word.rstrip("s") for word in re.findall(r"[a-z]{3,}", (text or "").casefold())} - {"the", "and", "our", "with", "for"}


def overlap(first, second):
    """Shared words between two phrases, counting prefixes ("mic" ~ "microphone", "pottery" ~ "potter")."""
    others = words(second)
    return sum(1 for word in words(first) if any(word.startswith(other) or other.startswith(word) for other in others))


def arrange_photos(plan, images):
    """Art-direct the available photos: the business's own pictures always come first, then representative stock photos.

    Own photos whose alt text names an offering go on that offering's card; the best remaining own photo leads the hero;
    stock photos go to the slot they were searched for (0 = hero, 1.. = offering 1..). Returns hero, story, one entry per
    offering card (empty when the cards stay typographic), gallery and the used photos, each exactly once, in file order."""
    listed = [item for item in images if not credit_of(item)]  # numbered 1.. in the brief, in this order
    own = rank_photos(listed)
    chosen = listed[plan.lead_photo - 1] if 1 <= plan.lead_photo <= len(listed) else None
    stock = [item for item in images if credit_of(item)]
    count = len(plan.offerings)
    used, taken = [], set()

    def take(item):
        if item is not None and id(item) not in taken:
            taken.add(id(item))
            used.append(item)
        return item

    matches = {}
    for index, offer in enumerate(plan.offerings):
        claimed = {id(item) for item in matches.values()}
        scored = [(overlap(describe(item), offer.title + " " + offer.text[:80]), item)
                  for item in own if id(item) not in claimed and item is not chosen]
        best = max(scored, key=lambda pair: pair[0], default=(0, None))
        if best[0]:
            matches[index] = best[1]
    matched = {id(item) for item in matches.values()}

    def free(items, *, reserved=True, claimed=True):
        return [item for item in items if id(item) not in taken
                and (reserved or not 1 <= (credit_of(item) or {}).get("slot", 0) <= count)
                and (claimed or id(item) not in matched)]

    def for_slot(index):
        return next((item for item in free(stock) if credit_of(item).get("slot") == index), None)

    # Without an explicit choice, lead with the photo whose description best matches the promise (ties: biggest, best shaped).
    promise = " ".join([*(plan.photo_subjects[:1]), plan.hero_headline, plan.hero_eyebrow, plan.brand])
    unclaimed = free(own, claimed=False)
    fitting = max(unclaimed, key=lambda item: overlap(describe(item), promise), default=None) if unclaimed else None
    hero = take(chosen or fitting or for_slot(0) or next(iter(free(own)), None)
                or next(iter(free(stock, reserved=False) or free(stock)), None))
    story = None
    if plan.story_text and (not count or len(free(own + stock)) >= 2):
        story = take(next(iter(free(own, claimed=False) or free(stock, reserved=False)), None))
    cards = []
    available = len([item for item in matches.values() if id(item) not in taken]) + len(free(own + stock, claimed=False))
    if count and available >= max(1, (count + 1) // 2):
        # Photo-led cards when at least half of them get a real picture; the rest get a quiet tinted panel.
        for index in range(count):
            mine = matches.get(index)
            cards.append(take((mine if mine is not None and id(mine) not in taken else None) or for_slot(index + 1)
                              or next(iter(free(own, claimed=False) or free(stock, reserved=False)), None)))
    if plan.story_text and story is None:
        story = take(next(iter(free(own + stock)), None))
    leftovers = free(own + stock)
    gallery = [take(item) for item in leftovers[:6]] if len(leftovers) >= 3 else []
    return {"hero": hero, "story": story, "cards": cards, "gallery": gallery, "used": used}


def missing_card_slots(plan, images):
    """Offering indexes (1-based) that the business's own photos cannot illustrate, for a targeted stock search."""
    layout = arrange_photos(plan, images)
    if not layout["cards"]:
        return list(range(1, len(plan.offerings) + 1))
    return [index + 1 for index, item in enumerate(layout["cards"]) if item is None]


COUNTABLE = re.compile(r"^(\d{1,5})(\+?)(\s+[A-Za-z][\w\s-]{0,40})?$")


def counter(title):
    """Animate a highlight only when it is a real, plain count such as "40+ workshops" (never a year)."""
    match = COUNTABLE.match(title.strip())
    if not match or 1900 <= int(match.group(1)) <= 2100 or int(match.group(1)) < 3:
        return ""
    return f' data-count="{int(match.group(1))}"'


def credits_html(photos):
    """Footer attribution for representative stock photos (title, creator, license, source), as CC licenses require."""
    entries = []
    for item in photos:
        credit = credit_of(item)
        if not credit:
            continue
        title = f'<a href="{e(credit["landing_url"])}">{e(credit["title"])}</a>' if credit.get("landing_url") else e(credit["title"])
        creator = credit.get("creator")
        by = (f' by <a href="{e(credit["creator_url"])}">{e(creator)}</a>' if creator and credit.get("creator_url")
              else f" by {e(creator)}" if creator else "")
        name = "CC0" if credit["license"] == "cc0" else "Public Domain Mark" if credit["license"] == "pdm" else \
            f'CC {credit["license"].upper()} {credit.get("license_version", "")}'.strip()
        licence = f'<a href="{e(credit["license_url"])}">{e(name)}</a>' if credit.get("license_url") else e(name)
        entries.append(f"<li>“{title}”{by}, {licence}, via {e(credit.get('provider') or 'Openverse')}</li>")
    if not entries:
        return ""
    return ('<details class="credits"><summary>Photo credits: representative stock photos, to be replaced with the '
            f"business's own</summary><ul>{''.join(entries)}</ul></details>")


def render(plan: SitePlan, *, images=(), phone="", source_url="", concept_by=""):
    """Return {filename: str|bytes} for a complete static site (index.html, style.css, fonts, photos)."""
    layout = arrange_photos(plan, list(images))
    names = {id(item): f"img-{index + 1}.jpg" for index, item in enumerate(layout["used"])}
    name = lambda item: names[id(item)] if item is not None else None  # noqa: E731
    hero_photo, story_photo = name(layout["hero"]), name(layout["story"])
    nav = [("offer", plan.offer_title and "What we offer"), ("story", plan.story_title and "Our story"),
           ("visit", plan.locations and "Visit"), ("faq", plan.faq and "FAQ")]
    nav_links = "".join(f'<a href="#{key}">{e(label)}</a>' for key, label in nav if label)
    first = plan.highlights[0] if plan.highlights else None
    landscape = hero_photo is not None and layout["hero"][1] / max(1, layout["hero"][2]) > 1.25
    if hero_photo:
        alt = describe(layout["hero"]) or \
            (plan.photo_subjects[0] if plan.photo_subjects else (plan.hero_eyebrow or plan.brand))
        media = (f'<figure class="hero-media{" landscape" if landscape else ""}"><div class="media-frame">'
                 f'<img src="{hero_photo}" alt="{e(alt)}" width="1200" height="1500" fetchpriority="high"></div>'
                 + (f'<figcaption class="hero-badge"><strong>{e(first.title)}</strong><span>{e(first.text)}</span></figcaption>' if first else "")
                 + "</figure>")
    else:
        media = '<div class="hero-art" role="img" aria-label="Decorative illustration"><span></span></div>'
    sections = []
    if plan.highlights:
        sections.append('<section class="highlights" aria-label="Highlights"><div class="container" data-reveal-group>' + "".join(
            f'<div class="highlight"><strong{counter(item.title)}>{e(item.title)}</strong><span>{e(item.text)}</span></div>' for item in plan.highlights)
            + "</div></section>")
    if plan.offerings:
        photo_cards = bool(layout["cards"])

        def card_media(index, item):
            if not photo_cards:
                return ""
            photo = layout["cards"][index]
            if photo is None:
                return f'<div class="card-media card-media-empty" aria-hidden="true"><span>{e(initials(item.title))}</span></div>'
            return f'<div class="card-media"><img src="{name(photo)}" alt="{e(describe(photo) or item.title)}" loading="lazy" width="800" height="600"></div>'

        cards = "".join(
            f'<article class="card{" has-photo" if photo_cards else ""}">{card_media(index, item)}<div class="card-body">'
            f'<span class="card-index">{index + 1:02d}</span><h3>{e(item.title)}</h3><p>{e(item.text)}</p>'
            + (f'<p class="card-meta">{e(item.meta)}</p>' if item.meta else "") + "</div></article>"
            for index, item in enumerate(plan.offerings))
        sections.append(f'<section class="section offer" id="offer"><div class="container"><div class="section-head" data-reveal><div>'
                        f'<span class="eyebrow">What we offer</span><h2>{e(plan.offer_title or "What we offer")}</h2></div>'
                        f'<p>{e(plan.offer_intro)}</p></div><div class="cards{" photo-cards count-" + str(len(plan.offerings)) if photo_cards else ""}" data-reveal-group>{cards}</div></div></section>')
    if plan.story_text:
        story_alt = describe(layout["story"]) or f"Inside {plan.brand}"
        media_html = (f'<figure class="story-media" data-parallax><div class="media-frame"><img src="{story_photo}" alt="{e(story_alt)}" '
                      'loading="lazy" width="1000" height="1200"></div></figure>'
                      if story_photo else '<div class="hero-art" role="img" aria-label="Decorative illustration"><span></span></div>')
        quote = f"<blockquote>{e(plan.story_quote)}</blockquote>" if plan.story_quote else ""
        sections.append(f'<section class="section story" id="story"><div class="container">{media_html}<div data-reveal>'
                        f'<span class="eyebrow">Our story</span><h2>{e(plan.story_title or "Our story")}</h2>'
                        f'<div class="story-text">{paragraphs(plan.story_text)}</div>{quote}</div></div></section>')
    if plan.steps:
        steps = "".join(f"<li><h3>{e(item.title)}</h3><p>{e(item.text)}</p></li>" for item in plan.steps)
        sections.append(f'<section class="section process"><div class="container"><div class="section-head"><div>'
                        f'<span class="eyebrow">How it works</span><h2>{e(plan.process_title or "How it works")}</h2></div></div>'
                        f'<ol class="steps" data-reveal-group>{steps}</ol></div></section>')
    if layout["gallery"]:
        figures = "".join(f'<figure><img src="{name(item)}" alt="{e(describe(item) or plan.brand + ", photo " + str(index + 1))}" loading="lazy" width="900" height="700"></figure>'
                          for index, item in enumerate(layout["gallery"]))
        sections.append(f'<section class="section gallery" aria-label="Gallery"><div class="container"><div class="section-head" data-reveal><div>'
                        f'<span class="eyebrow">Gallery</span><h2>A look inside</h2></div></div>'
                        f'<div class="gallery-grid count-{len(layout["gallery"])}" data-reveal-group>{figures}</div></div></section>')
    if plan.locations:
        places = "".join(f'<article class="location"><h3>{e(item.title)}</h3><p>{e(item.text)}</p>'
                         + (f'<p class="meta">{e(item.meta)}</p>' if item.meta else "") + "</article>" for item in plan.locations)
        sections.append(f'<section class="section visit" id="visit"><div class="container"><div class="section-head"><div>'
                        f'<span class="eyebrow">Visit</span><h2>{e(plan.visit_title or "Come and visit")}</h2></div></div>'
                        f'<div class="locations" data-reveal-group>{places}</div></div></section>')
    if plan.faq:
        questions = "".join(f"<details><summary>{e(item.title)}</summary><p>{e(item.text)}</p></details>" for item in plan.faq)
        sections.append(f'<section class="section faq" id="faq"><div class="container"><div class="section-head"><div>'
                        f'<span class="eyebrow">Questions</span><h2>Good to know</h2></div></div><div class="faq-list">{questions}</div>'
                        "</div></section>")
    if plan.closing_headline:
        sections.append(f'<section class="section closing"><div class="container" data-reveal><div><h2>{e(plan.closing_headline)}</h2>'
                        f'<p>{e(plan.closing_text)}</p></div><a class="button" href="#enquire">{e(plan.primary_cta)}</a></div></section>')
    topics = "".join(f"<option>{e(topic)}</option>" for topic in (plan.enquiry_topics or ["General enquiry"]))
    contact = f'<p>Call <a href="tel:{e(re.sub(r"[^0-9+]", "", phone))}">{e(phone)}</a></p>' if phone else ""
    sections.append(
        f'<section class="section enquiry" id="enquire"><div class="container"><div class="enquiry-intro"><span class="eyebrow">Get in touch</span>'
        f'<h2>{e(plan.enquiry_title or "Plan your visit")}</h2><p>{e(plan.enquiry_text)}</p><div class="contact-lines">{contact}</div></div>'
        '<form class="form-card demo-form" action="#" novalidate>'
        '<div class="form-row"><label for="f-name">Your name<input id="f-name" name="name" autocomplete="name" required></label>'
        '<label for="f-email">Email<input id="f-email" name="email" type="email" autocomplete="email" required></label></div>'
        f'<label for="f-topic">What are you interested in?<select id="f-topic" name="topic">{topics}</select></label>'
        '<label for="f-message">Message<textarea id="f-message" name="message"></textarea></label>'
        f'<button class="button" type="submit">{e(plan.primary_cta)}</button>'
        '<p class="form-note" role="status">Concept preview: this form does not send anything.</p></form></div></section>')
    style = accent_tokens(plan)
    description = plan.hero_subhead or plan.tagline
    source_host = re.sub(r"^https?://(?:www\.)?", "", source_url).rstrip("/")
    html = f"""<!doctype html>
<html lang="en" data-theme="{plan.theme}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(plan.brand)}{' | ' + e(plan.tagline) if plan.tagline else ''}</title>
<meta name="description" content="{e(description)[:300]}">
<link rel="stylesheet" href="style.css">
<script src="demo.js" defer></script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header"><div class="container">
<a class="brand" href="#main"><span class="brand-mark" aria-hidden="true">{e(initials(plan.brand))}</span>{e(plan.brand)}</a>
<nav class="site-nav" aria-label="Main">{nav_links}<a class="button" href="#enquire">{e(plan.primary_cta)}</a></nav>
</div></header>
<main id="main">
<section class="hero{' has-image' if hero_photo else ''}"><div class="container"><div>
<span class="eyebrow">{e(plan.hero_eyebrow or plan.tagline)}</span>
<h1>{e(plan.hero_headline)}</h1>
<p class="lead">{e(plan.hero_subhead)}</p>
<div class="hero-actions"><a class="button" href="#enquire">{e(plan.primary_cta)}</a><a class="button ghost" href="#{'offer' if plan.offerings else 'enquire'}">{e(plan.secondary_cta)}</a></div>
</div>{media}</div></section>
{''.join(sections)}
</main>
<footer class="site-footer"><div class="container"><div><a class="brand" href="#main">{e(plan.brand)}</a><p>{e(plan.tagline)}</p></div>
<p>{('Concept by ' + e(concept_by) + ' · ') if concept_by else ''}Based on <a href="{e(source_url)}">{e(source_host)}</a></p>{credits_html(layout["used"])}</div></footer>
</body>
</html>
"""
    css = (KIT / "kit.css").read_text(encoding="utf-8")
    if style:
        css += f"\n:root, [data-theme=\"{plan.theme}\"] {{ {style} }}\n"
    files = {"index.html": html, "style.css": css, "demo.js": (KIT / "motion.js").read_text(encoding="utf-8")}
    for font in FONTS:
        files[font.name] = font.read_bytes()
    for item in layout["used"]:
        files[name(item)] = item[0]
    return files


PLAN_SCHEMA_HINT = """Return one JSON object (no markdown fences) with these keys:
theme: one of "editorial" (refined serif, paper tones: craft, cafes, studios, boutiques, hospitality), "modern" (clean sans,
  soft depth: tech, clinics, professional services, education), "noir" (dark luxury: restaurants, salons, premium venues,
  architecture), "fresh" (bold and playful: fitness, kids, events, food trucks, creative workshops).
accent: a hex colour that fits the brand (or "" for the theme default).
brand, tagline (one line, their voice),
hero_eyebrow (2-5 words), hero_headline (specific promise in 4-10 words, never just the business name),
hero_subhead (1-2 sentences with concrete facts), primary_cta (verb-first, e.g. "Book a wheel class"), secondary_cta,
highlights: 3-4 items {title: short punchy fact e.g. "Two studios", text: 3-8 words},
offer_title, offer_intro, offerings: 3-6 items {title, text (1-2 sentences of real detail), meta (e.g. schedule/price ONLY if in the facts)},
story_title, story_text (2 short paragraphs from their real story), story_quote (one line in their voice, no invented customer quotes),
process_title, steps: 3-4 items {title, text} describing how a visit/booking works,
visit_title, locations: 0-3 items {title: place name, text: address exactly as given, meta: hours or phone if given},
faq: 0-5 items {title: question, text: answer from the facts},
closing_headline (inviting, 4-10 words), closing_text, enquiry_title, enquiry_text, enquiry_topics: 2-5 short options,
photo_subjects: 3-6 short concrete photo subjects (2-4 words, people doing the activity, hands, materials, the space),
  first = the hero image, then one per offering in the same order, e.g. ["hands shaping clay on wheel", "resin art pour"].
lead_photo: the number of the business photo (from the numbered list in the brief) that best shows the experience your
  headline promises, or 0 if none fits. Never pair a headline with a photo of something else.
Rules: use only facts in the brief; never invent prices, awards, reviews, years, numbers or testimonials. Omit a section by
leaving its list empty. Write like a top agency copywriter: specific, sensory, benefit-led, no hype words."""
