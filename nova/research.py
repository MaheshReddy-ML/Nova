import asyncio
import ipaddress
import json
import os
import re
import socket
import time
from html import unescape
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .domain import Candidate, NovaError
from .provenance import record_fetch
from .outreach import valid_address
from .research_wikidata import WikidataLookup

USER_AGENT = "NOVA-Research/0.1"
BROWSER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) NOVA-Agent/2.1"
MAX_PAGE = 1_500_000


class PublicResearch:
    def __init__(self, store, *, wikidata_contact=None):
        self.store = store
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(14, connect=6), trust_env=False,
                                        follow_redirects=False, limits=httpx.Limits(max_connections=3))
        self.lock = asyncio.Lock()
        self.next_request = 0.0
        contact = os.getenv("WIKIDATA_CONTACT", "") if wikidata_contact is None else wikidata_contact
        self.brave_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
        self.search_cooldown = 0.0
        self.wikidata = WikidataLookup(self.client, store, self.destination, contact=contact)

    async def close(self):
        await self.client.aclose()

    async def destination(self, url):
        try:
            source = urlsplit(url)
            if (source.scheme not in ("http", "https") or not source.hostname or source.username or source.password
                    or source.port or source.query or len(url) > 1000 or "\\" in url):
                raise ValueError()
            hostname = source.hostname.encode("idna").decode()
            if not re.fullmatch(r"[a-zA-Z0-9.-]+", hostname) or "." not in hostname:
                raise ValueError()
        except (UnicodeError, ValueError) as exc:
            raise NovaError("invalid_target", "Research accepts public HTTP(S) pages only.") from exc
        try:
            port = 443 if source.scheme == "https" else 80
            addresses = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(hostname, port, type=socket.SOCK_STREAM), timeout=5,
            )
        except (OSError, TimeoutError) as exc:
            raise NovaError("dns", "The public website hostname could not be resolved.", transient=True) from exc
        ips = sorted({ipaddress.ip_address(item[4][0]) for item in addresses}, key=lambda item: (item.version, int(item)))
        if not ips or any(not ip.is_global or ip.is_multicast or ip.is_reserved for ip in ips):
            raise NovaError("private_target", "Research is limited to public internet addresses.")
        address = f"[{ips[0]}]" if ips[0].version == 6 else str(ips[0])
        return urlunsplit((source.scheme, address, source.path or "/", "", "")), hostname

    async def request(self, url):
        pinned, hostname = await self.destination(url)
        async with self.lock:
            await asyncio.sleep(max(0, self.next_request - time.monotonic()))
            self.next_request = time.monotonic() + 1
            start = time.perf_counter()
            try:
                async with self.client.stream("GET", pinned, headers={
                    "Host": hostname, "User-Agent": USER_AGENT, "Accept": "text/html,text/plain",
                    "Accept-Encoding": "identity", "Connection": "close",
                }, extensions={"sni_hostname": hostname}) as response:
                    status = response.status_code
                    elapsed = round((time.perf_counter() - start) * 1000)
                    data = bytearray()
                    if status == 200:
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > MAX_PAGE:
                                raise NovaError("page_limit", "The page exceeded the research download limit.")
                    record_fetch(url, status, bytes(data), "web")
                    return status, response.headers, data.decode(response.encoding or "utf-8", errors="replace"), elapsed
            except httpx.HTTPError as exc:
                raise NovaError("web_network", "Could not fetch the public page.", transient=True) from exc

    async def robots(self, url, strict=True):
        origin = urlsplit(url)._replace(path="", query="", fragment="").geturl()
        key = f"robots:{origin}"
        found = self.store.cached(key)
        if found is None:
            target = origin + "/robots.txt"
            for _ in range(4):
                status, headers, text, _ = await self.request(target)
                if status not in (301, 302, 303, 307, 308):
                    break
                target = urljoin(target, headers.get("location", ""))
                if urlsplit(target).netloc != urlsplit(origin).netloc:
                    return False
            if status in (404, 410) or (status == 200 and "text/html" in headers.get("content-type", "")):
                found = []
            elif status == 200:
                found = text.splitlines()[:4000]
            else:
                return False
            self.store.cache(key, found, 3600)
        rules = RobotFileParser()
        rules.parse(found)
        if not strict:
            return rules.can_fetch(USER_AGENT, url)
        return rules.can_fetch(USER_AGENT, url) and not (rules.crawl_delay(USER_AGENT) or rules.request_rate(USER_AGENT))

    async def audit(self, candidate):
        key = f"public-audit:v3:{candidate.url}"
        origin = {"name": candidate.name, "source_directory": candidate.listed_by}
        cached = self.store.cached(key)
        if cached is not None:
            self.store.log("cache", "Reused a public website audit")
            return {**cached, **origin, "cache_hit": True}
        target, html, elapsed = await self.html(candidate.url)
        result = await asyncio.to_thread(inspect, target, html, elapsed)
        self.store.cache(key, result, 1800)
        return {**result, **origin, "cache_hit": False}

    async def search(self, query: str, *, interactive=False):
        return await self.wikidata.search(query, interactive=interactive)

    async def topic(self, query):
        key = f"public-topic:v1:{query.casefold()}"
        if cached := self.store.cached(key):
            return cached
        params = {"action": "query", "generator": "search", "gsrsearch": query[:180], "gsrnamespace": 0,
                  "gsrlimit": 3, "prop": "extracts|info", "inprop": "url", "exintro": 1,
                  "explaintext": 1, "exchars": 550, "format": "json", "formatversion": 2}
        async with self.lock:
            await asyncio.sleep(max(0, self.next_request - time.monotonic()))
            self.next_request = time.monotonic() + 1
            try:
                async with self.client.stream("GET", "https://en.wikipedia.org/w/api.php", params=params,
                                              headers={"User-Agent": "NOVA-Research/2.0 (local encyclopedia lookup)"}) as response:
                    if response.status_code != 200:
                        raise NovaError("topic_provider", "Wikipedia could not complete the lookup.", transient=response.status_code in {429, 502, 503})
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 150_000:
                            raise NovaError("topic_provider", "The topic response exceeded the research limit.")
                    record_fetch(f"https://en.wikipedia.org/w/api.php?search={query[:80]}", response.status_code, bytes(data), "Wikipedia")
                    pages = json.loads(data).get("query", {}).get("pages", [])
            except httpx.HTTPError as exc:
                raise NovaError("topic_provider", "The topic source is temporarily unreachable.", transient=True) from exc
            except ValueError as exc:
                raise NovaError("topic_provider", "The topic source returned an unreadable result.") from exc
        sources = []
        for page in sorted(pages, key=lambda item: item.get("index", 99))[:3]:
            if type(page.get("pageid")) is int and page.get("extract"):
                sources.append({"name": page["title"][:140], "url": f"https://en.wikipedia.org/?curid={page['pageid']}",
                                "extract": page["extract"][:550]})
        if not sources:
            raise NovaError("no_evidence", "Wikipedia did not return an introductory source for that topic.")
        result = {"provider": "Wikipedia", "sources": sources}
        self.store.cache(key, result, 3600)
        return result

    async def web_search(self, query, limit=6):
        """Web search: Brave Search API when BRAVE_SEARCH_API_KEY is set, otherwise DuckDuckGo's HTML endpoint (best effort).

        A rate-limited provider is reported instead of silently substituting unrelated results."""
        query = " ".join(query.split())[:200]
        key = f"web-search:v2:{query.casefold()}"
        if (cached := self.store.cached(key)) is not None:
            record_fetch(f"search:{query}", "cache", json.dumps(cached), cached.get("provider") or "search cache")
            return cached
        results, provider, limited = [], None, False
        if self.brave_key:
            try:
                response = await self.client.get("https://api.search.brave.com/res/v1/web/search",
                                                 params={"q": query, "count": min(limit + 2, 20), "country": "IN"},
                                                 headers={"X-Subscription-Token": self.brave_key, "Accept": "application/json"})
                record_fetch(f"https://api.search.brave.com/?q={query}", response.status_code, response.content, "Brave Search")
                if response.status_code == 200:
                    results = [{"title": item.get("title", "")[:160], "url": item.get("url", "")[:500],
                                "snippet": re.sub(r"<[^>]+>", "", item.get("description", ""))[:320]}
                               for item in response.json().get("web", {}).get("results", []) if item.get("url")][:limit]
                    provider = "Brave Search"
                limited = response.status_code == 429
            except (httpx.HTTPError, ValueError):
                pass
        if not results and time.monotonic() >= self.search_cooldown:
            async with self.lock:
                await asyncio.sleep(max(0, self.next_request - time.monotonic()))
                self.next_request = time.monotonic() + 1.2
                try:
                    response = await self.client.post(
                        "https://html.duckduckgo.com/html/", data={"q": query, "kl": "in-en"},
                        headers={"User-Agent": BROWSER_AGENT, "Accept": "text/html", "Referer": "https://html.duckduckgo.com/"})
                    record_fetch(f"https://html.duckduckgo.com/html/?q={query}", response.status_code, response.content, "DuckDuckGo")
                    if response.status_code == 200 and "anomaly" not in response.text[:20000].lower():
                        results = await asyncio.to_thread(parse_search, response.text, limit)
                        provider = "DuckDuckGo"
                    elif response.status_code in (202, 403, 429) or "anomaly" in response.text[:20000].lower():
                        # The provider is throttling automated traffic: back off instead of retrying.
                        self.search_cooldown = time.monotonic() + 600
                        limited = True
                except httpx.HTTPError:
                    pass
        elif not results:
            limited = True
        if not results and limited:
            raise NovaError("search_rate_limited", "Web search is temporarily rate-limited. Set BRAVE_SEARCH_API_KEY in .env "
                            "for reliable search, or try again in about ten minutes.", transient=True)
        result = {"query": query, "results": results, "provider": provider}
        if results:
            self.store.cache(key, result, 3600)
        return result

    async def read_page(self, url):
        """Readable text, structure and contact channels of one public page (owner-directed)."""
        url = normalize_url(url)
        key = f"read-page:v1:{url}"
        if (cached := self.store.cached(key)) is not None:
            record_fetch(url, "cache", cached.get("text", ""), "page cache")
            return cached
        target, html, elapsed = await self.html(url, strict=False)
        result = await asyncio.to_thread(readable, target, html)
        result["elapsed_ms"] = elapsed
        self.store.cache(key, result, 1800)
        return result

    async def contacts(self, url):
        """Collect published contact channels from a homepage and its contact page."""
        url = normalize_url(url)
        key = f"contacts:v1:{url}"
        if (cached := self.store.cached(key)) is not None:
            return cached
        page = await self.read_page(url)
        found = {name: list(page["contacts"][name]) for name in ("emails", "phones", "whatsapp", "social")}
        visited = [page["url"]]
        origin = urlsplit(page["url"])._replace(path="/", query="", fragment="").geturl()
        guesses = [page["contacts"].get("contact_page"), urljoin(origin, "/contact"), urljoin(origin, "/contact-us")]
        for extra in [item for item in dict.fromkeys(guesses) if item and item not in visited]:
            if found["emails"] and len(visited) > 1:
                break
            try:
                detail = await self.read_page(extra)
            except NovaError:
                continue
            visited.append(detail["url"])
            for name in found:
                found[name] = list(dict.fromkeys(found[name] + detail["contacts"][name]))[:6]
        result = {"url": page["url"], "title": page["title"], "visited": visited,
                  "contact_page": page["contacts"].get("contact_page") or (visited[1] if len(visited) > 1 else None),
                  **found}
        self.store.cache(key, result, 3600)
        return result

    async def fetch_bytes(self, url, limit=4_000_000):
        """Download one public binary resource (e.g. an image) through the pinned, rate-limited client."""
        if not await self.robots(url, strict=False):
            raise NovaError("robots", "The website's crawling policy disallows this file.")
        pinned, hostname = await self.destination(url)
        async with self.lock:
            await asyncio.sleep(max(0, self.next_request - time.monotonic()))
            self.next_request = time.monotonic() + 0.4
            try:
                async with self.client.stream("GET", pinned, headers={
                    "Host": hostname, "User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/jpeg,image/png,*/*;q=0.5",
                    "Accept-Encoding": "identity", "Connection": "close",
                }, extensions={"sni_hostname": hostname}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = urljoin(url, response.headers.get("location", ""))
                        if location == url:
                            raise NovaError("redirect", "The file redirected to itself.")
                        return await self.fetch_bytes(location, limit) if location.startswith("https://") else (b"", "")
                    if response.status_code != 200:
                        raise NovaError("site_response", f"The file returned HTTP {response.status_code}.")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > limit:
                            raise NovaError("page_limit", "The file exceeded the download limit.")
                    record_fetch(url, response.status_code, bytes(data), "web-file")
                    return bytes(data), response.headers.get("content-type", "")
            except httpx.HTTPError as exc:
                raise NovaError("web_network", "Could not fetch the file.", transient=True) from exc

    async def images(self, url, limit=6):
        """Photos published on a business's own page, best first: (bytes, width, height) as JPEG, max 1600 px wide."""
        target, html, _ = await self.html(normalize_url(url), strict=False)
        candidates = await asyncio.to_thread(image_candidates, target, html)
        photos = []
        for candidate in candidates[:14]:
            if len(photos) >= limit:
                break
            try:
                data, kind = await self.fetch_bytes(candidate)
            except NovaError:
                continue
            if not kind.startswith("image/") or "svg" in kind:
                continue
            photo = await asyncio.to_thread(prepare_photo, data)
            if photo and all(abs(len(photo[0]) - len(item[0])) > 2000 for item in photos):
                photos.append(photo)
        return photos

    async def discover(self, url):
        key = f"public-directory:v1:{url}"
        if (cached := self.store.cached(key)) is not None:
            self.store.log("cache", "Reused public directory candidates")
            return cached
        target, html, _ = await self.html(url)
        candidates = await asyncio.to_thread(directory_links, target, html)
        if not candidates:
            raise NovaError("directory_empty", "The public directory did not link to any named business homepages.")
        result = {"source": target, "candidates": [item.model_dump() for item in candidates]}
        self.store.cache(key, result, 3600)
        return result

    async def html(self, target, strict=True):
        for _ in range(5):
            if not await self.robots(target, strict):
                raise NovaError("robots", "The website's crawling policy could not authorize this check.")
            status, headers, html, elapsed = await self.request(target)
            if status not in (301, 302, 303, 307, 308):
                break
            location = headers.get("location")
            if not location:
                raise NovaError("redirect", "The website returned an incomplete redirect.")
            target = urljoin(target, location)
        if status != 200:
            raise NovaError("site_response", f"The public page returned HTTP {status}.", transient=status >= 500 or status == 429)
        if "text/html" not in headers.get("content-type", ""):
            raise NovaError("page_type", "The public URL did not return HTML.")
        return target, html, elapsed


def directory_links(source, html):
    soup = BeautifulSoup(html, "html.parser")
    region = soup.find("article") or soup.find("main") or soup.body or soup
    excluded = {"facebook.com", "instagram.com", "linkedin.com", "youtube.com", "x.com", "tiktok.com", "google.com"}
    seen = {urlsplit(source).hostname.removeprefix("www."), *excluded}
    candidates = []
    for node in region.find_all("a", href=True, limit=250):
        label = node.get_text(" ", strip=True).split(" | ", maxsplit=1)[0].strip()
        if not 3 <= len(label) <= 100 or label.casefold() in {"click here", "website", "learn more", "visit website"}:
            continue
        try:
            target = urlsplit(node["href"])
            if target.scheme not in {"http", "https"} or not target.hostname or target.path not in {"", "/"}:
                continue
            hostname = target.hostname.removeprefix("www.")
            if hostname in seen or any(hostname.endswith("." + domain) for domain in excluded):
                continue
            candidate = Candidate(name=label, url=target.geturl(), listed_by=source)
        except ValueError:
            continue
        candidates.append(candidate)
        seen.add(hostname)
        if len(candidates) >= 5:
            break
    return candidates


def inspect(url, html, elapsed):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    headings = [node.get_text(" ", strip=True)[:140] for node in soup.find_all("h1", limit=12)]
    visible = soup.body or soup
    controls = visible.select("a[href],button,[role=button]", limit=300)
    forms = visible.find_all("form", limit=15)
    images = visible.find_all("img", limit=150)
    missing = sum(not node.has_attr("alt") for node in images)
    labels = {node["for"] for node in visible.find_all("label", attrs={"for": True}, limit=200)
              if node.get_text(strip=True)}
    fields = [node for form in forms for node in form.select(
        "input:not([type=hidden]):not([type=submit]):not([type=button]),textarea,select", limit=75
    )]
    without_label = [
        node for node in fields if node.get("id") not in labels and not node.get("aria-label")
        and not node.get("aria-labelledby") and not node.find_parent("label")
    ]
    flags = []

    def finding(points, observation, change):
        flags.append({"points": points, "observation": observation, "change": change})

    if not soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}):
        finding(28, "No viewport meta tag was present in the public HTML.", "Set a mobile viewport and use a single-column layout on narrow screens.")
    if not title:
        finding(14, "The inspected page has no nonempty title element.", "Give the page a descriptive, business-specific title.")
    if not any(headings):
        finding(15, "No nonempty H1 was found in the public HTML.", "Add a clear page heading that introduces the offering.")
    if len([item for item in headings if item]) > 1:
        finding(5, f"The HTML contains {len(headings)} H1 elements.", "Use a clear page-level heading and arrange sections under H2 headings.")
    if missing:
        finding(min(20, 4 + missing * 2), f"{missing} of {len(images)} inspected images had no alt attribute.",
                "Provide text alternatives for meaningful images and empty alt attributes for decorative images.")
    if without_label:
        finding(min(24, 8 + len(without_label) * 3),
                f"{len(without_label)} of {len(fields)} form fields had no HTML label or ARIA label.",
                "Add persistent, programmatically associated labels to the enquiry fields.")
    if not soup.html or not soup.html.get("lang"):
        finding(8, "The document has no declared language.", "Declare the page language on the HTML element.")
    action = re.compile(r"\b(book|reserve|enquire|inquire|contact|class(?:es)?|courses?|schedule|appointment|whatsapp|booking|tickets?)\b", re.I)
    source = urlsplit(url)
    next_url = None
    contact_page = None
    public_emails = set()
    for node in controls:
        label = f"{node.get_text(' ', strip=True)} {node.get('aria-label', '')}"
        href = node.get("href", "")
        if href.lower().startswith("mailto:"):
            address = unquote(href[7:].split("?", 1)[0]).strip()
            if valid_address(address) and len(public_emails) < 5:
                public_emails.add(address)
            continue
        if not href or not action.search(label):
            continue
        try:
            target = urlsplit(urljoin(url, href))
            if (target.scheme == "https" and target.netloc == source.netloc and target.path not in {"", "/"}
                    and not target.query and not target.fragment):
                next_url = next_url or target.geturl()
                if re.search(r"\b(contact|enquire|inquire)\b", label + " " + target.path, re.I):
                    contact_page = contact_page or target.geturl()
        except ValueError:
            continue
    ranked = sorted(flags, key=lambda item: item["points"], reverse=True)
    return {
        "url": url, "title": title[:180], "headings": headings, "findings": ranked, "score": min(100, sum(item["points"] for item in ranked)),
        "elapsed_ms": elapsed, "bytes": len(html.encode()), "observed_at": time.time(), "image_count": len(images),
        "next_url": next_url, "unlabeled_fields": len(without_label),
        "public_emails": sorted(public_emails), "contact_page": contact_page,
        "scope": "Public HTML review of one page. Dynamic content and business demand were not assessed.",
    }


EMAIL_TEXT = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}")
PHONE_TEXT = re.compile(r"(?<![\w+])(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)\d{3,5}[\s-]?\d{3,5}(?!\w)")
SOCIAL = ("instagram.com", "facebook.com", "linkedin.com", "x.com", "twitter.com", "youtube.com")


def normalize_url(value):
    value = value.strip().strip("<>\"'").rstrip(".,;)")
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    parts = urlsplit(value)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", "", ""))


def parse_search(html, limit):
    soup = BeautifulSoup(html, "html.parser")
    results, seen = [], set()
    for node in soup.select(".result"):
        anchor = node.select_one("a.result__a")
        if not anchor or not anchor.get("href"):
            continue
        href = anchor["href"]
        if "duckduckgo.com/l/" in href:
            href = parse_qs(urlsplit(href if href.startswith("http") else "https:" + href).query).get("uddg", [""])[0]
        if not href.startswith(("http://", "https://")) or "duckduckgo.com/y.js" in href or href in seen:
            continue
        seen.add(href)
        snippet = node.select_one(".result__snippet")
        results.append({"title": anchor.get_text(" ", strip=True)[:160], "url": href[:500],
                        "snippet": snippet.get_text(" ", strip=True)[:320] if snippet else ""})
        if len(results) >= limit:
            break
    return results


def page_contacts(url, soup, text):
    emails, phones, whatsapp, social = [], [], [], []
    contact_page = None
    source = urlsplit(url)
    for node in soup.find_all("a", href=True, limit=600):
        href = node["href"].strip()
        lower = href.lower()
        if lower.startswith("mailto:"):
            address = unquote(href[7:].split("?", 1)[0]).strip().lower()
            if valid_address(address):
                emails.append(address)
        elif lower.startswith("tel:"):
            number = re.sub(r"[^\d+]", "", href[4:])
            if 7 <= len(number.lstrip("+")) <= 15:
                phones.append(number)
        elif "wa.me/" in lower or "api.whatsapp.com" in lower or "whatsapp://" in lower:
            digits = re.search(r"(?:wa\.me/|phone=)(\+?\d{7,15})", href)
            whatsapp.append(digits.group(1).lstrip("+") if digits else href[:200])
        else:
            try:
                target = urlsplit(urljoin(url, href))
            except ValueError:
                continue
            host = (target.hostname or "").removeprefix("www.")
            if any(host == item or host.endswith("." + item) for item in SOCIAL) and target.path not in {"", "/"}:
                social.append(target._replace(query="", fragment="").geturl()[:200])
            elif (contact_page is None and target.netloc == source.netloc and target.scheme in {"http", "https"}
                  and target.path.rstrip("/") != source.path.rstrip("/")
                  and re.search(r"contact|enquir|inquir|get-in-touch|reach", target.path + " " + node.get_text(" ", strip=True), re.I)):
                contact_page = target._replace(query="", fragment="").geturl()
    for match in EMAIL_TEXT.findall(text):
        address = match.lower().strip(".")
        if valid_address(address) and not re.search(r"\.(png|jpe?g|gif|webp|svg)$", address) and "example." not in address:
            emails.append(address)
    if not phones:
        for match in PHONE_TEXT.findall(text):
            digits = re.sub(r"[^\d+]", "", match)
            if 10 <= len(digits.lstrip("+")) <= 13 and not re.fullmatch(r"(19|20)\d{8}", digits):
                phones.append(digits)
    unique = lambda items: list(dict.fromkeys(items))[:6]
    return {"emails": unique(emails), "phones": unique(phones), "whatsapp": unique(whatsapp),
            "social": unique(social), "contact_page": contact_page}


def readable(url, html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True)[:200] if soup.title else ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    description = (meta.get("content") or "").strip()[:400] if meta else ""
    full_text = soup.get_text(" ", strip=True)
    contacts = page_contacts(url, soup, full_text)
    for node in soup(["script", "style", "noscript", "svg", "iframe", "template"]):
        node.decompose()
    headings = [node.get_text(" ", strip=True)[:120] for node in soup.find_all(["h1", "h2", "h3"], limit=30)]
    region = soup.find("main") or soup.find("article") or soup.body or soup
    blocks = []
    for node in region.find_all(["h1", "h2", "h3", "p", "li", "td", "address"], limit=400):
        line = " ".join(node.get_text(" ", strip=True).split())
        if len(line) >= 25 and line not in blocks:
            blocks.append(line)
    if sum(map(len, blocks)) < 600:
        for line in (soup.body or soup).get_text("\n", strip=True).splitlines():
            line = " ".join(line.split())
            if len(line) >= 25 and line not in blocks:
                blocks.append(line)
            if len(blocks) > 200:
                break
    text = unescape("\n".join(blocks))[:6000]
    links = []
    origin = urlsplit(url).netloc
    for node in soup.find_all("a", href=True, limit=300):
        label = node.get_text(" ", strip=True)[:60]
        try:
            target = urlsplit(urljoin(url, node["href"]))
        except ValueError:
            continue
        if label and target.netloc == origin and target.path not in {"", "/"} and len(links) < 25:
            entry = {"label": label, "url": target._replace(query="", fragment="").geturl()}
            if entry not in links:
                links.append(entry)
    return {"url": url, "title": title, "description": description, "headings": [item for item in headings if item][:20],
            "text": text, "links": links, "contacts": contacts, "observed_at": time.time()}


def image_candidates(url, html):
    soup = BeautifulSoup(html, "html.parser")
    found = []

    def add(value, weight):
        if not value or value.startswith("data:"):
            return
        absolute = urljoin(url, value.strip().split(" ")[0])
        if absolute.startswith("https://") and not re.search(r"(?i)(logo|icon|favicon|sprite|avatar|badge|pixel|\.svg)", absolute):
            found.append((weight, absolute))

    for meta in soup.find_all("meta", attrs={"property": re.compile(r"^og:image", re.I)}) + \
            soup.find_all("meta", attrs={"name": re.compile(r"^twitter:image", re.I)}):
        add(meta.get("content"), 3)
    for index, img in enumerate(soup.find_all("img", limit=80)):
        sources = [img.get("data-src"), img.get("data-lazy-src"), img.get("src")]
        srcset = img.get("srcset") or img.get("data-srcset")
        if srcset:
            sources.insert(0, srcset.split(",")[-1].strip().split(" ")[0])
        width = int(re.sub(r"\D", "", str(img.get("width") or "0")) or 0)
        weight = 2 if width >= 600 or not width else 0
        weight += 1 if index < 12 else 0
        for source in sources:
            if source:
                add(source, weight)
                break
    for style in soup.select("[style*='background']", limit=30):
        match = re.search(r"url\(['\"]?([^'\")]+)", style.get("style", ""))
        if match:
            add(match.group(1), 2)
    ordered = []
    for _, item in sorted(found, key=lambda pair: -pair[0]):
        if item not in ordered:
            ordered.append(item)
    return ordered


def prepare_photo(data):
    """Keep real photographs only; normalise to an optimised JPEG of at most 1600 px width."""
    from io import BytesIO

    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            width, height = image.size
            if width < 480 or height < 320 or not 0.45 <= width / height <= 2.6:
                return None
            colours = image.convert("RGB").resize((24, 24)).getcolors(24 * 24) or []
            if len(colours) < 60:  # flat graphics, logos and illustrations rather than photos
                return None
            image = image.convert("RGB")
            image.thumbnail((1600, 1600))
            output = BytesIO()
            image.save(output, format="JPEG", quality=80, optimize=True, progressive=True)
            return output.getvalue(), image.width, image.height
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None
