import re

import pytest

from nova import demo
from nova.sitekit import SitePlan, accent_tokens, arrange_photos, rank_photos, render
from nova.sitekit.generate import delivery_note, parse_plan, stock_slots, wanted_slots


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
    assert all(demo.SITE_ASSET.fullmatch(name) or name in demo.SOURCE_FILES for name in files)


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


def stock(slot, title="Clay", width=1200, height=900):
    return (f"stock-{slot}-{title}".encode(), width, height,
            {"id": f"id-{slot}", "title": title, "creator": "Ana", "creator_url": "https://example.org/ana", "license": "by",
             "license_version": "2.0", "license_url": "https://creativecommons.org/licenses/by/2.0/",
             "landing_url": "https://example.org/photo", "provider": "flickr", "query": title, "slot": slot})


def three_offers(**overrides):
    return plan(offerings=[{"title": "Wheel class", "text": "Clay."}, {"title": "Resin art", "text": "Pour."},
                           {"title": "Open mic", "text": "Sing."}], **overrides)


def test_own_photos_lead_and_stock_fills_matching_cards():
    own = (b"own", 1000, 1250)
    images = [stock(0, "Hero"), stock(2, "Resin"), own, stock(1, "Wheel"), stock(3, "Mic")]
    layout = arrange_photos(three_offers(), images)
    assert layout["hero"] is own  # the business's own photo always beats stock for the hero
    assert [item[3]["slot"] for item in layout["cards"]] == [1, 2, 3]  # each card gets the photo searched for it
    assert len({id(item) for item in layout["used"]}) == len(layout["used"])  # nothing is shown twice
    html = render(three_offers(), images=images, source_url="https://elm.example/")["index.html"]
    assert html.count('class="card has-photo"') == 3 and 'alt="Resin art"' in html
    assert "Photo credits" in html and "CC BY 2.0" in html and "https://creativecommons.org/licenses/by/2.0/" in html


def test_cards_stay_typographic_without_enough_photos():
    layout = arrange_photos(three_offers(), [(b"own", 1000, 1250)])
    assert layout["cards"] == [] and layout["gallery"] == []
    html = render(three_offers(), images=[(b"own", 1000, 1250)], source_url="https://elm.example/")["index.html"]
    assert "has-photo" not in html and "Photo credits" not in html


def test_motion_is_progressive_and_respects_reduced_motion():
    files = render(three_offers(), images=[(b"own", 1000, 1250)], source_url="https://elm.example/")
    html, css, script = files["index.html"], files["style.css"], files["demo.js"]
    assert '<script src="demo.js" defer></script>' in html and "data-reveal" in html
    # Content is only hidden under .motion, which the script sets after checking the visitor's preference.
    assert ".motion [data-reveal]" in css and "[data-reveal] {" not in css.split(".motion [data-reveal]")[0]
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in script and "reduce.matches" in script
    assert script.index("reduce.matches") < script.index('classList.add("motion")')
    motion = css.split("@media (prefers-reduced-motion: no-preference)")[1].split("@keyframes")[0]
    animated = set(re.findall(r"(?:transition|animation):\s*([a-z-]+)", motion))
    assert animated <= {"opacity", "translate", "ken-burns", "rise"}  # compositor-only properties: no layout shift
    assert "animation: none !important" in css.split("@media (prefers-reduced-motion: reduce)")[1]


def test_counters_only_for_real_counts():
    html = render(plan(highlights=[{"title": "40+ workshops"}, {"title": "Since 2023"}, {"title": "2019"}]),
                  source_url="https://elm.example/")["index.html"]
    assert html.count("data-count=") == 1 and 'data-count="40"' in html


def test_stock_queries_follow_the_plan_and_delivery_flags_placeholders():
    current = three_offers(photo_subjects=["hands on a pottery wheel", "glossy resin pour", "clay wheel throwing"])
    slots = stock_slots(current)
    assert slots[0] == ["hands on a pottery wheel"] and slots[3] == ["Open mic"]
    assert slots[2][0] == "glossy resin pour"  # subjects are matched to offerings by meaning, not by position
    assert slots[1][0] in {"hands on a pottery wheel", "clay wheel throwing"} and slots[-1] == slots[0]
    design = {"direction": "Editorial", "photo_sources": {"own": 1, "stock": 1}}
    note = delivery_note({"name": "Elm"}, design, {"score": 90, "design_score": 80}, [stock(1)[3]])
    assert "Replace them with the client's own photos" in note and "CC BY 2.0" in note


def test_proposal_mentions_stock_photos(tmp_path):
    folder = demo.project_dir(tmp_path, "abc123def456")
    demo.write_json(folder / "design.json", {"direction": "Editorial", "revision": "a" * 12, "photo_sources": {"own": 0, "stock": 3}})
    draft = demo.proposal(tmp_path, "abc123def456", {"name": "Elm", "url": "https://elm.example/", "findings": []}, {})
    assert any("representative stock" in item for item in draft["limitations"])


def test_own_photos_follow_their_alt_text_and_stock_only_fills_gaps():
    def own(alt, size):
        return (alt.encode(), size, size, {"alt": alt, "url": "https://elm.example/" + alt})
    pottery, resin, mic, room = own("Pottery Workshop", 1500), own("Resin Art", 1400), own("Open Mic", 1300), own("", 1000)
    current = plan(offerings=[{"title": "Wheel pottery class", "text": "Clay."}, {"title": "Resin art", "text": "Pour."},
                                      {"title": "Open mic", "text": "Sing."}, {"title": "Bento cakes", "text": "Pipe."}])
    layout = arrange_photos(current, [mic, pottery, room, resin])
    assert layout["hero"] is room  # the unclaimed photo leads; matched photos stay with their offering
    assert layout["cards"][:3] == [pottery, resin, mic] and layout["cards"][3] is None
    assert wanted_slots(current, [mic, pottery, room, resin]) == [4]  # only the uncovered card asks for stock
    assert wanted_slots(current, []) == [0, 1, 2, 3, 4, 5]  # nothing of their own: hero, every card, story
    html = render(current, images=[mic, pottery, room, resin, stock(4, "Bento")], source_url="https://elm.example/")["index.html"]
    assert html.count('class="card has-photo"') == 4 and "card-media-empty" not in html


def jpeg(width, height, colour):
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="JPEG")
    return buffer.getvalue()


async def test_vision_captions_override_misleading_alt_text_and_lead_photo_picks_the_hero():
    from nova.sitekit.generate import caption_photos, photo_brief

    class Vision:
        async def visual_review(self, image, description, *, instruction=None, output=600):
            assert image.startswith(b"\x89PNG") and "numbered photos" in instruction
            return {"model": "fake", "critique": "1: chocolate drip cake on a stand\n2) hands shaping clay on a wheel"}

    photos = [(jpeg(900, 1200, "brown"), 900, 1200, {"alt": "Pottery Workshop"}), (jpeg(1000, 800, "tan"), 1000, 800, {"alt": ""})]
    tagged = await caption_photos(Vision(), photos, log=lambda _: None)
    assert [item[3].get("caption") for item in tagged] == ["chocolate drip cake on a stand", "hands shaping clay on a wheel"]
    assert "1. shows: chocolate drip cake" in photo_brief(tagged) and "alt text: Pottery Workshop" in photo_brief(tagged)
    current = plan(offerings=[{"title": "Pottery wheel class", "text": "Clay."}, {"title": "Bento cakes", "text": "Cake."}],
                   lead_photo=2)
    layout = arrange_photos(current, tagged)
    assert layout["hero"] is tagged[1]  # the model's choice, not the larger photo
    assert layout["cards"] == [] or layout["cards"][1] is tagged[0]  # the cake photo follows its caption, not its alt
    html = render(current, images=tagged, source_url="https://elm.example/")["index.html"]
    assert 'alt="hands shaping clay on a wheel"' in html
    assert parse_plan('{"theme": "modern", "brand": "Elm", "hero_headline": "Make a bowl", "lead_photo": "#2"}').lead_photo == 2


def test_hero_follows_the_promise_when_the_model_does_not_choose():
    flags = (b"flags", 1600, 1200, {"caption": "Flags in front of a small building"})
    cherries = (b"cherries", 900, 1000, {"caption": "Hand holding red coffee cherries"})
    current = plan(brand="Roastery Coffee House", hero_headline="Specialty coffee roasted for you", offerings=[],
                   photo_subjects=["barista pouring coffee"])
    assert arrange_photos(current, [flags, cherries])["hero"] is cherries


def test_stock_is_kept_only_when_the_vision_caption_is_on_topic():
    from nova.sitekit.generate import choose_stock

    current = three_offers()
    def candidate(slot, caption, query):
        return (caption.encode(), 1200, 900, {"license": "by", "slot": slot, "query": query, "caption": caption})
    coaster = candidate(2, "Roller coaster at a county fair", "pour coasters")
    pour = candidate(2, "Hands pouring blue resin into a mould", "pour coasters")
    parade = candidate(3, "People marching in a street parade", "open mic stage")
    picked = choose_stock(current, [coaster, pour, parade], {2: ["resin pour coasters", "pour coasters"], 3: ["open mic stage"]})
    assert picked == [pour]  # the coaster and the parade are off-topic; the open mic card keeps its quiet panel
    assert choose_stock(current, [coaster], {2: ["resin pour coasters"]}) == []  # one shared word is not enough
    unverified = (b"x", 1200, 900, {"license": "by", "slot": 3, "query": "open mic stage"})
    assert choose_stock(current, [unverified], {3: ["open mic stage"]}) == [unverified]


def test_verified_stock_can_serve_a_sibling_slot_but_never_twice():
    from nova.sitekit.generate import choose_stock

    wheel = (b"w", 1200, 900, {"license": "cc0", "slot": 4, "query": "clay wheel", "caption": "hands shaping clay on a pottery wheel"})
    picked = choose_stock(three_offers(), [wheel], {0: ["hands shaping clay on wheel"], 4: ["hands shaping clay on wheel"]})
    assert [item[3]["slot"] for item in picked] == [0] and picked[0][0] == b"w"
