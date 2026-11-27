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
        _, width, height = item
        ratio = width / max(1, height)
        social_card = abs(ratio - 1.9) < .1
        shape = 1.0 if .62 <= ratio <= 1.4 else .7 if ratio < .62 else .55
        return width * height * shape * (.25 if social_card else 1)
    return sorted(images, key=score, reverse=True)


def render(plan: SitePlan, *, images=(), phone="", source_url="", concept_by=""):
    """Return {filename: str|bytes} for a complete static site (index.html, style.css, fonts, photos)."""
    images = rank_photos(list(images))
    photos = [f"img-{index + 1}.jpg" for index in range(len(images))]
    hero_photo, story_photo = (photos[0] if photos else None), (photos[1] if len(photos) > 1 else None)
    gallery = photos[2:] if len(photos) >= 5 else []
    nav = [("offer", plan.offer_title and "What we offer"), ("story", plan.story_title and "Our story"),
           ("visit", plan.locations and "Visit"), ("faq", plan.faq and "FAQ")]
    nav_links = "".join(f'<a href="#{key}">{e(label)}</a>' for key, label in nav if label)
    first = plan.highlights[0] if plan.highlights else None
    landscape = bool(images) and images[0][1] / max(1, images[0][2]) > 1.25
    if hero_photo:
        media = (f'<figure class="hero-media{" landscape" if landscape else ""}"><img src="{hero_photo}" alt="{e(plan.brand)}" width="1200" height="1500" fetchpriority="high">'
                 + (f'<figcaption class="hero-badge"><strong>{e(first.title)}</strong><span>{e(first.text)}</span></figcaption>' if first else "")
                 + "</figure>")
    else:
        media = '<div class="hero-art" role="img" aria-label="Decorative illustration"><span></span></div>'
    sections = []
    if plan.highlights:
        sections.append('<section class="highlights" aria-label="Highlights"><div class="container">' + "".join(
            f'<div class="highlight"><strong>{e(item.title)}</strong><span>{e(item.text)}</span></div>' for item in plan.highlights)
            + "</div></section>")
    if plan.offerings:
        cards = "".join(
            f'<article class="card"><span class="card-index">{index + 1:02d}</span><h3>{e(item.title)}</h3><p>{e(item.text)}</p>'
            + (f'<p class="card-meta">{e(item.meta)}</p>' if item.meta else "") + "</article>"
            for index, item in enumerate(plan.offerings))
        sections.append(f'<section class="section offer" id="offer"><div class="container"><div class="section-head"><div>'
                        f'<span class="eyebrow">What we offer</span><h2>{e(plan.offer_title or "What we offer")}</h2></div>'
                        f'<p>{e(plan.offer_intro)}</p></div><div class="cards">{cards}</div></div></section>')
    if plan.story_text:
        media_html = (f'<figure class="story-media"><img src="{story_photo}" alt="Inside {e(plan.brand)}" loading="lazy" width="1000" height="1200"></figure>'
                      if story_photo else '<div class="hero-art" role="img" aria-label="Decorative illustration"><span></span></div>')
        quote = f"<blockquote>{e(plan.story_quote)}</blockquote>" if plan.story_quote else ""
        sections.append(f'<section class="section story" id="story"><div class="container">{media_html}<div>'
                        f'<span class="eyebrow">Our story</span><h2>{e(plan.story_title or "Our story")}</h2>'
                        f'<div class="story-text">{paragraphs(plan.story_text)}</div>{quote}</div></div></section>')
    if plan.steps:
        steps = "".join(f"<li><h3>{e(item.title)}</h3><p>{e(item.text)}</p></li>" for item in plan.steps)
        sections.append(f'<section class="section process"><div class="container"><div class="section-head"><div>'
                        f'<span class="eyebrow">How it works</span><h2>{e(plan.process_title or "How it works")}</h2></div></div>'
                        f'<ol class="steps">{steps}</ol></div></section>')
    if gallery:
        figures = "".join(f'<figure><img src="{name}" alt="{e(plan.brand)} photo {index + 1}" loading="lazy"></figure>'
                          for index, name in enumerate(gallery[:5]))
        sections.append(f'<section class="section gallery" aria-label="Gallery"><div class="container"><div class="section-head"><div>'
                        f'<span class="eyebrow">Gallery</span><h2>A look inside</h2></div></div><div class="gallery-grid">{figures}</div>'
                        "</div></section>")
    if plan.locations:
        places = "".join(f'<article class="location"><h3>{e(item.title)}</h3><p>{e(item.text)}</p>'
                         + (f'<p class="meta">{e(item.meta)}</p>' if item.meta else "") + "</article>" for item in plan.locations)
        sections.append(f'<section class="section visit" id="visit"><div class="container"><div class="section-head"><div>'
                        f'<span class="eyebrow">Visit</span><h2>{e(plan.visit_title or "Come and visit")}</h2></div></div>'
                        f'<div class="locations">{places}</div></div></section>')
    if plan.faq:
        questions = "".join(f"<details><summary>{e(item.title)}</summary><p>{e(item.text)}</p></details>" for item in plan.faq)
        sections.append(f'<section class="section faq" id="faq"><div class="container"><div class="section-head"><div>'
                        f'<span class="eyebrow">Questions</span><h2>Good to know</h2></div></div><div class="faq-list">{questions}</div>'
                        "</div></section>")
    if plan.closing_headline:
        sections.append(f'<section class="section closing"><div class="container"><div><h2>{e(plan.closing_headline)}</h2>'
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
<p>{('Concept by ' + e(concept_by) + ' · ') if concept_by else ''}Based on <a href="{e(source_url)}">{e(source_host)}</a></p></div></footer>
</body>
</html>
"""
    css = (KIT / "kit.css").read_text(encoding="utf-8")
    if style:
        css += f"\n:root, [data-theme=\"{plan.theme}\"] {{ {style} }}\n"
    files = {"index.html": html, "style.css": css}
    for font in FONTS:
        files[font.name] = font.read_bytes()
    for name, (data, _, _) in zip(photos, images):
        files[name] = data
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
closing_headline (inviting, 4-10 words), closing_text, enquiry_title, enquiry_text, enquiry_topics: 2-5 short options.
Rules: use only facts in the brief; never invent prices, awards, reviews, years, numbers or testimonials. Omit a section by
leaving its list empty. Write like a top agency copywriter: specific, sensory, benefit-led, no hype words."""
