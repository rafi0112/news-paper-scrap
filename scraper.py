import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json
import re

from database import init_db, save_news


# ==========================================
# CONFIG
# ==========================================

MAX_LINKS_PER_SITE = 80
NEWS_MAX_AGE_DAYS = 2

BANGLADESH_TZ = ZoneInfo("Asia/Dhaka")


# ==========================================
# NEWS SITES
# ==========================================

SITES = [
    {
        "name": "BDNews24",
        "url": "https://bangla.bdnews24.com/",
        "listing_url": "https://bangla.bdnews24.com/"
    },

    {
        "name": "The Daily Star",
        "url": "https://www.thedailystar.net/",
        "listing_url": "https://www.thedailystar.net/"
    },

    {
        "name": "Prothom Alo",
        "url": "https://www.prothomalo.com/",
        "listing_url": "https://www.prothomalo.com/"
    },

    {
        "name": "The Business Standard",
        "url": "https://www.tbsnews.net/",
        "listing_url": "https://www.tbsnews.net/latest"
    }
]


# ==========================================
# HEADERS
# ==========================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,bn;q=0.8"
}


# ==========================================
# GET PAGE
# ==========================================

def get_page(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        return response.text

    except requests.RequestException as e:

        print()
        print("Request failed:")
        print(url)
        print(e)

        return None


# ==========================================
# PARSE DATE
# ==========================================

def parse_date(value):

    if not value:
        return None

    value = str(value).strip()

    if not value:
        return None

    # --------------------------------------
    # ISO 8601
    # --------------------------------------

    try:

        value_clean = value.replace(
            "Z",
            "+00:00"
        )

        dt = datetime.fromisoformat(
            value_clean
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=BANGLADESH_TZ
            )

        return dt.isoformat()

    except ValueError:
        pass


    # --------------------------------------
    # Common formats
    # --------------------------------------

    formats = [

        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",

        "%Y-%m-%d",

        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",

        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",

        "%d %B %Y %H:%M:%S",
        "%d %B %Y %H:%M",
        "%d %B %Y",

        "%d %b %Y %H:%M:%S",
        "%d %b %Y %H:%M",
        "%d %b %Y",

        "%B %d, %Y %H:%M:%S",
        "%B %d, %Y %H:%M",
        "%B %d, %Y",

        "%b %d, %Y %H:%M:%S",
        "%b %d, %Y %H:%M",
        "%b %d, %Y",
    ]


    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt
            )

            dt = dt.replace(
                tzinfo=BANGLADESH_TZ
            )

            return dt.isoformat()

        except ValueError:

            continue


    return None


# ==========================================
# EXTRACT PUBLISHED DATE
# ==========================================

def extract_published_date(soup):

    # --------------------------------------
    # META TAGS
    # --------------------------------------

    meta_tags = [

        ("property", "article:published_time"),
        ("property", "article:published"),
        ("property", "og:published_time"),

        ("name", "date"),
        ("name", "publish-date"),
        ("name", "published"),
        ("name", "published_time"),
        ("name", "datePublished"),
        ("name", "timestamp"),

        ("itemprop", "datePublished"),
    ]


    for attr, value in meta_tags:

        tag = soup.find(
            "meta",
            attrs={
                attr: value
            }
        )

        if tag:

            date_value = (
                tag.get("content")
                or tag.get("datetime")
                or tag.get("value")
            )

            if date_value:

                parsed = parse_date(
                    date_value
                )

                if parsed:
                    return parsed


    # --------------------------------------
    # TIME TAGS
    # --------------------------------------

    for tag in soup.find_all("time"):

        date_value = (
            tag.get("datetime")
            or tag.get("content")
            or tag.get_text(
                " ",
                strip=True
            )
        )

        if date_value:

            parsed = parse_date(
                date_value
            )

            if parsed:
                return parsed


    # --------------------------------------
    # JSON-LD
    # --------------------------------------

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )


    for script in scripts:

        try:

            raw = (
                script.string
                or script.get_text()
            )

            data = json.loads(raw)

        except Exception:

            continue


        objects = []


        if isinstance(data, dict):

            objects.append(data)

            graph = data.get("@graph")

            if isinstance(graph, list):

                objects.extend(graph)


        elif isinstance(data, list):

            objects.extend(data)


        for obj in objects:

            if not isinstance(obj, dict):
                continue


            date_value = (
                obj.get("datePublished")
                or obj.get("dateCreated")
                or obj.get("dateModified")
            )


            if date_value:

                parsed = parse_date(
                    date_value
                )

                if parsed:
                    return parsed


    # --------------------------------------
    # COMMON HTML SELECTORS
    # --------------------------------------

    selectors = [

        ".published-date",
        ".publish-date",
        ".published",
        ".article-date",
        ".post-date",

        "[class*='published']",
        "[class*='publish-date']",
        "[class*='article-date']",
        "[class*='date']",
    ]


    for selector in selectors:

        try:

            tag = soup.select_one(
                selector
            )

        except Exception:

            continue


        if tag:

            date_value = (
                tag.get("datetime")
                or tag.get("content")
                or tag.get_text(
                    " ",
                    strip=True
                )
            )

            parsed = parse_date(
                date_value
            )

            if parsed:
                return parsed


    # --------------------------------------
    # RAW HTML FALLBACK
    # --------------------------------------

    html = str(soup)


    patterns = [

        r'"datePublished"\s*:\s*"([^"]+)"',

        r'"publishedAt"\s*:\s*"([^"]+)"',

        r'"publishDate"\s*:\s*"([^"]+)"',

        r'"published_time"\s*:\s*"([^"]+)"',

    ]


    for pattern in patterns:

        matches = re.findall(
            pattern,
            html,
            flags=re.I
        )

        for value in matches:

            parsed = parse_date(
                value
            )

            if parsed:
                return parsed


    return None


# ==========================================
# CHECK RECENT NEWS
# ==========================================

def is_recent_news(published_at):

    if not published_at:
        return False


    try:

        article_date = datetime.fromisoformat(
            published_at.replace(
                "Z",
                "+00:00"
            )
        )


        if article_date.tzinfo is None:

            article_date = article_date.replace(
                tzinfo=BANGLADESH_TZ
            )


        now = datetime.now(
            timezone.utc
        )


        article_date = article_date.astimezone(
            timezone.utc
        )


        cutoff = (
            now
            - timedelta(
                days=NEWS_MAX_AGE_DAYS
            )
        )


        return article_date >= cutoff


    except Exception as e:

        print(
            "Date validation error:",
            published_at
        )

        print(e)

        return False


# ==========================================
# SOURCE-SPECIFIC ARTICLE URL CHECK
# ==========================================

def is_probable_article_url(
    url,
    source
):

    try:

        parsed = urlparse(url)

        path = parsed.path.rstrip("/").lower()

        if not path:
            return False


        # ======================================
        # BDNEWS24
        # ======================================

        if source == "BDNews24":

            blocked = [

                "/archive",
                "/search",
                "/category",
                "/tag/",
                "/author",
                "/video",
                "/photo",
                "/gallery",
                "/live",
                "/about",
                "/contact",

            ]


            if any(
                item in path
                for item in blocked
            ):
                return False


            parts = [
                x
                for x in path.split("/")
                if x
            ]


            # Need at least:
            # /section/article-id

            if len(parts) < 2:
                return False


            last_part = parts[-1]


            # BDNews24 article IDs are
            # generally hexadecimal strings.

            if not re.fullmatch(
                r"[a-f0-9]{8,}",
                last_part
            ):
                return False


            return True


        # ======================================
        # THE DAILY STAR
        # ======================================

        if source == "The Daily Star":

            blocked = [

                "/search",
                "/tag/",
                "/author/",
                "/category/",
                "/subscribe",
                "/about",
                "/contact",
                "/video/",
                "/photo/",
                "/gallery/",

            ]


            if any(
                item in path
                for item in blocked
            ):
                return False


            # Actual Daily Star article URLs
            # normally end with numeric article ID.

            if not re.search(
                r"-\d+$",
                path
            ):
                return False


            return True


        # ======================================
        # PROTHOM ALO
        # ======================================

        if source == "Prothom Alo":

            blocked = [

                "/search",
                "/collection",
                "/author/",
                "/topic/",
                "/tag/",
                "/video/",
                "/photo/",
                "/gallery/",
                "/about",
                "/contact",

            ]


            if any(
                item in path
                for item in blocked
            ):
                return False


            parts = [
                x
                for x in path.split("/")
                if x
            ]


            if len(parts) < 2:
                return False


            last_part = parts[-1]


            # Prothom Alo article ID
            # example: g7a92y0s2h

            if not re.fullmatch(
                r"[a-zA-Z0-9_-]{8,}",
                last_part
            ):
                return False


            return True


        # ======================================
        # THE BUSINESS STANDARD
        # ======================================

        if source == "The Business Standard":

            blocked = [

                "/latest",
                "/search",
                "/tag/",
                "/author/",
                "/category/",
                "/video/",
                "/photo/",
                "/gallery/",
                "/about",
                "/contact",

            ]


            if any(
                item in path
                for item in blocked
            ):
                return False


            # TBS article URLs normally end
            # with numeric article ID.

            if not re.search(
                r"-\d+$",
                path
            ):
                return False


            return True


        return False


    except Exception:

        return False


# ==========================================
# FIND ARTICLE LINKS
# ==========================================

def get_article_links(site):

    listing_url = site[
        "listing_url"
    ]

    print()
    print(
        "Listing page:",
        listing_url
    )


    html = get_page(
        listing_url
    )


    if not html:

        return []


    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    listing_domain = urlparse(
        listing_url
    ).netloc


    links = []
    seen = set()


    # ======================================
    # NORMAL <a href="">
    # ======================================

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a.get(
            "href"
        )


        if not href:
            continue


        url = urljoin(
            listing_url,
            href
        )


        parsed = urlparse(
            url
        )


        # ----------------------------------
        # Same domain only
        # ----------------------------------

        if parsed.netloc != listing_domain:
            continue


        # ----------------------------------
        # Remove fragments
        # ----------------------------------

        clean_url = url.split(
            "#"
        )[0]


        # ----------------------------------
        # Remove duplicate
        # ----------------------------------

        if clean_url in seen:
            continue


        # ----------------------------------
        # Article URL filter
        # ----------------------------------

        if not is_probable_article_url(
            clean_url,
            site["name"]
        ):
            continue


        # ----------------------------------
        # Link text
        # ----------------------------------

        title = a.get_text(
            " ",
            strip=True
        )


        # Very short links are usually
        # navigation/category links.

        if len(title) < 15:
            continue


        seen.add(
            clean_url
        )


        links.append(
            clean_url
        )


    # ======================================
    # PROTHOM ALO FALLBACK
    # ======================================

    if (
        site["name"] == "Prothom Alo"
        and len(links) < MAX_LINKS_PER_SITE
    ):

        raw_html = html.replace(
            "\\/",
            "/"
        )


        pattern = (
            r'https?://www\.prothomalo\.com'
            r'/[A-Za-z0-9_./-]+'
        )


        matches = re.findall(
            pattern,
            raw_html
        )


        for url in matches:

            url = url.rstrip(
                '",\\'
            )


            if url in seen:
                continue


            if not is_probable_article_url(
                url,
                site["name"]
            ):
                continue


            seen.add(
                url
            )


            links.append(
                url
            )


    return links


# ==========================================
# EXTRACT ARTICLE
# ==========================================

def extract_article(
    url,
    source
):

    html = get_page(
        url
    )


    if not html:
        return None


    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    # ======================================
    # TITLE
    # ======================================

    title = None


    # og:title

    tag = soup.find(
        "meta",
        property="og:title"
    )


    if tag:

        title = tag.get(
            "content"
        )


    # h1 fallback

    if not title:

        h1 = soup.find(
            "h1"
        )


        if h1:

            title = h1.get_text(
                " ",
                strip=True
            )


    # title tag fallback

    if not title and soup.title:

        title = soup.title.get_text(
            " ",
            strip=True
        )


    if not title:
        return None


    title = title.strip()


    # ======================================
    # DESCRIPTION
    # ======================================

    description = ""


    tag = soup.find(
        "meta",
        property="og:description"
    )


    if tag:

        description = tag.get(
            "content",
            ""
        )


    if not description:

        tag = soup.find(
            "meta",
            attrs={
                "name": "description"
            }
        )


        if tag:

            description = tag.get(
                "content",
                ""
            )


    # ======================================
    # IMAGE
    # ======================================

    image = None


    tag = soup.find(
        "meta",
        property="og:image"
    )


    if tag:

        image = tag.get(
            "content"
        )


    if image:

        image = urljoin(
            url,
            image
        )


    # ======================================
    # PUBLISHED DATE
    # ======================================

    published_at = (
        extract_published_date(
            soup
        )
    )


    # ======================================
    # NO DATE
    # ======================================

    if not published_at:

        print()
        print(
            "[SKIP - NO DATE]"
        )

        print(
            "TITLE:",
            title
        )

        return None


    # ======================================
    # OLDER THAN 2 DAYS
    # ======================================

    if not is_recent_news(
        published_at
    ):

        print()
        print(
            "[SKIP - OLDER THAN 2 DAYS]"
        )

        print(
            "TITLE:",
            title
        )

        print(
            "DATE:",
            published_at
        )

        return None


    # ======================================
    # RETURN
    # ======================================

    return {

        "source": source,

        "title": title,

        "description":
            description.strip(),

        "image": image,

        "url": url,

        "published_at":
            published_at
    }


# ==========================================
# SCRAPE ONE SITE
# ==========================================

def scrape_site(site):

    print()
    print(
        "=" * 70
    )

    print(
        "SOURCE:",
        site["name"]
    )

    print(
        "=" * 70
    )


    # ======================================
    # FIND ARTICLE LINKS
    # ======================================

    links = get_article_links(
        site
    )


    print()
    print(
        "Possible article links:",
        len(links)
    )


    if not links:

        print(
            "WARNING: No article links found."
        )

        return


    new_count = 0
    skipped_count = 0
    existing_count = 0


    # ======================================
    # ONLY FIRST 80 LINKS
    # ======================================

    links_to_check = links[
        :MAX_LINKS_PER_SITE
    ]


    print(
        "Will check:",
        len(links_to_check)
    )


    # ======================================
    # CHECK ARTICLES
    # ======================================

    for index, url in enumerate(
        links_to_check,
        start=1
    ):

        print()
        print(
            f"[{index}/{len(links_to_check)}]"
        )

        print(
            "URL:",
            url
        )


        article = extract_article(
            url,
            site["name"]
        )


        if not article:

            skipped_count += 1

            continue


        # ==================================
        # SAVE
        # ==================================

        inserted = save_news(
            article
        )


        if inserted:

            new_count += 1


            print()
            print(
                "[NEW]"
            )

            print(
                "TITLE:",
                article["title"]
            )

            print(
                "DATE:",
                article["published_at"]
            )

            print(
                "IMAGE:",
                article["image"]
            )

            print(
                "URL:",
                article["url"]
            )


        else:

            existing_count += 1

            print(
                "[ALREADY EXISTS]"
            )


    # ======================================
    # SUMMARY
    # ======================================

    print()
    print(
        "-" * 70
    )

    print(
        site["name"],
        "SUMMARY"
    )

    print(
        "-" * 70
    )

    print(
        "Possible links:",
        len(links)
    )

    print(
        "Checked:",
        len(links_to_check)
    )

    print(
        "New saved:",
        new_count
    )

    print(
        "Already existed:",
        existing_count
    )

    print(
        "Skipped:",
        skipped_count
    )

    print(
        "-" * 70
    )


# ==========================================
# SCRAPE ALL
# ==========================================

def scrape_all():

    init_db()


    print()
    print(
        "=" * 70
    )

    print(
        "STARTING NEWS SCRAPER"
    )

    print(
        "News age limit:",
        NEWS_MAX_AGE_DAYS,
        "days"
    )

    print(
        "Maximum links per site:",
        MAX_LINKS_PER_SITE
    )

    print(
        "=" * 70
    )


    for site in SITES:

        try:

            scrape_site(
                site
            )

        except Exception as e:

            print()
            print(
                "ERROR:",
                site["name"]
            )

            print(e)

            print(
                "Continuing..."
            )


    print()
    print(
        "=" * 70
    )

    print(
        "SCRAPING COMPLETED"
    )

    print(
        "=" * 70
    )


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    scrape_all()