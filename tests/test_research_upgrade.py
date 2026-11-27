from urllib.parse import parse_qs

import httpx
import pytest

from nova.domain import NovaError
from nova.research_wikidata import WikidataLookup, active_site_claims, public_claim
from nova.store import Store


def statement(value, rank="normal", qualifiers=None, value_type="string"):
    return {"rank": rank, "qualifiers": qualifiers or {},
            "mainsnak": {"snaktype": "value", "datavalue": {"type": value_type, "value": value}}}


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://169.254.169.254/", "https://bad.local/",
                                  "https://example.com/?private=1", "https://me@example.com/", "https://instagram.com/user"])
def test_public_business_claims_exclude_unsafe_and_social_urls(url):
    assert not public_claim(url)


def test_claims_skip_people_and_superseded_urls():
    site = "https://www.tajhotels.com/"
    assert active_site_claims({"claims": {"P856": [statement(site, "preferred"), statement("https://old.example.com/", qualifiers={"P582": [{}]})]}}) == [site]
    person = statement({"entity-type": "item", "id": "Q5", "numeric-id": 5}, value_type="wikibase-entityid")
    assert active_site_claims({"claims": {"P31": [person], "P856": [statement(site)]}}) == []


async def test_wikidata_search_preserves_provenance_and_reuses_cache(tmp_path):
    seen = []
    store = Store(tmp_path / "nova.db")

    def provider(request):
        params = parse_qs(request.url.query.decode())
        seen.append(params)
        if params["action"] == ["wbsearchentities"]:
            return httpx.Response(200, json={"search": [{"id":"Q1521893", "label":"Taj Hotels"}]})
        return httpx.Response(200, json={"entities": {"Q1521893": {"claims": {"P856": [statement("https://www.tajhotels.com/")]}}}})

    async def allow_url(url):
        assert url == "https://www.tajhotels.com/"

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        lookup = WikidataLookup(client, store, allow_url)
        first = await lookup.search("Taj Hotels", interactive=True)
        second = await lookup.search("taj hotels")
    assert len(seen) == 2 and all("maxlag" not in params for params in seen)
    assert first["candidates"][0]["listed_by"] == "https://www.wikidata.org/wiki/Q1521893"
    assert second["cache_hit"] is True
    store.db.close()


async def test_background_wikidata_preserves_provider_backoff(tmp_path):
    store = Store(tmp_path / "nova.db")
    seen = []
    def provider(request):
        seen.append(request)
        return httpx.Response(200, json={"error": {"code":"maxlag"}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        lookup = WikidataLookup(client, store, None)
        for _ in range(2):
            with pytest.raises(NovaError) as error:
                await lookup.search("Taj Hotels")
            assert error.value.transient and error.value.retry_after >= 1
    assert len(seen) == 1 and b"maxlag=5" in seen[0].url.query
    store.db.close()
