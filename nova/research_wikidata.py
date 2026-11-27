import asyncio
import hashlib
import ipaddress
import json
import re
import time
import unicodedata
from urllib.parse import urlsplit

import httpx

from .domain import Candidate, NovaError

API = "https://www.wikidata.org/w/api.php"
SOURCE = "https://www.wikidata.org/wiki/Wikidata:Main_Page"
ITEM = re.compile(r"Q[1-9]\d{0,14}")
LIMIT = 6
MAX_BYTES = 1_500_000
SOCIAL_HOSTS = frozenset({"facebook.com", "instagram.com", "linkedin.com", "youtube.com", "x.com", "tiktok.com", "twitter.com"})


def public_claim(url):
    try:
        if not isinstance(url, str) or not 10 <= len(url) <= 500 or "\\" in url:
            return False
        if any(unicodedata.category(c) in {"Cc", "Cf"} for c in url):
            return False
        parsed = urlsplit(url)
        if (parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.port is not None
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment):
            return False
        host = parsed.hostname.lower().rstrip(".")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address:
            return address.is_global and not (address.is_reserved or address.is_multicast)
        if "." not in host or host.endswith((".localhost", ".local", ".internal")) or host.endswith(".wikidata.org"):
            return False
        return not any(domain == host or host.endswith("." + domain) for domain in SOCIAL_HOSTS)
    except (ValueError, UnicodeError):
        return False


def active_site_claims(entity):
    claims = entity.get("claims", {})
    if not isinstance(claims, dict):
        return []
    instances = claims.get("P31", [])
    if isinstance(instances, list):
        if any(isinstance(row, dict) and claim_value(row, "wikibase-entityid") == {"entity-type": "item", "id": "Q5"}
               for row in instances):
            return []
        for row in instances:
            kind = claim_value(row, "wikibase-entityid")
            if isinstance(kind, dict) and kind.get("id") in {"Q5", "Q13442814", "Q4167410"}:
                return []
    rows = claims.get("P856", [])
    if not isinstance(rows, list):
        return []
    ranked = []
    for row in rows[:20]:
        if not isinstance(row, dict) or row.get("rank") not in {"normal", "preferred"}:
            continue
        qualifiers = row.get("qualifiers", {})
        if isinstance(qualifiers, dict) and qualifiers.get("P582"):
            continue
        url = claim_value(row, "string")
        if public_claim(url):
            ranked.append((row["rank"] != "preferred", not url.startswith("https://"), url))
    return [item[-1] for item in sorted(ranked)]


def claim_value(claim, value_type):
    if not isinstance(claim, dict):
        return None
    main = claim.get("mainsnak")
    if not isinstance(main, dict) or main.get("snaktype") != "value":
        return None
    data = main.get("datavalue")
    if not isinstance(data, dict) or data.get("type") != value_type:
        return None
    return data.get("value")


class WikidataLookup:
    def __init__(self, client, store, public_destination, *, contact=""):
        self.client = client
        self.store = store
        self.public_destination = public_destination
        self.lock = asyncio.Lock()
        self.next_request = 0.0
        self.pause_until = 0.0
        self.user_agent = "NOVA-Research/2.0 (local named-organization lookup)"
        if re.fullmatch(r"(?:https://[A-Za-z0-9._~/?#@:+%=-]{4,140}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,16})", contact, re.ASCII):
            self.user_agent = f"NOVA-Research/2.0 ({contact})"

    def backoff(self, retry_after):
        seconds = int(retry_after) if re.fullmatch(r"[0-9]{1,5}", retry_after or "") else 15
        delay = max(1, min(300, seconds))
        self.pause_until = max(self.pause_until, time.monotonic() + delay)
        return NovaError("research_provider_busy", "Wikidata asked NOVA to slow down.", transient=True, retry_after=delay)

    async def request(self, action, *, interactive=False, **params):
        if self.pause_until > time.monotonic():
            raise NovaError("research_provider_busy", "Wikidata is temporarily rate-limited.", transient=True,
                            retry_after=max(1, self.pause_until - time.monotonic()))
        await asyncio.sleep(max(0, self.next_request - time.monotonic()))
        self.next_request = time.monotonic() + 1
        collect = bytearray()
        if not interactive:
            params["maxlag"] = 5
        try:
            async with asyncio.timeout(18):
                async with self.client.stream(
                    "GET", API, params={"action": action, "format": "json", **params},
                    headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                ) as response:
                    if response.status_code in (429, 503):
                        raise self.backoff(response.headers.get("retry-after"))
                    if response.status_code != 200:
                        raise NovaError("research_provider_http", f"Wikidata returned HTTP {response.status_code}.",
                                        transient=response.status_code >= 500)
                    async for chunk in response.aiter_bytes():
                        collect.extend(chunk)
                        if len(collect) > MAX_BYTES:
                            raise NovaError("research_provider_size", "The Wikidata response exceeded the research limit.")
        except (httpx.HTTPError, TimeoutError) as exc:
            raise NovaError("research_provider_network", "Could not reach Wikidata.", transient=True) from exc
        try:
            document = json.loads(collect)
        except (UnicodeError, ValueError) as exc:
            raise NovaError("research_provider_response", "Wikidata returned unreadable research data.") from exc
        if not isinstance(document, dict):
            raise NovaError("research_provider_response", "Wikidata returned malformed research data.")
        if error := document.get("error"):
            if isinstance(error, dict) and error.get("code") in {"maxlag", "ratelimited", "readonly"}:
                raise self.backoff(None)
            raise NovaError("research_provider_response", "Wikidata could not complete the lookup.")
        return document

    async def candidate(self, item_id, name, entity):
        if isinstance(entity.get("labels"), dict):
            entry = entity["labels"].get("en")
            if isinstance(entry, dict) and isinstance(entry.get("value"), str):
                name = entry["value"]
        if not isinstance(name, str):
            return None
        name = " ".join(name.split())
        if (not 2 <= len(name) <= 100 or
                any(unicodedata.category(char) in {"Cc", "Cf"} and char not in ("\u200c", "\u200d") for char in name)):
            return None
        for url in active_site_claims(entity)[:2]:
            try:
                await self.public_destination(url)
                return Candidate(name=name, url=url, listed_by=f"https://www.wikidata.org/wiki/{item_id}")
            except (NovaError, ValueError):
                continue
        return None

    async def search(self, query, *, interactive=False):
        query = " ".join(unicodedata.normalize("NFKC", query).split())
        if not 2 <= len(query) <= 100 or not any(char.isalpha() for char in query):
            raise NovaError("research_query", "Enter a public organization name between 2 and 100 characters.")
        key = "wikidata-search:v1:" + hashlib.sha256(query.casefold().encode()).hexdigest()
        async with self.lock:
            if (cached := self.store.cached(key)) is not None:
                self.store.log("cache", "Reused Wikidata lookup results")
                return {**cached, "cache_hit": True}
            response = await self.request("wbsearchentities", interactive=interactive, search=query, type="item", language="en",
                                          uselang="en", limit=LIMIT)
            found = response.get("search")
            if not isinstance(found, list):
                raise NovaError("research_provider_response", "Wikidata returned malformed search results.")
            ids = {}
            for row in found[:LIMIT]:
                if not isinstance(row, dict):
                    continue
                item_id = row.get("id")
                if isinstance(item_id, str) and ITEM.fullmatch(item_id):
                    ids[item_id] = row.get("label")
            candidates = []
            if ids:
                response = await self.request("wbgetentities", interactive=interactive, ids="|".join(ids), props="claims|labels", languages="en")
                entities = response.get("entities")
                if not isinstance(entities, dict):
                    raise NovaError("research_provider_response", "Wikidata returned malformed entity records.")
                matches = await asyncio.gather(*(self.candidate(item_id, label, entities[item_id])
                                                  for item_id, label in ids.items()
                                                  if isinstance(entities.get(item_id), dict)))
                seen = set()
                for match in matches:
                    if match is None:
                        continue
                    host = urlsplit(match.url).hostname.rstrip(".").removeprefix("www.")
                    if host in seen:
                        continue
                    seen.add(host)
                    candidates.append(match.model_dump())
                    if len(candidates) == 5:
                        break
            result = {"source": SOURCE, "provider": "wikidata", "candidates": candidates}
            self.store.cache(key, result, 12 * 3600 if candidates else 3600)
            return {**result, "cache_hit": False}
