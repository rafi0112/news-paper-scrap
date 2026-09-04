import os
import io
import json
import re
import requests

from urllib.parse import urljoin
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client, Client


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv(
    "FACEBOOK_PAGE_ACCESS_TOKEN"
)

META_GRAPH_VERSION = os.getenv(
    "META_GRAPH_VERSION",
    "v25.0"
)

MAX_POSTS_PER_RUN = 3

CARD_WIDTH = 1200
CARD_HEIGHT = 1200

REQUEST_TIMEOUT = 25


# ============================================================
# VALIDATE ENVIRONMENT
# ============================================================

required = {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
    "FACEBOOK_PAGE_ID": FACEBOOK_PAGE_ID,
    "FACEBOOK_PAGE_ACCESS_TOKEN": FACEBOOK_PAGE_ACCESS_TOKEN,
}

missing = [
    key
    for key, value in required.items()
    if not value
]

if missing:
    raise RuntimeError(
        "Missing environment variables: "
        + ", ".join(missing)
    )


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
})


# ============================================================
# FONT
# ============================================================

def get_font(size, bold=False):

    # IMPORTANT:
    # Bengali fonts MUST come before DejaVu.

    preferred = []

    if bold:
        preferred.extend([
            "/usr/share/fonts/truetype/noto/"
            "NotoSansBengali-Bold.ttf",

            "/usr/share/fonts/opentype/noto/"
            "NotoSansBengali-Bold.ttf",

            "/usr/share/fonts/truetype/noto/"
            "NotoSansBengaliUI-Bold.ttf",
        ])

    else:
        preferred.extend([
            "/usr/share/fonts/truetype/noto/"
            "NotoSansBengali-Regular.ttf",

            "/usr/share/fonts/opentype/noto/"
            "NotoSansBengali-Regular.ttf",

            "/usr/share/fonts/truetype/noto/"
            "NotoSansBengaliUI-Regular.ttf",
        ])

    # Search preferred fonts first
    for path in preferred:
        if os.path.exists(path):
            print(f"Font: {path}")
            return ImageFont.truetype(path, size)

    # Recursive search
    search_dirs = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
    ]

    patterns = []

    if bold:
        patterns = [
            "NotoSansBengali-Bold.ttf",
            "NotoSansBengaliUI-Bold.ttf",
            "NotoSans-Bold.ttf",
        ]
    else:
        patterns = [
            "NotoSansBengali-Regular.ttf",
            "NotoSansBengaliUI-Regular.ttf",
            "NotoSans-Regular.ttf",
        ]

    for root in search_dirs:

        for dirpath, _, filenames in os.walk(root):

            for filename in filenames:

                if filename in patterns:

                    path = os.path.join(
                        dirpath,
                        filename
                    )

                    print(f"Font: {path}")

                    return ImageFont.truetype(
                        path,
                        size
                    )

    # Final fallback
    fallback = (
        "/usr/share/fonts/truetype/dejavu/"
        "DejaVuSans-Bold.ttf"
        if bold
        else
        "/usr/share/fonts/truetype/dejavu/"
        "DejaVuSans.ttf"
    )

    print(f"WARNING: Bengali Noto font not found.")
    print(f"Font fallback: {fallback}")

    return ImageFont.truetype(
        fallback,
        size
    )


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width
):

    words = text.split()

    lines = []
    current = ""

    for word in words:

        test = (
            word
            if not current
            else current + " " + word
        )

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:

            current = test

        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


# ============================================================
# GENERIC IMAGE DETECTION
# ============================================================

def is_generic_image(url):

    if not url:
        return True

    lower = url.lower()

    # These are truly generic images.
    bad_patterns = [
        "banner.png",
        "banner.jpg",
        "banner.jpeg",
        "/logo.",
        "logo.png",
        "logo.jpg",
        "logo.jpeg",
        "default.jpg",
        "default.png",
        "default.jpeg",
        "placeholder",
        "og-default",
        "fallback",
        "avatar",
        "/icon.",
        "icon.png",
        "icon.jpg",
    ]

    for pattern in bad_patterns:

        if pattern in lower:
            return True

    # IMPORTANT:
    #
    # DO NOT reject:
    #
    # social_share
    # share-image
    #
    # because TBS can use /styles/social_share/
    # for a real article photograph.

    return False


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(url):

    if not url:
        return None

    try:

        print(f"Downloading image: {url}")

        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get("Content-Type", "")
            .lower()
        )

        # Make sure this is actually an image.
        if (
            not content_type.startswith("image/")
            and not url.lower().endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".gif",
                )
            )
        ):

            print(
                f"✗ Not an image response: "
                f"{content_type}"
            )

            return None

        image = Image.open(
            io.BytesIO(response.content)
        )

        image.load()

        print(
            f"✓ Image downloaded "
            f"({image.width}, {image.height})"
        )

        return image.convert("RGB")

    except Exception as e:

        print(
            f"✗ Image download failed: {e}"
        )

        return None


# ============================================================
# ARTICLE IMAGE EXTRACTION
# ============================================================

def extract_article_image(article_url):

    if not article_url:
        return None

    try:

        print(
            "Opening article page to find "
            "actual article image..."
        )

        response = session.get(
            article_url,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # ----------------------------------------------------
        # 1. OG IMAGE
        # ----------------------------------------------------

        og = soup.find(
            "meta",
            property="og:image"
        )

        if og and og.get("content"):

            image_url = urljoin(
                article_url,
                og["content"].strip()
            )

            if not is_generic_image(image_url):

                print(
                    f"✓ Found og:image: "
                    f"{image_url}"
                )

                return image_url

        # ----------------------------------------------------
        # 2. TWITTER IMAGE
        # ----------------------------------------------------

        twitter = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        )

        if twitter and twitter.get("content"):

            image_url = urljoin(
                article_url,
                twitter["content"].strip()
            )

            if not is_generic_image(image_url):

                print(
                    f"✓ Found twitter:image: "
                    f"{image_url}"
                )

                return image_url

        # ----------------------------------------------------
        # 3. JSON-LD
        # ----------------------------------------------------

        for script in soup.find_all(
            "script",
            type="application/ld+json"
        ):

            try:

                data = json.loads(
                    script.string or
                    script.get_text()
                )

                objects = (
                    data
                    if isinstance(data, list)
                    else [data]
                )

                for obj in objects:

                    if not isinstance(
                        obj,
                        dict
                    ):
                        continue

                    image = obj.get("image")

                    if isinstance(
                        image,
                        str
                    ):

                        image_url = urljoin(
                            article_url,
                            image
                        )

                        if not is_generic_image(
                            image_url
                        ):

                            print(
                                "✓ Found "
                                "JSON-LD image"
                            )

                            return image_url

                    if isinstance(
                        image,
                        dict
                    ):

                        image_url = image.get(
                            "url"
                        )

                        if image_url:

                            image_url = urljoin(
                                article_url,
                                image_url
                            )

                            if not is_generic_image(
                                image_url
                            ):

                                print(
                                    "✓ Found "
                                    "JSON-LD image"
                                )

                                return image_url

                    if isinstance(
                        image,
                        list
                    ):

                        for item in image:

                            if isinstance(
                                item,
                                str
                            ):

                                image_url = urljoin(
                                    article_url,
                                    item
                                )

                                if not is_generic_image(
                                    image_url
                                ):

                                    print(
                                        "✓ Found "
                                        "JSON-LD image"
                                    )

                                    return image_url

            except Exception:
                continue

        print(
            "✗ Could not find actual "
            "article image."
        )

        return None

    except Exception as e:

        print(
            f"✗ Article page image "
            f"extraction failed: {e}"
        )

        return None


# ============================================================
# RESOLVE IMAGE
# ============================================================

def resolve_article_image(
    stored_image,
    article_url
):

    # --------------------------------------------------------
    # FIRST:
    # Try the stored image directly.
    #
    # This is the important fix for TBS.
    # --------------------------------------------------------

    if stored_image:

        print(
            f"Stored image: {stored_image}"
        )

        if not is_generic_image(
            stored_image
        ):

            print(
                "Stored image appears to "
                "be an article image."
            )

            image = download_image(
                stored_image
            )

            if image is not None:

                return image

            print(
                "Stored image download failed."
            )

    # --------------------------------------------------------
    # SECOND:
    # Try article-page metadata.
    # --------------------------------------------------------

    actual_url = extract_article_image(
        article_url
    )

    if actual_url:

        image = download_image(
            actual_url
        )

        if image is not None:

            return image

    # --------------------------------------------------------
    # Nothing worked.
    # --------------------------------------------------------

    print(
        "✗ No usable article image found."
    )

    return None


# ============================================================
# CROP IMAGE TO SQUARE
# ============================================================

def crop_to_square(image):

    width, height = image.size

    size = min(
        width,
        height
    )

    left = (
        width - size
    ) // 2

    top = (
        height - size
    ) // 2

    right = left + size
    bottom = top + size

    return image.crop(
        (
            left,
            top,
            right,
            bottom
        )
    )


# ============================================================
# CREATE MODERN PHOTO CARD
# ============================================================

def create_photo_card(
    image,
    title,
    source
):

    try:

        image = crop_to_square(
            image
        )

        image = image.resize(
            (
                CARD_WIDTH,
                CARD_HEIGHT
            ),
            Image.Resampling.LANCZOS
        )

        # ----------------------------------------------------
        # Slight blur background layer
        # ----------------------------------------------------

        background = image.copy()

        background = background.filter(
            ImageFilter.GaussianBlur(8)
        )

        # Darken background
        overlay = Image.new(
            "RGBA",
            background.size,
            (0, 0, 0, 65)
        )

        background = Image.alpha_composite(
            background.convert("RGBA"),
            overlay
        )

        card = background.convert(
            "RGBA"
        )

        # ----------------------------------------------------
        # Main image
        # ----------------------------------------------------

        card.alpha_composite(
            image.convert("RGBA")
        )

        # ----------------------------------------------------
        # Top gradient
        # ----------------------------------------------------

        gradient = Image.new(
            "RGBA",
            card.size,
            (0, 0, 0, 0)
        )

        gd = ImageDraw.Draw(
            gradient
        )

        for y in range(500):

            alpha = int(
                150 * (1 - y / 500)
            )

            gd.line(
                [
                    (0, y),
                    (CARD_WIDTH, y)
                ],
                fill=(
                    0,
                    0,
                    0,
                    alpha
                )
            )

        card = Image.alpha_composite(
            card,
            gradient
        )

        # ----------------------------------------------------
        # Bottom gradient
        # ----------------------------------------------------

        gradient2 = Image.new(
            "RGBA",
            card.size,
            (0, 0, 0, 0)
        )

        gd2 = ImageDraw.Draw(
            gradient2
        )

        start_y = 600

        for y in range(
            start_y,
            CARD_HEIGHT
        ):

            progress = (
                y - start_y
            ) / (
                CARD_HEIGHT - start_y
            )

            alpha = int(
                20 + 205 * progress
            )

            gd2.line(
                [
                    (0, y),
                    (CARD_WIDTH, y)
                ],
                fill=(
                    0,
                    0,
                    0,
                    alpha
                )
            )

        card = Image.alpha_composite(
            card,
            gradient2
        )

        draw = ImageDraw.Draw(
            card
        )

        # ----------------------------------------------------
        # Source badge
        # ----------------------------------------------------

        source_font = get_font(
            28,
            bold=True
        )

        badge_text = source

        bbox = draw.textbbox(
            (0, 0),
            badge_text,
            font=source_font
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        badge_x = 55
        badge_y = 55

        badge_width = (
            text_width + 44
        )

        badge_height = 54

        draw.rounded_rectangle(
            (
                badge_x,
                badge_y,
                badge_x + badge_width,
                badge_y + badge_height
            ),
            radius=27,
            fill=(
                255,
                255,
                255,
                225
            )
        )

        draw.text(
            (
                badge_x + 22,
                badge_y + 8
            ),
            badge_text,
            font=source_font,
            fill=(
                20,
                20,
                20,
                255
            )
        )

        # ----------------------------------------------------
        # Title
        # ----------------------------------------------------

        title_font = get_font(
            58,
            bold=True
        )

        max_width = 1050

        lines = wrap_text(
            draw,
            title,
            title_font,
            max_width
        )

        # Limit title height
        max_lines = 5

        if len(lines) > max_lines:

            lines = lines[:max_lines]

            last = lines[-1]

            while True:

                test = last + "..."

                bbox = draw.textbbox(
                    (0, 0),
                    test,
                    font=title_font
                )

                if (
                    bbox[2] - bbox[0]
                    <= max_width
                ):
                    lines[-1] = test
                    break

                last = last[:-1]

        line_spacing = 12

        heights = []

        for line in lines:

            bbox = draw.textbbox(
                (0, 0),
                line,
                font=title_font
            )

            heights.append(
                bbox[3] - bbox[1]
            )

        total_height = (
            sum(heights)
            + line_spacing * (
                len(lines) - 1
            )
        )

        y = (
            CARD_HEIGHT
            - total_height
            - 90
        )

        # Text shadow
        for line, height in zip(
            lines,
            heights
        ):

            draw.text(
                (
                    60 + 3,
                    y + 3
                ),
                line,
                font=title_font,
                fill=(
                    0,
                    0,
                    0,
                    180
                )
            )

            draw.text(
                (
                    60,
                    y
                ),
                line,
                font=title_font,
                fill=(
                    255,
                    255,
                    255,
                    255
                )
            )

            y += (
                height
                + line_spacing
            )

        # ----------------------------------------------------
        # Export
        # ----------------------------------------------------

        output = io.BytesIO()

        card.convert("RGB").save(
            output,
            format="JPEG",
            quality=94,
            optimize=True
        )

        output.seek(0)

        print(
            "✓ Modern photo card created"
        )

        return output

    except Exception as e:

        print(
            f"✗ Photo card creation "
            f"failed: {e}"
        )

        return None


# ============================================================
# FACEBOOK POST
# ============================================================

def post_to_facebook(
    photo_bytes,
    title,
    article_url
):

    endpoint = (
        f"https://graph.facebook.com/"
        f"{META_GRAPH_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/photos"
    )

    caption = (
        f"{title}\n\n"
        f"{article_url}"
    )

    try:

        response = requests.post(
            endpoint,
            data={
                "access_token":
                    FACEBOOK_PAGE_ACCESS_TOKEN,
                "caption":
                    caption,
            },
            files={
                "source": (
                    "news.jpg",
                    photo_bytes,
                    "image/jpeg"
                )
            },
            timeout=60
        )

        data = response.json()

        if response.ok and data.get("id"):

            return data["id"], None

        return (
            None,
            data.get(
                "error",
                data
            )
        )

    except Exception as e:

        return None, str(e)


# ============================================================
# GET UNPOSTED NEWS
# ============================================================

def get_unposted_news():

    result = (
        supabase
        .table("news")
        .select(
            "id,title,source,image,url"
        )
        .eq(
            "facebook_posted",
            False
        )
        .neq(
            "source",
            "The Daily Star"
        )
        .not_.is_(
            "image",
            "null"
        )
        .order(
            "published_at",
            desc=True
        )
        .limit(
            MAX_POSTS_PER_RUN
        )
        .execute()
    )

    return result.data or []


# ============================================================
# MARK POSTED
# ============================================================

def mark_posted(
    news_id,
    post_id
):

    try:

        supabase.table(
            "news"
        ).update({

            "facebook_posted":
                True,

            "facebook_post_id":
                post_id,

            "facebook_posted_at":
                "now()",

            "facebook_error":
                None,

        }).eq(
            "id",
            news_id
        ).execute()

        print(
            "✓ Supabase: "
            "facebook_posted = TRUE"
        )

    except Exception as e:

        print(
            "✗ Supabase update failed:",
            e
        )


# ============================================================
# SAVE ERROR
# ============================================================

def save_error(
    news_id,
    error
):

    try:

        supabase.table(
            "news"
        ).update({

            "facebook_error":
                str(error),

            "facebook_posted":
                False,

        }).eq(
            "id",
            news_id
        ).execute()

    except Exception as e:

        print(
            "✗ Could not save error:",
            e
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n=========================================="
    )

    print(
        "Starting Facebook poster..."
    )

    print(
        "=========================================="
    )

    print(
        f"Graph API: "
        f"{META_GRAPH_VERSION}"
    )

    print(
        f"Maximum posts: "
        f"{MAX_POSTS_PER_RUN}"
    )

    print(
        "Daily Star: SKIPPED"
    )

    news = get_unposted_news()

    print(
        f"Found {len(news)} news."
    )

    posted_count = 0

    for article in news:

        print(
            "\n------------------------------------------"
        )

        news_id = article["id"]

        title = (
            article.get("title")
            or "Untitled"
        )

        source = (
            article.get("source")
            or ""
        )

        article_url = (
            article.get("url")
            or ""
        )

        stored_image = (
            article.get("image")
        )

        print(
            f"Processing: {title}"
        )

        print(
            f"Source: {source}"
        )

        print(
            f"Article URL: {article_url}"
        )

        try:

            image = resolve_article_image(
                stored_image,
                article_url
            )

            if image is None:

                error = (
                    "Could not obtain a "
                    "usable original article image."
                )

                print(
                    f"✗ FAILED\n{error}"
                )

                save_error(
                    news_id,
                    error
                )

                continue

            card = create_photo_card(
                image,
                title,
                source
            )

            if card is None:

                error = (
                    "Could not create photo "
                    "card from original article image."
                )

                print(
                    f"✗ FAILED\n{error}"
                )

                save_error(
                    news_id,
                    error
                )

                continue

            print(
                "Posting photo card to Facebook..."
            )

            post_id, error = (
                post_to_facebook(
                    card,
                    title,
                    article_url
                )
            )

            if post_id:

                print(
                    "✓ Facebook post successful"
                )

                print(
                    f"Facebook Post ID: "
                    f"{post_id}"
                )

                mark_posted(
                    news_id,
                    post_id
                )

                posted_count += 1

                print(
                    "✓ COMPLETE"
                )

            else:

                print(
                    "✗ Facebook post failed"
                )

                print(
                    f"Error: {error}"
                )

                save_error(
                    news_id,
                    error
                )

        except Exception as e:

            print(
                f"✗ FAILED\n{e}"
            )

            save_error(
                news_id,
                e
            )

    print(
        "\n=========================================="
    )

    print(
        f"Finished. Posted: "
        f"{posted_count}"
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()