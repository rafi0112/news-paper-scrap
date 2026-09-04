import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone, timedelta
import json
import re

from database import init_db, save_news


# ==========================================
# NEWS SITES
# ==========================================

SITES = [
    {
        "name": "BDNews24",
        "url": "https://bdnews24.com/"
    },
    {
        "name": "The Daily Star",
        "url": "https://www.thedailystar.net/"
    },
    {
        "name": "Prothom Alo",
        "url": "https://www.prothomalo.com/"
    },
    {
        "name": "The Business Standard",
        "url": "https://www.tbsnews.net/"
    }
]


# ==========================================
# REQUEST HEADERS
# ==========================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
}


# ==========================================
# GET WEB PAGE
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

        print(f"Request failed: {url}")
        print(e)

        return None


# ==========================================
# FIND PUBLISHED DATE
# ==========================================

def extract_published_date(soup):

    # --------------------------------------
    # 1. OpenGraph / article metadata
    # --------------------------------------

    meta_names = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"property": "og:published_time"}),
        ("meta", {"name": "date"}),
        ("meta", {"name": "publish-date"}),
        ("meta", {"name": "published_time"}),
        ("meta", {"name": "datePublished"}),
    ]

    for tag_name, attrs in meta_names:

        tag = soup.find(
            tag_name,
            attrs
        )

        if tag:

            value = (
                tag.get("content")
                or tag.get("datetime")
            )

            if value:

                parsed = parse_date(value)

                if parsed:
                    return parsed


    # --------------------------------------
    # 2. <time datetime="...">
    # --------------------------------------

    time_tags = soup.find_all(
        "time"
    )

    for tag in time_tags:

        value = (
            tag.get("datetime")
            or tag.get("content")
        )

        if value:

            parsed = parse_date(value)

            if parsed:
                return parsed


    # --------------------------------------
    # 3. JSON-LD
    # --------------------------------------

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:

            data = json.loads(
                script.string or script.get_text()
            )

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
            )


            if date_value:

                parsed = parse_date(
                    date_value
                )

                if parsed:

                    return parsed


    # --------------------------------------
    # 4. Common HTML classes
    # --------------------------------------

    selectors = [
        ".published-date",
        ".publish-date",
        ".published",
        ".article-date",
        ".post-date",
        ".date"
    ]


    for selector in selectors:

        tag = soup.select_one(
            selector
        )

        if tag:

            value = tag.get(
                "datetime"
            ) or tag.get_text(
                " ",
                strip=True
            )


            parsed = parse_date(
                value
            )


            if parsed:

                return parsed


    return None


# ==========================================
# DATE PARSER
# ==========================================

def parse_date(value):

    if not value:
        return None


    value = value.strip()


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
                tzinfo=timezone.utc
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

    ]


    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt
            )


            dt = dt.replace(
                tzinfo=timezone.utc
            )


            return dt.isoformat()

        except ValueError:

            continue


    return None


# ==========================================
# CHECK NEWS AGE
# ==========================================

def is_recent_news(published_at):

    """
    Return True only if the article was published
    within the last 2 days.
    """

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
                tzinfo=timezone.utc
            )


        now = datetime.now(
            timezone.utc
        )


        cutoff = now - timedelta(
            days=2
        )


        return article_date >= cutoff


    except Exception as e:

        print(
            "Date validation failed:",
            published_at
        )

        print(e)

        return False


# ==========================================
# ARTICLE EXTRACTION
# ==========================================

def extract_article(url, source):

    html = get_page(url)

    if not html:

        return None


    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    # --------------------------------------
    # TITLE
    # --------------------------------------

    title = None


    tag = soup.find(
        "meta",
        property="og:title"
    )


    if tag:

        title = tag.get(
            "content"
        )


    if not title:

        h1 = soup.find("h1")

        if h1:

            title = h1.get_text(
                " ",
                strip=True
            )


    # --------------------------------------
    # DESCRIPTION
    # --------------------------------------

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


    # --------------------------------------
    # IMAGE
    # --------------------------------------

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


    # --------------------------------------
    # PUBLISHED DATE
    # --------------------------------------

    published_at = extract_published_date(
        soup
    )


    # --------------------------------------
    # VALIDATE TITLE
    # --------------------------------------

    if not title:

        return None


    # --------------------------------------
    # IMPORTANT:
    # SKIP ARTICLES WITHOUT DATE
    # --------------------------------------

    if not published_at:

        print(
            "Skipping article: "
            "publication date not found."
        )

        print(
            "TITLE:",
            title.strip()
        )

        return None


    # --------------------------------------
    # IMPORTANT:
    # SKIP ARTICLES OLDER THAN 2 DAYS
    # --------------------------------------

    if not is_recent_news(
        published_at
    ):

        print(
            "\n[SKIP - OLDER THAN 2 DAYS]"
        )

        print(
            "TITLE:",
            title.strip()
        )

        print(
            "DATE:",
            published_at
        )

        return None


    # --------------------------------------
    # RETURN ARTICLE
    # --------------------------------------

    return {

        "source": source,

        "title": title.strip(),

        "description":
            description.strip(),

        "image": image,

        "url": url,

        "published_at":
            published_at

    }


# ==========================================
# FIND ARTICLE LINKS
# ==========================================

def get_article_links(site):

    html = get_page(
        site["url"]
    )


    if not html:

        return []


    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    domain = urlparse(
        site["url"]
    ).netloc


    links = []

    seen = set()


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
            site["url"],
            href
        )


        parsed = urlparse(
            url
        )


        # --------------------------------------
        # Same domain only
        # --------------------------------------

        if parsed.netloc != domain:

            continue


        # --------------------------------------
        # Ignore duplicate
        # --------------------------------------

        if url in seen:

            continue


        title = a.get_text(
            " ",
            strip=True
        )


        # --------------------------------------
        # Ignore navigation links
        # --------------------------------------

        if len(title) < 20:

            continue


        seen.add(url)

        links.append(url)


    return links


# ==========================================
# SCRAPE ONE SITE
# ==========================================

def scrape_site(site):

    print()

    print(
        "=" * 70
    )

    print(
        site["name"]
    )

    print(
        "=" * 70
    )


    links = get_article_links(
        site
    )


    print(
        "Possible links:",
        len(links)
    )


    new_count = 0


    # --------------------------------------
    # Check maximum 20 links
    # --------------------------------------

    for url in links[:20]:

        article = extract_article(
            url,
            site["name"]
        )


        if not article:

            continue


        inserted = save_news(
            article
        )


        if inserted:

            new_count += 1


            print(
                "\n[NEW]"
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


    print(
        f"\nNew articles saved: {new_count}"
    )


# ==========================================
# SCRAPE ALL SITES
# ==========================================

def scrape_all():

    init_db()


    print(
        "\nStarting news scraper..."
    )


    for site in SITES:

        scrape_site(
            site
        )


    print(
        "\nScraping completed."
    )


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    scrape_all()