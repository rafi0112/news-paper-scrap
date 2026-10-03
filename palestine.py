"""
Palestine coverage aggregator.

Pulls free, public RSS / Atom feeds (news outlets + YouTube channels),
keeps only Palestine-related items and normalises them into one list.

Nothing is written to Supabase on purpose: facebook_poster.py posts
every row of the `news` table, so this feed is served live instead.

Run directly to print every collected content link:

    python palestine.py
"""

import re
import time
from collections import Counter
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape

import requests
from bs4 import BeautifulSoup


# ==========================================
# CONFIG
# ==========================================

CACHE_SECONDS = 600
FEED_TIMEOUT = 5
IMAGE_TIMEOUT = 3
MAX_IMAGE_LOOKUPS = 30
# Matches the Supabase cleanup job, which deletes news older than 1 day.
WINDOW_HOURS = 24
# Videos may reach further back so the Shorts feed is never empty.
VIDEO_LOOKBACK_HOURS = 72
MIN_VIDEOS = 12
MAX_ITEMS_PER_FEED = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}


# ==========================================
# SOURCES
# ==========================================
# focused=True  -> outlet covers Palestine almost exclusively,
#                  every item is kept.
# focused=False -> general outlet, items are keyword-filtered.

YOUTUBE = "https://www.youtube.com/feeds/videos.xml?channel_id="

FEEDS = [
    # ---------- Palestine-focused outlets ----------
    {"name": "Electronic Intifada", "site": "https://electronicintifada.net", "url": "https://electronicintifada.net/rss.xml", "kind": "article", "lang": "en", "focused": True},
    {"name": "Mondoweiss", "site": "https://mondoweiss.net", "url": "https://mondoweiss.net/feed/", "kind": "article", "lang": "en", "focused": True},
    {"name": "+972 Magazine", "site": "https://www.972mag.com", "url": "https://www.972mag.com/feed/", "kind": "article", "lang": "en", "focused": True},
    {"name": "Palestinian Information Center", "site": "https://english.palinfo.com", "url": "https://english.palinfo.com/feed/", "kind": "article", "lang": "en", "focused": True},
    {"name": "The Guardian", "site": "https://www.theguardian.com/world/palestinian-territories", "url": "https://www.theguardian.com/world/palestinian-territories/rss", "kind": "article", "lang": "en", "focused": True},

    # ---------- International outlets (filtered) ----------
    {"name": "Al Jazeera", "site": "https://www.aljazeera.com", "url": "https://www.aljazeera.com/xml/rss/all.xml", "kind": "article", "lang": "en", "focused": False},
    {"name": "Middle East Eye", "site": "https://www.middleeasteye.net", "url": "https://www.middleeasteye.net/rss", "kind": "article", "lang": "en", "focused": False},
    {"name": "Middle East Monitor", "site": "https://www.middleeastmonitor.com", "url": "https://www.middleeastmonitor.com/feed/", "kind": "article", "lang": "en", "focused": False},
    {"name": "UN News", "site": "https://news.un.org/en/news/region/middle-east", "url": "https://news.un.org/feed/subscribe/en/news/region/middle-east/feed/rss.xml", "kind": "article", "lang": "en", "focused": False},
    {"name": "BBC News", "site": "https://www.bbc.com/news/world/middle_east", "url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "kind": "article", "lang": "en", "focused": False},
    {"name": "Anadolu Agency", "site": "https://www.aa.com.tr/en/middle-east", "url": "https://www.aa.com.tr/en/rss/default?cat=middle-east", "kind": "article", "lang": "en", "focused": False},
    {"name": "Democracy Now!", "site": "https://www.democracynow.org", "url": "https://www.democracynow.org/democracynow.rss", "kind": "article", "lang": "en", "focused": False},

    # ---------- Bangla outlets (filtered) ----------
    {"name": "Prothom Alo", "site": "https://www.prothomalo.com/world", "url": "https://www.prothomalo.com/feed/", "kind": "article", "lang": "bn", "focused": False},
    {"name": "BBC Bangla", "site": "https://www.bbc.com/bengali", "url": "https://feeds.bbci.co.uk/bengali/rss.xml", "kind": "article", "lang": "bn", "focused": False},
    {"name": "DW Bangla", "site": "https://www.dw.com/bn", "url": "https://rss.dw.com/rdf/rss-ben-all", "kind": "article", "lang": "bn", "focused": False},

    # ---------- YouTube channels (filtered) ----------
    {"name": "Al Jazeera English", "site": "https://www.youtube.com/@aljazeeraenglish", "url": YOUTUBE + "UCNye-wNBqNL5ZzHSJj3l8Bg", "kind": "video", "lang": "en", "focused": False},
    {"name": "Middle East Eye", "site": "https://www.youtube.com/@middleeasteye", "url": YOUTUBE + "UCR0fZh5SBxxMNYdg0VzRFkg", "kind": "video", "lang": "en", "focused": False},
    {"name": "AJ+", "site": "https://www.youtube.com/@ajplus", "url": YOUTUBE + "UCV3Nm3T-XAgVhKH9jT0ViRg", "kind": "video", "lang": "en", "focused": False},
    {"name": "TRT World", "site": "https://www.youtube.com/@trtworld", "url": YOUTUBE + "UC7fWeaHhqgM4Ry-RMpM2YYw", "kind": "video", "lang": "en", "focused": False},
    {"name": "Democracy Now!", "site": "https://www.youtube.com/@democracynow", "url": YOUTUBE + "UCzuqE7-t13O4NIDYJfakrhw", "kind": "video", "lang": "en", "focused": False},
    {"name": "Drop Site News", "site": "https://www.youtube.com/@DropSiteNews", "url": YOUTUBE + "UCBMrOkjg3AbvLS5g1MhtlRQ", "kind": "video", "lang": "en", "focused": False},
    {"name": "Channel 4 News", "site": "https://www.youtube.com/@channel4news", "url": YOUTUBE + "UCTrQ7HXWRRxr7OsOtodr2_w", "kind": "video", "lang": "en", "focused": False},
    {"name": "Electronic Intifada", "site": "https://www.youtube.com/@TheElectronicIntifada", "url": YOUTUBE + "UC9jY5IcAA99wX8MZQ9K9r-Q", "kind": "video", "lang": "en", "focused": True},
    {"name": "+972 Magazine", "site": "https://www.youtube.com/@972mag", "url": YOUTUBE + "UCdPB7J77CNSNWC6Qh3Ys1fg", "kind": "video", "lang": "en", "focused": False},

    # ---------- Bangla YouTube channels (filtered) ----------
    {"name": "Jamuna TV", "site": "https://www.youtube.com/@jamunatvbd", "url": YOUTUBE + "UCN6sm8iHiPd0cnoUardDAnw", "kind": "video", "lang": "bn", "focused": False},
    {"name": "Channel 24", "site": "https://www.youtube.com/@channel24digital", "url": YOUTUBE + "UCHLqIOMPk20w-6cFgkA90jw", "kind": "video", "lang": "bn", "focused": False},
    {"name": "DBC News", "site": "https://www.youtube.com/@dbcnewstv", "url": YOUTUBE + "UCUvXoiDEKI8VZJrr58g4VAw", "kind": "video", "lang": "bn", "focused": False},
]


# Palestine-specific terms only: a bare "Israel" match pulls in
# unrelated stories (flights, Iran, Lebanon) from general outlets.
KEYWORDS = re.compile(
    r"palestin|gaza|west bank|jerusalem|al-aqsa|al aqsa|rafah|khan younis|"
    r"jenin|nablus|hebron|ramallah|tulkarem|unrwa|\bhamas\b|nakba|"
    r"occupied territor|"
    r"ফিলিস্তিন|গাজা|পশ্চিম তীর|জেরুজালেম|আল-আকসা|হামাস|রাফা",
    re.I,
)


NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "rss1": "http://purl.org/rss/1.0/",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


# ==========================================
# HELPERS
# ==========================================

def clean_text(value, limit=320):
    if not value:
        return ""

    text = BeautifulSoup(unescape(value), "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"

    return text


def parse_date(value):
    if not value:
        return None

    value = value.strip()

    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def first_image_in_html(html):
    if not html:
        return None

    match = re.search(r'<img[^>]+src=["\']([^"\']+)', unescape(html), re.I)

    return match.group(1) if match else None


def find_text(node, *paths):
    for path in paths:
        found = node.find(path, NS)

        if found is not None and (found.text or "").strip():
            return found.text.strip()

    return ""


# ==========================================
# PARSERS
# ==========================================

def parse_rss_item(item):
    """RSS 2.0 <item> and RSS 1.0 (RDF) <rss1:item>."""

    title = find_text(item, "title", "rss1:title")
    link = find_text(item, "link", "rss1:link")

    raw_description = find_text(item, "description", "rss1:description")
    raw_content = find_text(item, "content:encoded")

    published = find_text(item, "pubDate", "dc:date", "atom:updated")

    image = None

    for path in ("media:content", "media:thumbnail", "media:group/media:content", "enclosure"):
        for node in item.findall(path, NS):
            url = node.get("url")
            mime = node.get("type", "image")

            if url and (mime.startswith("image") or path.startswith("media:thumbnail") or node.get("medium") == "image"):
                image = url
                break

        if image:
            break

    if not image:
        image = first_image_in_html(raw_content) or first_image_in_html(raw_description)

    return {
        "title": clean_text(title, 300),
        "url": link,
        "description": clean_text(raw_description or raw_content),
        "image": image,
        "published_at": parse_date(published),
        "video_id": None,
    }


def parse_youtube_entry(entry):
    video_id = find_text(entry, "yt:videoId")

    link_node = entry.find("atom:link", NS)
    link = link_node.get("href") if link_node is not None else f"https://www.youtube.com/watch?v={video_id}"

    group = entry.find("media:group", NS)
    description = find_text(group, "media:description") if group is not None else ""

    return {
        "title": clean_text(find_text(entry, "atom:title"), 300),
        "url": link,
        "description": clean_text(description),
        "image": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None,
        "published_at": parse_date(find_text(entry, "atom:published", "atom:updated")),
        "video_id": video_id,
    }


def parse_atom_entry(entry):
    # Element truthiness depends on child count, so compare with None explicitly.
    link_node = entry.find("atom:link[@rel='alternate']", NS)

    if link_node is None:
        link_node = entry.find("atom:link", NS)

    raw_summary = find_text(entry, "atom:summary", "atom:content")

    return {
        "title": clean_text(find_text(entry, "atom:title"), 300),
        "url": link_node.get("href") if link_node is not None else "",
        "description": clean_text(raw_summary),
        "image": first_image_in_html(raw_summary),
        "published_at": parse_date(find_text(entry, "atom:published", "atom:updated")),
        "video_id": None,
    }


def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)

    if root.find("yt:channelId", NS) is not None or root.find("atom:entry/yt:videoId", NS) is not None:
        return [parse_youtube_entry(e) for e in root.findall("atom:entry", NS)]

    if root.tag == f"{{{NS['atom']}}}feed":
        return [parse_atom_entry(e) for e in root.findall("atom:entry", NS)]

    items = root.findall("channel/item") or root.findall("rss1:item", NS)

    return [parse_rss_item(i) for i in items]


# ==========================================
# FETCH ONE FEED
# ==========================================

def fetch_feed(feed):
    status = {
        "name": feed["name"],
        "site": feed["site"],
        "feed": feed["url"],
        "kind": feed["kind"],
        "lang": feed["lang"],
        "ok": False,
        "count": 0,
    }

    try:
        response = requests.get(feed["url"], headers=HEADERS, timeout=FEED_TIMEOUT)
        response.raise_for_status()

        entries = parse_feed(response.content)

    except Exception as e:
        status["error"] = str(e)[:160]
        return status, []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=VIDEO_LOOKBACK_HOURS)
    items = []

    for entry in entries[:MAX_ITEMS_PER_FEED * 2]:
        if not entry["title"] or not entry["url"]:
            continue

        if not feed["focused"] and not KEYWORDS.search(f"{entry['title']} {entry['description']}"):
            continue

        if entry["published_at"] and entry["published_at"] < cutoff:
            continue

        entry.update(source=feed["name"], kind=feed["kind"], lang=feed["lang"])
        items.append(entry)

        if len(items) >= MAX_ITEMS_PER_FEED:
            break

    status["ok"] = True
    status["count"] = len(items)

    return status, items


# ==========================================
# IMAGE FALLBACK (og:image)
# ==========================================

def find_og_image(url):
    try:
        with requests.get(url, headers=HEADERS, timeout=IMAGE_TIMEOUT, stream=True) as response:
            response.raise_for_status()
            head = response.raw.read(200_000, decode_content=True).decode("utf-8", "ignore")
    except Exception:
        return None

    match = re.search(
        r"<meta[^>]+(?:property|name)=[\"'](?:og:image|twitter:image)[\"'][^>]+content=[\"']([^\"']+)"
        r"|<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:property|name)=[\"'](?:og:image|twitter:image)",
        head,
        re.I,
    )

    return unescape(match.group(1) or match.group(2)) if match else None


def fill_missing_images(articles):
    missing = [a for a in articles if not a["image"]][:MAX_IMAGE_LOOKUPS]

    if not missing:
        return

    with ThreadPoolExecutor(max_workers=len(missing)) as pool:
        for article, image in zip(missing, pool.map(lambda a: find_og_image(a["url"]), missing)):
            article["image"] = image


# ==========================================
# AGGREGATE (cached)
# ==========================================

_cache = {"at": 0.0, "data": None}


def collect():
    with ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
        results = list(pool.map(fetch_feed, FEEDS))

    seen = set()
    articles, videos, sources = [], [], []

    for status, items in results:
        sources.append(status)

        for item in items:
            key = item["url"].split("?")[0].rstrip("/") if item["kind"] == "article" else item["video_id"]

            if key in seen:
                continue

            seen.add(key)
            (videos if item["kind"] == "video" else articles).append(item)

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    window = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)

    def in_window(item):
        return item["published_at"] is None or item["published_at"] >= window

    for bucket in (articles, videos):
        bucket.sort(key=lambda x: x["published_at"] or epoch, reverse=True)

    articles = [a for a in articles if in_window(a)]

    recent_videos = [v for v in videos if in_window(v)]
    videos = recent_videos if len(recent_videos) >= MIN_VIDEOS else videos[:max(MIN_VIDEOS, len(recent_videos))]

    fill_missing_images(articles)

    counts = Counter((item["source"], item["kind"]) for item in articles + videos)

    for status in sources:
        if status["ok"]:
            status["count"] = counts.get((status["name"], status["kind"]), 0)

    for bucket in (articles, videos):
        for item in bucket:
            item["published_at"] = item["published_at"].isoformat() if item["published_at"] else None

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": WINDOW_HOURS,
        "sources": sources,
        "articles": articles,
        "videos": videos,
    }


def get_palestine_feed(force=False):
    if force or not _cache["data"] or time.time() - _cache["at"] > CACHE_SECONDS:
        _cache["data"] = collect()
        _cache["at"] = time.time()

    return _cache["data"]


# ==========================================
# MAIN: list every content link
# ==========================================

if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    data = get_palestine_feed(force=True)

    print("=" * 70)
    print("SOURCES")
    print("=" * 70)

    for s in data["sources"]:
        mark = "OK " if s["ok"] else "ERR"
        print(f"[{mark}] {s['kind']:<7} {s['lang']}  {s['count']:>3}  {s['name']:<32} {s['feed']}")

    for label, bucket in (("ARTICLES", data["articles"]), ("VIDEOS", data["videos"])):
        print()
        print("=" * 70)
        print(f"{label} ({len(bucket)})")
        print("=" * 70)

        for item in bucket:
            date = (item["published_at"] or "")[:16].replace("T", " ")
            print(f"{date}  [{item['source']}] {item['title']}")
            print(f"    {item['url']}")
