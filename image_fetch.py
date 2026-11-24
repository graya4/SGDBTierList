"""Shared, resilient image fetching for the /proxy route and the PNG renderer.

- pooled HTTP session with retries/backoff on connection errors, 429 and 5xx
- bounded in-memory LRU cache (by bytes) so repeat loads never hit upstream
- concurrent requests for the same URL are coalesced into one download
- old-style Steam CDN URLs that now 404 are re-resolved via the Steam store API
  (newer games keep their art under a content hash)
"""
import json
import mimetypes
import re
import threading
from collections import OrderedDict
from urllib.parse import urlparse, parse_qs

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "Mozilla/5.0 (compatible; TierListMaker/1.0)"
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 20
MAX_IMAGE_BYTES = 20 * 1024 * 1024
CACHE_MAX_BYTES = 256 * 1024 * 1024

STEAM_KEY = None  # set by app.py; GetItems also works without a key
STEAM_ASSET_BASE = "https://shared.akamai.steamstatic.com/store_item_assets/"
STEAM_TYPE_GAME = 0  # EStoreAppType: 0 = game, 1 = demo, 4 = DLC, ...


def make_session(retries=3, pool=32):
    session = requests.Session()
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),  # our POSTs are read-only searches
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pool, pool_maxsize=pool)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = USER_AGENT
    return session


session = make_session()


class FetchError(Exception):
    def __init__(self, status, message=""):
        super().__init__(message or f"upstream returned {status}")
        self.status = status


# --- Steam -------------------------------------------------------------------

def get_steam_items(appids):
    """Fetch store items (with assets) for many appids in one request."""
    payload = {
        "ids": [{"appid": int(a)} for a in appids],
        "context": {"language": "english", "country_code": "US"},
        "data_request": {"include_assets": True},
    }
    params = {"input_json": json.dumps(payload)}
    if STEAM_KEY:
        params["key"] = STEAM_KEY
    r = session.get("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/",
                    params=params, timeout=(CONNECT_TIMEOUT, 10))
    r.raise_for_status()
    return r.json().get("response", {}).get("store_items", [])


def steam_asset_url(item, *asset_keys):
    """Build a full image URL from a store item's assets.

    Newer games store art under a content hash (e.g. "<sha1>/library_600x900_2x.jpg"),
    and some use different filenames entirely, so the path must come from the API
    rather than being guessed. Returns the first key that exists, or None.
    """
    assets = item.get("assets") or {}
    fmt = assets.get("asset_url_format")
    if not fmt:
        return None
    for key in asset_keys:
        filename = assets.get(key)
        if filename:
            return STEAM_ASSET_BASE + fmt.replace("${FILENAME}", filename)
    return None


_STEAM_URL = re.compile(
    r"^https?://[^/]*(?:steamstatic\.com|steamcdn[^/]*|akamaihd\.net|steampowered\.com)/"
    r".*?steam/apps/(\d+)/(?:[0-9a-f]{40}/)?([a-z0-9_]+)\.(?:jpg|png)",
    re.IGNORECASE,
)
_STEAM_ASSET_KEYS = {
    "library_600x900_2x": ("library_capsule_2x", "library_capsule"),
    "library_600x900": ("library_capsule", "library_capsule_2x"),
    "library_capsule_2x": ("library_capsule_2x", "library_capsule"),
    "library_capsule": ("library_capsule", "library_capsule_2x"),
    "header": ("header", "header_2x"),
    "header_2x": ("header_2x", "header"),
    "library_hero": ("library_hero", "library_hero_2x"),
}


def steam_fallback_url(url):
    """Map a stale Steam CDN URL to the game's current (possibly hashed) asset URL."""
    m = _STEAM_URL.match(url)
    if not m:
        return None
    appid, name = m.group(1), m.group(2).lower()
    keys = _STEAM_ASSET_KEYS.get(name)
    if not keys:
        return None
    try:
        items = get_steam_items([appid])
    except requests.RequestException:
        return None
    for item in items:
        if item.get("success") == 1:
            return steam_asset_url(item, *keys)
    return None


# --- cache -------------------------------------------------------------------

class _BytesLRU:
    def __init__(self, max_bytes):
        self.max_bytes = max_bytes
        self.size = 0
        self.data = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            value = self.data.get(key)
            if value is not None:
                self.data.move_to_end(key)
            return value

    def put(self, key, value):
        n = len(value[0])
        if n > self.max_bytes:
            return
        with self.lock:
            old = self.data.pop(key, None)
            if old is not None:
                self.size -= len(old[0])
            self.data[key] = value
            self.size += n
            while self.size > self.max_bytes:
                _, evicted = self.data.popitem(last=False)
                self.size -= len(evicted[0])


_cache = _BytesLRU(CACHE_MAX_BYTES)
_inflight = {}
_inflight_lock = threading.Lock()


def unwrap_proxy(url):
    """'https://any-host/proxy?url=X' -> X (repeatedly, for nested wraps)."""
    for _ in range(3):
        try:
            parsed = urlparse(url)
        except ValueError:
            break
        if not parsed.path.rstrip("/").endswith("/proxy"):
            break
        inner = parse_qs(parsed.query).get("url")
        if not inner:
            break
        url = inner[0]
    return url


def _download(url):
    def get(u):
        return session.get(u, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))

    r = get(url)
    if r.status_code in (403, 404):
        alt = steam_fallback_url(url)
        if alt and alt != url:
            r = get(alt)
    if r.status_code != 200:
        raise FetchError(r.status_code)
    if len(r.content) > MAX_IMAGE_BYTES:
        raise FetchError(413, "image too large")

    ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if not ctype.startswith("image/"):
        guessed = mimetypes.guess_type(urlparse(url).path)[0]
        if guessed and guessed.startswith("image/"):
            ctype = guessed
        else:
            raise FetchError(415, f"not an image ({ctype or 'unknown type'})")
    return r.content, ctype


def fetch_image(url):
    """Return (bytes, content_type) for an image URL, using the shared cache.
    Raises FetchError or requests.RequestException on failure."""
    url = unwrap_proxy(url)
    if urlparse(url).scheme not in ("http", "https"):
        raise FetchError(400, "only http(s) URLs are allowed")

    cached = _cache.get(url)
    if cached is not None:
        return cached

    # Coalesce concurrent requests for the same URL into one download
    with _inflight_lock:
        lock = _inflight.setdefault(url, threading.Lock())
    with lock:
        cached = _cache.get(url)
        if cached is not None:
            return cached
        try:
            result = _download(url)
            _cache.put(url, result)
            return result
        finally:
            with _inflight_lock:
                _inflight.pop(url, None)
