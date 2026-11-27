"""Local business discovery with ratings, review counts and website status.

Preferred source: Google Places API (Text Search, New) when GOOGLE_PLACES_API_KEY is set, which returns rating,
userRatingCount and websiteUri directly. Without a key: OpenStreetMap (Nominatim + Overpass, keyless, ODbL) supplies
candidates and website tags, and ratings come from public directory snippets found by web search.
Ranking combines quality and volume with a Bayesian average, so 4.7 from 900 reviews beats 5.0 from 3.
"""
import asyncio
import re
import time

import httpx

from .domain import NovaError
from .provenance import record_fetch

AGENT = "NOVA-Agent/2.1 (local personal assistant)"
SOCIAL = ("facebook.com", "instagram.com", "wa.me", "whatsapp.com", "linktr.ee", "justdial.com", "zomato.com", "swiggy.com",
          "google.com", "business.site", "x.com", "twitter.com", "youtube.com")
# Common requests mapped to OpenStreetMap tags.
CATEGORIES = {
    "cafe": [("amenity", "cafe")], "coffee": [("amenity", "cafe")], "bakery": [("shop", "bakery")],
    "restaurant": [("amenity", "restaurant")], "food": [("amenity", "restaurant"), ("amenity", "fast_food")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")], "beauty": [("shop", "beauty")], "spa": [("leisure", "spa"), ("shop", "massage")],
    "gym": [("leisure", "fitness_centre")], "fitness": [("leisure", "fitness_centre")], "yoga": [("leisure", "fitness_centre")],
    "clinic": [("amenity", "clinic"), ("amenity", "doctors")], "doctor": [("amenity", "doctors")], "dentist": [("amenity", "dentist")],
    "pharmacy": [("amenity", "pharmacy")], "vet": [("amenity", "veterinary")], "pet": [("shop", "pet")],
    "school": [("amenity", "school")], "tuition": [("amenity", "school"), ("office", "educational_institution")],
    "boutique": [("shop", "clothes"), ("shop", "boutique")], "clothes": [("shop", "clothes")], "tailor": [("shop", "tailor"), ("craft", "tailor")],
    "florist": [("shop", "florist")], "jewellery": [("shop", "jewelry")], "jewelry": [("shop", "jewelry")],
    "optician": [("shop", "optician")], "electronics": [("shop", "electronics"), ("shop", "mobile_phone")],
    "hardware": [("shop", "hardware")], "furniture": [("shop", "furniture")], "photo": [("shop", "photo"), ("craft", "photographer")],
    "pottery": [("craft", "pottery"), ("shop", "pottery")], "art": [("shop", "art"), ("craft", "pottery")],
    "car": [("shop", "car_repair")], "garage": [("shop", "car_repair")], "laundry": [("shop", "laundry"), ("shop", "dry_cleaning")],
    "hotel": [("tourism", "hotel"), ("tourism", "guest_house")], "sweet": [("shop", "confectionery"), ("shop", "pastry")],
}
DEFAULT_TAGS = [("amenity", "cafe"), ("amenity", "restaurant"), ("shop", "bakery"), ("shop", "hairdresser"), ("shop", "beauty"),
                ("leisure", "fitness_centre"), ("amenity", "clinic"), ("shop", "clothes")]
RATING_PATTERNS = [
    re.compile(r"Rated\s+(\d(?:\.\d)?)\s+based on\s+([\d,]+)", re.I),
    re.compile(r"(\d\.\d)\s*(?:★|stars?|/\s*5|out of 5)[^.\d]{0,40}?([\d,]{1,7})\s*(?:reviews|ratings|votes)", re.I),
    re.compile(r"([\d,]{1,7})\s*(?:reviews|ratings|votes)[^.\d]{0,30}?(\d\.\d)\s*(?:★|stars?|/\s*5)?", re.I),
]


GENERIC = {"the", "cafe", "cafes", "coffee", "salon", "salons", "beauty", "hair", "unisex", "restaurant", "bakery", "bakers",
           "clinic", "studio", "shop", "store", "house", "kitchen", "hyderabad", "gachibowli", "new", "sri", "shree", "and"}


def key_name(name):
    return " ".join(re.findall(r"[a-z0-9]+", name.casefold())[:3])


def distinctive(name):
    """The most identifying word in a business name, for matching search results and website domains."""
    words = [word for word in re.findall(r"[a-z0-9]+", name.casefold()) if word not in GENERIC and len(word) >= 3]
    return (words or re.findall(r"[a-z0-9]+", name.casefold()) or [name.casefold()])[0]


def website_status(url):
    if not url:
        return "none"
    host = re.sub(r"^https?://(?:www\.)?", "", url.lower()).split("/")[0]
    return "social_only" if any(host == item or host.endswith("." + item) or item in host for item in SOCIAL) else "has_website"


def bayesian(rating, count, prior=4.0, weight=40):
    if rating is None:
        return 0.0
    count = count or 0
    return round((count / (count + weight)) * rating + (weight / (count + weight)) * prior, 3)


def parse_rating(text):
    best = None
    for pattern in RATING_PATTERNS:
        for match in pattern.finditer(text or ""):
            first, second = match.group(1), match.group(2)
            rating, count = (first, second) if "." in first or pattern is RATING_PATTERNS[0] else (second, first)
            try:
                value, reviews = float(rating), int(count.replace(",", ""))
            except ValueError:
                continue
            if 1 <= value <= 5 and reviews > 0 and (best is None or reviews > best[1]):
                best = (value, reviews)
    return best


class Places:
    def __init__(self, settings, research, store):
        self.settings, self.research, self.store = settings, research, store
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(40, connect=10), headers={"User-Agent": AGENT})
        self.osm_lock = asyncio.Lock()

    async def close(self):
        await self.client.aclose()

    async def find(self, category, area, *, without_website=True, limit=5, rate_lookups=12):
        category, area = category.strip()[:60], area.strip()[:80]
        if not category or not area:
            raise NovaError("tool_input", "Give a business category and an area, e.g. 'cafes' in 'Gachibowli, Hyderabad'.")
        key = f"places:v1:{category.casefold()}:{area.casefold()}:{without_website}"
        if (cached := self.store.cached(key)) is not None:
            return cached
        api_key = self.settings.google_places_api_key.get_secret_value()
        if api_key:
            candidates, source = await self.google(category, area, api_key), "Google Places API"
        else:
            listed = await self.directory(category, area)
            try:
                mapped = await self.osm(category, area)
            except (NovaError, httpx.HTTPError, ValueError):
                mapped = []
            seen = {key_name(item["name"]) for item in listed}
            candidates = listed + [item for item in mapped if key_name(item["name"]) not in seen]
            source = "public business directories + OpenStreetMap, with review snippets"
        for item in candidates:
            item["website_status"] = website_status(item.get("website"))
        pool = [item for item in candidates if not without_website or item["website_status"] != "has_website"]
        if not api_key:
            # Every candidate gets a lookup: it fills missing ratings and detects official websites (chains drop out).
            for item in pool[:rate_lookups]:
                await self.lookup_rating(item, area)
            # A lookup can discover a real website; those businesses no longer qualify.
            pool = [item for item in pool if not without_website or item["website_status"] != "has_website"]
        for item in pool:
            item["score"] = bayesian(item.get("rating"), item.get("reviews"))
        rated = sorted((item for item in pool if item.get("rating")), key=lambda item: (-item["score"], -(item.get("reviews") or 0)))
        unrated = [item for item in pool if not item.get("rating")]
        result = {"category": category, "area": area, "source": source, "candidates_seen": len(candidates),
                  "without_website": len([item for item in candidates if item["website_status"] != "has_website"]),
                  "ranking": "Bayesian average: rating weighted by review count (prior 4.0, weight 40 reviews)",
                  "top": rated[:limit], "unrated_examples": unrated[:3],
                  "note": ("Ratings and review counts come from Google Places." if api_key else
                           "Ratings come from public directory snippets (Justdial and similar), checked per business; set "
                           "GOOGLE_PLACES_API_KEY for Google's own ratings and review counts.")}
        self.store.cache(key, result, 6 * 3600)
        return result

    async def google(self, category, area, api_key):
        fields = ("places.displayName,places.rating,places.userRatingCount,places.websiteUri,places.nationalPhoneNumber,"
                  "places.formattedAddress,places.googleMapsUri,places.primaryTypeDisplayName,places.businessStatus,nextPageToken")
        results, token = [], None
        for _ in range(3):
            body = {"textQuery": f"{category} in {area}", "pageSize": 20, **({"pageToken": token} if token else {})}
            response = await self.client.post("https://places.googleapis.com/v1/places:searchText", json=body,
                                              headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": fields})
            record_fetch(f"https://places.googleapis.com/v1/places:searchText?q={category} in {area}", response.status_code,
                         response.content, "Google Places")
            if response.status_code != 200:
                raise NovaError("places_provider", f"Google Places returned HTTP {response.status_code}.")
            data = response.json()
            for place in data.get("places", []):
                if place.get("businessStatus", "OPERATIONAL") != "OPERATIONAL":
                    continue
                results.append({"name": place.get("displayName", {}).get("text", ""), "rating": place.get("rating"),
                                "reviews": place.get("userRatingCount"), "website": place.get("websiteUri"),
                                "phone": place.get("nationalPhoneNumber"), "address": place.get("formattedAddress"),
                                "maps": place.get("googleMapsUri"), "type": place.get("primaryTypeDisplayName", {}).get("text")})
            token = data.get("nextPageToken")
            if not token:
                break
            await asyncio.sleep(1.5)
        return results

    async def osm(self, category, area):
        async with self.osm_lock:
            geo = await self.client.get("https://nominatim.openstreetmap.org/search",
                                        params={"q": area, "format": "json", "limit": 1})
            await asyncio.sleep(1)  # Nominatim usage policy: at most one request per second
        record_fetch(f"https://nominatim.openstreetmap.org/search?q={area}", geo.status_code, geo.content, "OpenStreetMap Nominatim")
        places = geo.json() if geo.status_code == 200 else []
        if not places:
            raise NovaError("places_area", f"I couldn't locate “{area}” on the map.")
        south, north, west, east = (float(value) for value in places[0]["boundingbox"])
        if north - south < 0.04:  # small suburbs: widen to roughly 4 km
            mid_lat, mid_lon = (north + south) / 2, (east + west) / 2
            south, north, west, east = mid_lat - .02, mid_lat + .02, mid_lon - .02, mid_lon + .02
        words = set(re.findall(r"[a-z]+", category.casefold()))
        tags = [tag for word in words for tag in CATEGORIES.get(word.rstrip("s"), CATEGORIES.get(word, []))] or DEFAULT_TAGS
        box = f"({south:.4f},{west:.4f},{north:.4f},{east:.4f})"
        query = "[out:json][timeout:25];(" + "".join(f'nwr["{k}"="{v}"]["name"]{box};' for k, v in dict.fromkeys(tags)) + ");out tags center 150;"
        response = await self.client.post("https://overpass-api.de/api/interpreter", data={"data": query})
        record_fetch("https://overpass-api.de/api/interpreter", response.status_code, response.content, "OpenStreetMap Overpass")
        if response.status_code != 200:
            raise NovaError("places_provider", "OpenStreetMap search is busy. Try again shortly.", transient=True)
        results = []
        for element in response.json().get("elements", []):
            tags_ = element.get("tags", {})
            if tags_.get("brand") or tags_.get("brand:wikidata"):
                continue  # chains are not our customers
            address = ", ".join(filter(None, [tags_.get("addr:housenumber"), tags_.get("addr:street"), tags_.get("addr:suburb"),
                                              tags_.get("addr:city")]))
            results.append({"name": tags_["name"], "website": tags_.get("website") or tags_.get("contact:website"),
                            "phone": tags_.get("phone") or tags_.get("contact:phone"), "address": address or None,
                            "type": tags_.get("shop") or tags_.get("amenity") or tags_.get("craft") or tags_.get("leisure"),
                            "osm": f"https://www.openstreetmap.org/{element['type']}/{element['id']}"})
        return list({item["name"].casefold(): item for item in results}.values())

    async def directory(self, category, area):
        """Individual business listings (with ratings when the snippet shows them) from public directory search results."""
        results = []
        for query in (f"{category} in {area} site:justdial.com", f"best {category} {area} site:justdial.com"):
            try:
                found = await self.research.web_search(query, limit=10)
            except NovaError:
                continue
            for item in found["results"]:
                url = item["url"]
                if "/nct-" in url or "justdial.com" not in url or not re.search(r"justdial\.com/[^/]+/[^/]+/", url):
                    continue
                name = re.split(r"\s+in\s+|,|\s+-\s+|\s+near\s+", item["title"], maxsplit=1, flags=re.I)[0].strip()
                if not 2 < len(name) < 70 or re.match(r"(?i)(top|best|popular|\w+ near me)\b", name):
                    continue
                entry = {"name": name, "website": None, "phone": None, "address": area, "type": category,
                         "listing": url.replace("stg.justdial.com", "www.justdial.com")}
                rated = parse_rating(item["title"] + " " + item["snippet"])
                if rated:
                    entry.update(rating=rated[0], reviews=rated[1], rating_source=entry["listing"])
                results.append(entry)
        return list({key_name(item["name"]): item for item in results}.values())

    async def lookup_rating(self, item, area):
        try:
            found = await self.research.web_search(f"{item['name']} {area} reviews rating", limit=6)
        except NovaError:
            return
        best, source = None, None
        token = distinctive(item["name"])
        for result in found["results"]:
            if token not in (result["title"] + result["snippet"] + result["url"]).casefold():
                continue
            parsed = parse_rating(result["title"] + " " + result["snippet"])
            if parsed and (best is None or parsed[1] > best[1]):
                best, source = parsed, result["url"]
            host = re.sub(r"^https?://(?:www\.)?", "", result["url"].casefold()).split("/")[0]
            if not item.get("website") and website_status(result["url"]) == "has_website" and token in host.replace("-", ""):
                item["website"], item["website_status"] = result["url"], "has_website"
        if best and not item.get("rating"):
            item["rating"], item["reviews"], item["rating_source"] = best[0], best[1], source
