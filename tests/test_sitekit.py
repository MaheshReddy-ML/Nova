import re

import pytest

from nova import demo
from nova.sitekit import SitePlan, accent_tokens, rank_photos, render
from nova.sitekit.generate import parse_plan


def plan(**overrides):
    data = {"theme": "editorial", "brand": "Elm & Clay", "tagline": "Pottery for everyone",
            "hero_headline": "Your first bowl starts here", "hero_subhead": "Beginner wheel classes in Hyderabad.",
            "highlights": [{"title": "Two studios", "text": "Kondapur and Secunderabad"}],
            "offerings": [{"title": "Wheel class", "text": "Three hours at the wheel.", "meta": "Weekends"}],
            "story_text": "We started with one wheel.", "steps": [{"title": "Book", "text": "Pick a slot."}],
            "locations": [{"title": "Kondapur", "text": "Road 1, Kondapur"}], "faq": [{"title": "Any experience?", "text": "None needed."}],
            "closing_headline": "Come make something", "enquiry_topics": ["Classes", "Events"]}
    data.update(overrides)
    return SitePlan.model_validate(data)


def test_render_is_semantic_and_self_contained():
    files = render(plan(), images=[(b"jpg", 1200, 1500)], phone="+91 90000 00000", source_url="https://elm.example/")
    html = files["index.html"]
    assert html.count("<h1>") == 1 and 'lang="en"' in html and 'data-theme="editorial"' in html
    assert all(tag in html for tag in ("<header", "<nav", "<main", "<footer", 'for="f-name"', 'for="f-email"'))
    assert "img-1.jpg" in html and files["img-1.jpg"] == b"jpg"
    assert any(name.endswith(".woff2") for name in files) and "@font-face" in files["style.css"]
    assert not re.search(r"https?://(?!elm\.example)", html.replace("http://www.w3.org", ""))
    assert all(demo.SITE_ASSET.fullmatch(name) for name in files if name not in {"index.html", "style.css"})


def test_image_free_render_uses_art_and_skips_gallery():
    html = render(plan(), images=[], source_url="https://elm.example/")["index.html"]
    assert "hero-art" in html and "gallery-grid" not in html


def test_accent_must_stay_readable():
    assert accent_tokens(plan(accent="#a8482a"))
    assert accent_tokens(plan(accent="#f6f0e6")) == ""  # pale accent on a paper background is rejected
    assert plan(accent="red").accent == ""


def test_social_cards_never_become_the_hero():
    ranked = rank_photos([(b"card", 1200, 630), (b"photo", 900, 1200)])
    assert ranked[0][0] == b"photo"


def test_plan_parser_repairs_common_model_mistakes():
    parsed = parse_plan('Here you go: {"theme": "Editorial", "brand": "Elm", "hero_headline": "Make a bowl",'
                        ' "offerings": [{"title": "Wheel", "text": 3, "price": "x"}, "junk"], "unknown": 1}')
    assert parsed.theme == "editorial" and parsed.offerings[0].text == "3"
    assert [item.title for item in parsed.offerings] == ["Wheel", "junk"]  # bare strings become titles


def test_plan_parser_repairs_benchmark_failures():
    long_intro = "Start at the centre. " * 20
    parsed = parse_plan('{"theme": "modern", "brand": "Elm", "hero_headline": "Make a bowl", "offer_intro": "' + long_intro +
                        '", "story_text": ["First paragraph.", "Second paragraph."]} {"trailing": true}')
    assert len(parsed.offer_intro) <= 240 and parsed.offer_intro.endswith(".")
    assert parsed.story_text == "First paragraph.\n\nSecond paragraph."


def test_preview_policy_allows_only_project_assets():
    _, policy = demo.sandbox_preview("<html></html>", "http://127.0.0.1:8000/projects/abc")
    assert "font-src http://127.0.0.1:8000/projects/abc/" in policy and "img-src data: http://127.0.0.1:8000/projects/abc/" in policy
    assert not demo.SITE_ASSET.fullmatch("../secret.jpg") and not demo.SITE_ASSET.fullmatch("index.php")
