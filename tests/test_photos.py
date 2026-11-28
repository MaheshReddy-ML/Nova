"""Photo extraction from business pages and the licensed Openverse fallback."""
import asyncio
import json
from io import BytesIO

import httpx
import pytest

from nova import provenance
from nova.domain import NovaError
from nova.research import PublicResearch, image_candidates, largest_from_srcset, openverse_results
from nova.store import Store


def photo_bytes(width=900, height=700, seed=0):
    from PIL import Image

    image = Image.new("RGB", (width, height))
    image.putdata([((x * 7 + seed) % 256, (y * 5 + seed) % 256, (x * y + seed) % 256) for y in range(height) for x in range(width)])
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def test_candidates_cover_lazy_loading_css_backgrounds_and_json_ld():
    html = """<html><head>
      <meta property="og:image" content="https://cdn.example.com/og.jpg?w=1200&amp;fit=crop">
      <style>.hero { background: url('https://images.example.com/hero.jpg?q=80&w=2070') center/cover; }
             .x { filter: url(#liquid); } .y { background: url(/img/logo.png); }</style>
      <script type="application/ld+json">{"@type": "LocalBusiness", "image": ["https://shop.example.com/a.webp"],
        "photo": {"@type": "ImageObject", "contentUrl": "https://shop.example.com/b.jpg"}}</script>
      </head><body>
      <img data-src="/lazy.jpg" src="data:image/gif;base64,R0lGOD">
      <img srcset="/small.jpg 480w, /large.jpg 1600w, /medium.jpg 900w">
      <picture><source srcset="/pic-800.avif 800w, /pic-2000.avif 2000w"><img src="/pic-fallback.jpg"></picture>
      <div data-bg="/section.jpg"></div>
      <img src="/icons/favicon.png"><img src="/spinner.gif">
      <img src="https://cdn.example.com/og.jpg?w=400">
    </body></html>"""
    found = image_candidates("https://studio.example.com/", html)
    expected = {"https://cdn.example.com/og.jpg?w=1200&fit=crop", "https://images.example.com/hero.jpg?q=80&w=2070",
                "https://shop.example.com/a.webp", "https://shop.example.com/b.jpg", "https://studio.example.com/lazy.jpg",
                "https://studio.example.com/large.jpg", "https://studio.example.com/pic-2000.avif",
                "https://studio.example.com/section.jpg"}
    assert expected <= set(found)
    assert not any(word in url for url in found for word in ("logo", "favicon", "spinner", "#liquid", "data:"))
    assert len([url for url in found if "og.jpg" in url]) == 1  # one picture, two CDN renditions -> one candidate
    assert found[0].startswith("https://cdn.example.com/og.jpg")  # social card ranks first, as before


def test_srcset_picks_the_widest_candidate():
    assert largest_from_srcset("a.jpg 1x, b.jpg 2x") == "b.jpg"
    assert largest_from_srcset("a.jpg 300w,b.jpg 1200w , c.jpg 800w") == "b.jpg"
    assert largest_from_srcset("only.jpg") == "only.jpg"


async def test_files_may_carry_a_query_but_pages_and_private_hosts_may_not(tmp_path):
    store = Store(tmp_path / "t.db")
    research = PublicResearch(store)
    try:
        with pytest.raises(NovaError, match="public HTTP"):
            await research.destination("https://example.com/page?x=1")
        with pytest.raises(NovaError, match="public"):
            await research.destination("http://127.0.0.1/img.jpg?w=1", allow_query=True)
        with pytest.raises(NovaError, match="public HTTP"):
            await research.destination("https://example.com/a b.jpg?w=1", allow_query=True)
    finally:
        await research.close()
        store.db.close()


def fake_network(research, handler):
    """Route the research client through a mock transport and skip DNS (addresses are tested separately)."""
    async def destination(url, allow_query=False):
        if "?" in url and not allow_query:
            raise NovaError("invalid_target", "Research accepts public HTTP(S) pages only.")
        return url, httpx.URL(url).host

    async def robots(url, strict=True):
        return "blocked.example" not in url

    research.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    research.destination = destination
    research.robots = robots


async def test_cdn_redirects_are_followed_without_deadlocking(tmp_path):
    store = Store(tmp_path / "t.db")
    research = PublicResearch(store)
    image = photo_bytes()

    def handler(request):
        if request.url.path == "/0*abc":
            return httpx.Response(302, headers={"location": "https://cdn.example.com/resized/abc.jpg?w=1600"})
        assert request.url.query == b"w=1600"  # the rendition query survives pinning
        return httpx.Response(200, content=image, headers={"content-type": "image/jpeg"})

    fake_network(research, handler)
    try:
        data, kind = await asyncio.wait_for(research.fetch_bytes("https://cdn.example.com/0*abc?w=2070"), 5)
        assert data == image and kind == "image/jpeg"
    finally:
        await research.close()
        store.db.close()


OPENVERSE_PAYLOAD = {"results": [
    {"id": "m1", "title": "Mature", "url": "https://img.example.com/m.jpg", "thumbnail": "https://api.openverse.org/v1/images/m1/thumb/",
     "license": "by", "mature": True, "width": 2000},
    {"id": "nc", "title": "Non-commercial", "url": "https://img.example.com/nc.jpg",
     "thumbnail": "https://api.openverse.org/v1/images/nc/thumb/", "license": "by-nc", "width": 2000},
    {"id": "blocked", "title": "Robots say no", "url": "https://blocked.example/p.jpg",
     "thumbnail": "https://api.openverse.org/v1/images/blocked/thumb/", "license": "cc0", "width": 2000},
    {"id": "ok1", "title": "Hands on a wheel", "url": "https://img.example.com/wheel.jpg", "creator": "Ana",
     "creator_url": "https://img.example.com/ana", "thumbnail": "https://api.openverse.org/v1/images/ok1/thumb/",
     "license": "by", "license_version": "2.0", "license_url": "https://creativecommons.org/licenses/by/2.0/",
     "foreign_landing_url": "https://img.example.com/photo/1", "source": "flickr", "width": 3000, "height": 2000},
    {"id": "ok2", "title": "Resin pour", "url": "https://img.example.com/resin.jpg", "creator": None,
     "thumbnail": "https://api.openverse.org/v1/images/ok2/thumb/", "license": "cc0", "license_version": "1.0",
     "license_url": "javascript:alert(1)", "source": "rawpixel", "width": 3000, "height": 2000},
]}


def test_openverse_results_keep_attribution_and_drop_unlicensed_or_unsafe():
    results = openverse_results(OPENVERSE_PAYLOAD)
    assert [item["id"] for item in results] == ["blocked", "ok1", "ok2"]
    first = next(item for item in results if item["id"] == "ok1")
    assert first["creator"] == "Ana" and first["license"] == "by" and first["landing_url"] == "https://img.example.com/photo/1"
    assert next(item for item in results if item["id"] == "ok2")["license_url"] == ""  # non-https links are dropped


async def test_stock_photos_use_openverse_with_licence_filters_safe_fetch_and_provenance(tmp_path):
    store = Store(tmp_path / "t.db")
    research = PublicResearch(store)
    requests = []

    def handler(request):
        requests.append(str(request.url))
        if request.url.host == "api.openverse.org":
            params = dict(request.url.params)
            assert params["license_type"] == "commercial,modification" and params["mature"] == "false"
            assert params["category"] == "photograph"
            return httpx.Response(200, json=OPENVERSE_PAYLOAD)
        size = (640, 520) if "resin" in request.url.path else (900, 700)
        return httpx.Response(200, content=photo_bytes(*size), headers={"content-type": "image/jpeg"})

    fake_network(research, handler)
    token, fetches = provenance.begin()
    try:
        photos = await research.stock_photos([["pottery wheel hands"], ["nonexistent thing", "resin art"]], 2)
    finally:
        provenance.end(token)
        await research.close()
        store.db.close()
    assert [photo[3]["id"] for photo in photos] == ["ok1", "ok2"]
    assert [photo[3]["slot"] for photo in photos] == [0, 1] and photos[0][3]["query"] == "pottery wheel hands"
    assert photos[0][1] == 900 and photos[0][0][:2] == b"\xff\xd8"  # normalised JPEG through prepare_photo
    assert not any("blocked.example" in url or "nc.jpg" in url for url in requests)
    assert any(item["provider"] == "Openverse" for item in fetches) and any(item["provider"] == "web-file" for item in fetches)
    assert json.dumps(photos[0][3])  # credits are JSON-serialisable for design.json


def test_candidates_carry_alt_text_for_offering_matching():
    html = '<img src="/a.jpg?w=2000" alt="Resin Art"><img data-src="/b.jpg" alt=" Open   Mic "><div data-bg="/c.jpg"></div>'
    pairs = dict(image_candidates("https://studio.example.com/", html, with_alt=True))
    assert pairs["https://studio.example.com/a.jpg?w=2000"] == "Resin Art"
    assert pairs["https://studio.example.com/b.jpg"] == "Open Mic" and pairs["https://studio.example.com/c.jpg"] == ""


def test_specific_subjects_relax_to_shorter_queries():
    from nova.research import relax_query

    assert relax_query("bento cake decorating") == ["bento cake decorating", "cake decorating", "bento cake"]
    assert relax_query("hands shaping clay wheel")[:3] == ["hands shaping clay wheel", "shaping clay wheel", "clay wheel"]
    assert relax_query("resin art") == ["resin art"]


def test_relaxed_queries_skip_filler_words():
    from nova.research import relax_query

    assert relax_query("hands shaping clay on wheel") == ["hands shaping clay on wheel", "shaping clay wheel", "clay wheel", "hands shaping"]
