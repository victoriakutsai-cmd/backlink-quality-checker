"""Stage 3: page-level checks for links that survived screening."""
import re
import threading
import time
from html.parser import HTMLParser
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests

from .screening import hostname, registrable

LOGIN_RE = re.compile(r"(log-?in|sign-?in|register|signup|account/)", re.I)
EN_STOP = {"the", "and", "of", "to", "in", "a", "is", "for", "on", "with", "that", "it", "this", "how", "what", "you", "are"}


class PageParser(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.anchors, self.robots_meta, self.title, self.h1 = base, [], "", "", ""
        self._a, self._in_title, self._in_h1, self.text = None, False, False, []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self._a = {"href": urljoin(self.base, d["href"]), "rel": (d.get("rel") or "").lower(), "text": ""}
            self.anchors.append(self._a)
        elif tag == "meta" and (d.get("name") or "").lower() == "robots":
            self.robots_meta = (d.get("content") or "").lower()
        elif tag == "title":
            self._in_title = True
        elif tag == "h1" and not self.h1:
            self._in_h1 = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._a = None
        elif tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False

    def handle_data(self, data):
        self.text.append(data)
        if self._a is not None:
            self._a["text"] += data
        if self._in_title:
            self.title += data
        if self._in_h1:
            self.h1 += data


def looks_non_english(text: str) -> bool:
    """Cheap heuristic: mostly non-Latin letters, or a long Latin text with no common English words.
    Good enough to queue pages for a human; not a language detector."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    if sum(1 for c in letters if not c.isascii()) / len(letters) > 0.3:
        return True
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return len(words) >= 5 and not (set(words) & EN_STOP)


def norm(url: str) -> str:
    p = urlparse(url.strip())
    return f"{p.netloc.lower().removeprefix('www.')}{p.path.rstrip('/')}" + (f"?{p.query}" if p.query else "")


class Throttle:
    def __init__(self, delay):
        self.delay, self.last, self.lock = delay, {}, threading.Lock()

    def wait(self, host):
        with self.lock:
            now = time.monotonic()
            ready = max(now, self.last.get(host, 0) + self.delay)
            self.last[host] = ready
        time.sleep(max(0, ready - now))


class Robots:
    def __init__(self, ua):
        self.ua, self.cache, self.lock = ua, {}, threading.Lock()

    def allowed(self, url):
        p = urlparse(url)
        key = f"{p.scheme}://{p.netloc}"
        with self.lock:
            if key not in self.cache:
                rp = robotparser.RobotFileParser(f"{key}/robots.txt")
                try:
                    rp.read()
                except Exception:
                    rp = None
                self.cache[key] = rp
        rp = self.cache[key]
        return True if rp is None else rp.can_fetch(self.ua, url)


def fetch(session, url, timeout, throttle, max_hops=5):
    """Follow redirects manually so every hop's status code is visible."""
    chain, cur = [], url
    for _ in range(max_hops + 1):
        throttle.wait(urlparse(cur).netloc)
        r = session.get(cur, timeout=timeout, allow_redirects=False)
        chain.append(r.status_code)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            cur = urljoin(cur, r.headers["Location"])
            continue
        return r, chain, cur
    return r, chain, cur


def check_page(row, cfg, session, throttle, robots):
    """Returns (flags, details) for one link row. `row` needs link_url; optional target_url."""
    url = row["link_url"].strip()
    flags, d = [], {"http_status": "", "redirect_chain": "", "title": "", "h1": "", "target_links": 0, "anchor": "", "rel": ""}
    ccfg = cfg["crawl"]
    try:
        if ccfg["respect_robots"] and not robots.allowed(url):
            return ["skipped_robots"], d
        r, chain, final = fetch(session, url, ccfg["timeout"], throttle)
        d["http_status"], d["redirect_chain"] = r.status_code, ">".join(map(str, chain))
        if r.status_code in (403, 429, 503):
            return ["blocked_needs_manual"], d
        if r.status_code >= 400:
            return ["http_error"], d
        if any(c in (302, 303, 307) for c in chain[:-1]) and LOGIN_RE.search(final):
            return ["login_wall"], d
        if "noindex" in r.headers.get("X-Robots-Tag", "").lower():
            flags.append("noindex")
        if "html" not in r.headers.get("Content-Type", ""):
            return flags, d
        p = PageParser(final)
        p.feed(r.text)
        if "noindex" in p.robots_meta and "noindex" not in flags:
            flags.append("noindex")
        d["title"], d["h1"] = " ".join(p.title.split()), " ".join(p.h1.split())
        if looks_non_english(f"{d['title']} {d['h1']}"):
            flags.append("non_english_text")

        target_dom = registrable(cfg["target_domain"])
        mine = [a for a in p.anchors if registrable(hostname(a["href"])) == target_dom]
        d["target_links"] = len(mine)
        want = (row.get("target_url") or "").strip() if isinstance(row.get("target_url"), str) else ""
        if not mine:
            plain = cfg["target_domain"].lower() in "".join(p.text).lower()
            flags.append("link_not_clickable" if plain else "link_missing")
        else:
            hit = next((a for a in mine if want and norm(a["href"]) == norm(want)), mine[0])
            d["anchor"], d["rel"] = " ".join(hit["text"].split()), hit["rel"]
            if want and not any(norm(a["href"]) == norm(want) for a in mine):
                flags.append("wrong_target_url")
            if len(mine) > 1:
                flags.append("extra_target_links")
    except requests.RequestException as e:
        flags.append("http_error")
        d["http_status"] = type(e).__name__
    return flags, d
