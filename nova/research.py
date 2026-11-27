import asyncio
import ipaddress
import re
import socket
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .domain import Candidate, NovaError

USER_AGENT = "NOVA-Research/0.1"
MAX_PAGE = 1_500_000


class PublicResearch:
    def __init__(self, store):
        self.store = store
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(14, connect=6), trust_env=False,
                                        follow_redirects=False, limits=httpx.Limits(max_connections=3))
        self.lock = asyncio.Lock()
        self.next_request = 0.0

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
                    return status, response.headers, data.decode(response.encoding or "utf-8", errors="replace"), elapsed
            except httpx.HTTPError as exc:
                raise NovaError("web_network", "Could not fetch the public page.", transient=True) from exc

    async def robots(self, url):
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
        return rules.can_fetch(USER_AGENT, url) and not (rules.crawl_delay(USER_AGENT) or rules.request_rate(USER_AGENT))

    async def audit(self, candidate):
        key = f"public-audit:v2:{candidate.url}"
        origin = {"name": candidate.name, "source_directory": candidate.listed_by}
        cached = self.store.cached(key)
        if cached is not None:
            self.store.log("cache", "Reused a public website audit")
            return {**cached, **origin, "cache_hit": True}
        target, html, elapsed = await self.html(candidate.url)
        result = await asyncio.to_thread(inspect, target, html, elapsed)
        self.store.cache(key, result, 1800)
        return {**result, **origin, "cache_hit": False}

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

    async def html(self, target):
        for _ in range(5):
            if not await self.robots(target):
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
    for node in controls:
        label = f"{node.get_text(' ', strip=True)} {node.get('aria-label', '')}"
        href = node.get("href", "")
        if not href or not action.search(label):
            continue
        try:
            target = urlsplit(urljoin(url, href))
            if (target.scheme == "https" and target.netloc == source.netloc and target.path not in {"", "/"}
                    and not target.query and not target.fragment):
                next_url = target.geturl()
                break
        except ValueError:
            continue
    ranked = sorted(flags, key=lambda item: item["points"], reverse=True)
    return {
        "url": url, "title": title[:180], "headings": headings, "findings": ranked, "score": min(100, sum(item["points"] for item in ranked)),
        "elapsed_ms": elapsed, "bytes": len(html.encode()), "observed_at": time.time(), "image_count": len(images),
        "next_url": next_url, "unlabeled_fields": len(without_label),
        "scope": "Public HTML review of one page. Dynamic content and business demand were not assessed.",
    }
