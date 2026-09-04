import os
import io
import json
import re
import requests

from urllib.parse import urljoin

from PIL import Image, ImageDraw, ImageFont
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client


# =========================================================
# ENVIRONMENT
# =========================================================

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


# =========================================================
# CONFIG
# =========================================================

# TEST WITH 1 FIRST
# MAX_POSTS_PER_RUN = 1

# After successful test:
MAX_POSTS_PER_RUN = 3

CARD_WIDTH = 1200
CARD_HEIGHT = 1200

IMAGE_TIMEOUT = 25
ARTICLE_TIMEOUT = 25

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)


# =========================================================
# VALIDATE ENVIRONMENT
# =========================================================

required = {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
    "FACEBOOK_PAGE_ID": FACEBOOK_PAGE_ID,
    "FACEBOOK_PAGE_ACCESS_TOKEN":
        FACEBOOK_PAGE_ACCESS_TOKEN,
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


# =========================================================
# SUPABASE
# =========================================================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# =========================================================
# FONT FINDER
# =========================================================

def get_font(size, bold=False):

    """
    Find Bengali-capable Noto font.

    GitHub Actions installs it through:
        fonts-noto-core
    """

    if bold:

        preferred = [
            "NotoSansBengali-Bold.ttf",
            "NotoSansBengaliUI-Bold.ttf",
            "NotoSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
        ]

    else:

        preferred = [
            "NotoSansBengali-Regular.ttf",
            "NotoSansBengaliUI-Regular.ttf",
            "NotoSans-Regular.ttf",
            "DejaVuSans.ttf",
        ]

    search_dirs = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
    ]

    # -----------------------------------------------------
    # Search recursively
    # -----------------------------------------------------

    for root_dir in search_dirs:

        for root, dirs, files in os.walk(
            root_dir
        ):

            for filename in files:

                if filename in preferred:

                    path = os.path.join(
                        root,
                        filename
                    )

                    try:

                        print(
                            f"Font: {path}"
                        )

                        return ImageFont.truetype(
                            path,
                            size
                        )

                    except Exception:
                        pass

    # -----------------------------------------------------
    # Repository font fallback
    # -----------------------------------------------------

    for directory in [
        "fonts",
        "./fonts",
    ]:

        for filename in preferred:

            path = os.path.join(
                directory,
                filename
            )

            if os.path.exists(path):

                try:

                    print(
                        f"Font: {path}"
                    )

                    return ImageFont.truetype(
                        path,
                        size
                    )

                except Exception:
                    pass

    print(
        "WARNING: Bengali font not found."
    )

    return ImageFont.load_default()


# =========================================================
# TEXT WIDTH
# =========================================================

def get_text_width(
    draw,
    text,
    font
):

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font
    )

    return (
        bbox[2]
        - bbox[0]
    )


# =========================================================
# TEXT WRAP
# =========================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
    max_lines=4
):

    words = str(text).split()

    if not words:
        return []

    lines = []

    current = ""

    for word in words:

        test = (
            word
            if not current
            else current
            + " "
            + word
        )

        width = get_text_width(
            draw,
            test,
            font
        )

        if width <= max_width:

            current = test

        else:

            if current:

                lines.append(
                    current
                )

            current = word

    if current:

        lines.append(
            current
        )

    # -----------------------------------------------------
    # Maximum line count
    # -----------------------------------------------------

    if len(lines) <= max_lines:

        return lines

    lines = lines[:max_lines]

    # Add ...
    last = lines[-1]

    while len(last) > 1:

        candidate = (
            last.rstrip()
            + "..."
        )

        if (
            get_text_width(
                draw,
                candidate,
                font
            )
            <= max_width
        ):

            lines[-1] = candidate
            break

        last = last[:-1]

    return lines


# =========================================================
# GENERIC IMAGE DETECTOR
# =========================================================

def is_generic_image(
    image_url
):

    if not image_url:

        return True

    url = image_url.lower()

    generic_words = [
        "banner",
        "logo",
        "default",
        "placeholder",
        "share-image",
        "share_image",
        "og-default",
        "og_default",
        "fallback",
        "avatar",
        "icon",
        "site-logo",
        "site_logo",
    ]

    for word in generic_words:

        if word in url:

            return True

    return False


# =========================================================
# DOWNLOAD IMAGE
# =========================================================

def download_image(
    image_url
):

    if not image_url:

        return None

    urls = [
        image_url
    ]

    # HTTP fallback
    if image_url.startswith(
        "https://"
    ):

        urls.append(
            image_url.replace(
                "https://",
                "http://",
                1
            )
        )

    for url in urls:

        try:

            print(
                f"Downloading image: {url}"
            )

            response = requests.get(
                url,
                headers={
                    "User-Agent":
                        USER_AGENT,
                    "Accept":
                        "image/avif,"
                        "image/webp,"
                        "image/apng,"
                        "image/jpeg,"
                        "image/png,"
                        "image/*,"
                        "*/*;q=0.8",
                },
                timeout=IMAGE_TIMEOUT
            )

            response.raise_for_status()

            image = Image.open(
                io.BytesIO(
                    response.content
                )
            )

            image = image.convert(
                "RGB"
            )

            print(
                f"✓ Image downloaded "
                f"{image.size}"
            )

            return image

        except Exception as e:

            print(
                f"Image download failed: {e}"
            )

    return None


# =========================================================
# EXTRACT ARTICLE IMAGE
# =========================================================

def extract_article_image(
    article_url
):

    """
    Open actual article page and find:
        og:image
        twitter:image
        JSON-LD image

    This fixes cases where scraper stored
    generic banner/logo image.
    """

    if not article_url:

        return None

    try:

        print(
            "Opening article page to find "
            "actual article image..."
        )

        response = requests.get(
            article_url,
            headers={
                "User-Agent":
                    USER_AGENT,
                "Accept":
                    "text/html,"
                    "application/xhtml+xml"
            },
            timeout=ARTICLE_TIMEOUT
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # =================================================
        # 1. OG IMAGE
        # =================================================

        meta = soup.find(
            "meta",
            attrs={
                "property":
                    "og:image"
            }
        )

        if meta:

            image_url = (
                meta.get("content")
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
                        "✓ Found og:image:"
                    )

                    print(
                        image_url
                    )

                    return image_url

        # =================================================
        # 2. TWITTER IMAGE
        # =================================================

        meta = soup.find(
            "meta",
            attrs={
                "name":
                    "twitter:image"
            }
        )

        if meta:

            image_url = (
                meta.get("content")
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
                        "✓ Found twitter:image:"
                    )

                    print(
                        image_url
                    )

                    return image_url

        # =================================================
        # 3. JSON-LD
        # =================================================

        scripts = soup.find_all(
            "script",
            attrs={
                "type":
                    "application/ld+json"
            }
        )

        for script in scripts:

            try:

                raw = script.string

                if not raw:
                    continue

                data = json.loads(
                    raw
                )

                objects = []

                if isinstance(
                    data,
                    list
                ):

                    objects = data

                elif isinstance(
                    data,
                    dict
                ):

                    objects = [
                        data
                    ]

                    graph = data.get(
                        "@graph"
                    )

                    if isinstance(
                        graph,
                        list
                    ):

                        objects.extend(
                            graph
                        )

                for obj in objects:

                    if not isinstance(
                        obj,
                        dict
                    ):

                        continue

                    image = obj.get(
                        "image"
                    )

                    # String
                    if isinstance(
                        image,
                        str
                    ):

                        image = urljoin(
                            article_url,
                            image
                        )

                        if not is_generic_image(
                            image
                        ):

                            print(
                                "✓ Found JSON-LD image:"
                            )

                            print(
                                image
                            )

                            return image

                    # List
                    if isinstance(
                        image,
                        list
                    ):

                        for item in image:

                            if isinstance(
                                item,
                                str
                            ):

                                item = urljoin(
                                    article_url,
                                    item
                                )

                                if not is_generic_image(
                                    item
                                ):

                                    print(
                                        "✓ Found JSON-LD image:"
                                    )

                                    print(
                                        item
                                    )

                                    return item

                    # Dict
                    if isinstance(
                        image,
                        dict
                    ):

                        image_url = (
                            image.get(
                                "url"
                            )
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
                                    "✓ Found JSON-LD image:"
                                )

                                print(
                                    image_url
                                )

                                return image_url

            except Exception:
                continue

    except Exception as e:

        print(
            "Article page image extraction failed:"
        )

        print(
            str(e)
        )

    return None


# =========================================================
# RESOLVE BEST IMAGE
# =========================================================

def resolve_article_image(
    stored_image,
    article_url
):

    """
    Decide which image to use.

    If stored image looks like banner/logo,
    fetch actual image from article page.
    """

    # -----------------------------------------------------
    # Case 1:
    # Stored image looks generic
    # -----------------------------------------------------

    if is_generic_image(
        stored_image
    ):

        print(
            "⚠ Stored image looks like "
            "banner/logo/default."
        )

        actual_image_url = (
            extract_article_image(
                article_url
            )
        )

        if actual_image_url:

            return actual_image_url

        print(
            "✗ Could not find actual article image."
        )

        return None

    # -----------------------------------------------------
    # Case 2:
    # Stored image looks normal
    # -----------------------------------------------------

    print(
        "Stored image appears to be "
        "an article image."
    )

    return stored_image


# =========================================================
# COVER CROP
# =========================================================

def crop_to_square(
    image
):

    width, height = image.size

    if width == height:

        return image

    if width > height:

        crop = height

        left = (
            width
            - crop
        ) // 2

        return image.crop(
            (
                left,
                0,
                left + crop,
                height
            )
        )

    crop = width

    top = (
        height
        - crop
    ) // 2

    return image.crop(
        (
            0,
            top,
            width,
            top + crop
        )
    )


# =========================================================
# CREATE MODERN PHOTO CARD
# =========================================================

def create_photo_card(
    image_url,
    title,
    source,
    article_url
):

    # -----------------------------------------------------
    # Resolve actual article image
    # -----------------------------------------------------

    best_image_url = (
        resolve_article_image(
            image_url,
            article_url
        )
    )

    if not best_image_url:

        print(
            "✗ No usable article image found."
        )

        return None

    # -----------------------------------------------------
    # Download
    # -----------------------------------------------------

    image = download_image(
        best_image_url
    )

    if image is None:

        print(
            "✗ Actual article image "
            "could not be downloaded."
        )

        return None

    try:

        # =================================================
        # ORIGINAL PHOTO
        # =================================================

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

        image = image.convert(
            "RGBA"
        )

        # =================================================
        # OVERLAY
        # =================================================

        overlay = Image.new(
            "RGBA",
            (
                CARD_WIDTH,
                CARD_HEIGHT
            ),
            (
                0,
                0,
                0,
                0
            )
        )

        draw = ImageDraw.Draw(
            overlay
        )

        # -------------------------------------------------
        # Bottom gradient
        # -------------------------------------------------

        gradient_start = 500

        for y in range(
            gradient_start,
            CARD_HEIGHT
        ):

            progress = (
                y
                - gradient_start
            ) / (
                CARD_HEIGHT
                - gradient_start
            )

            alpha = int(
                235 * progress
            )

            draw.line(
                (
                    0,
                    y,
                    CARD_WIDTH,
                    y
                ),
                fill=(
                    0,
                    0,
                    0,
                    alpha
                )
            )

        # -------------------------------------------------
        # Very subtle top gradient
        # -------------------------------------------------

        for y in range(
            0,
            170
        ):

            alpha = int(
                100
                * (
                    1
                    - y / 170
                )
            )

            draw.line(
                (
                    0,
                    y,
                    CARD_WIDTH,
                    y
                ),
                fill=(
                    0,
                    0,
                    0,
                    alpha
                )
            )

        image = Image.alpha_composite(
            image,
            overlay
        )

        draw = ImageDraw.Draw(
            image
        )

        # =================================================
        # FONTS
        # =================================================

        source_font = get_font(
            34,
            bold=True
        )

        title_font = get_font(
            62,
            bold=True
        )

        # =================================================
        # SOURCE
        # =================================================

        source_text = str(
            source
        ).strip()

        source_x = 70
        source_y = 710

        source_bbox = draw.textbbox(
            (
                0,
                0
            ),
            source_text,
            font=source_font
        )

        source_width = (
            source_bbox[2]
            - source_bbox[0]
        )

        source_height = (
            source_bbox[3]
            - source_bbox[1]
        )

        # Clean modern pill
        draw.rounded_rectangle(
            (
                source_x - 18,
                source_y - 10,
                source_x
                + source_width
                + 18,
                source_y
                + source_height
                + 18
            ),
            radius=16,
            fill=(
                255,
                255,
                255,
                235
            )
        )

        draw.text(
            (
                source_x,
                source_y
            ),
            source_text,
            font=source_font,
            fill=(
                25,
                25,
                25
            )
        )

        # =================================================
        # EXACT ARTICLE TITLE
        # =================================================

        title_lines = wrap_text(
            draw,
            title,
            title_font,
            CARD_WIDTH - 140,
            max_lines=4
        )

        title_y = 800

        for line in title_lines:

            # Shadow
            draw.text(
                (
                    72,
                    title_y + 3
                ),
                line,
                font=title_font,
                fill=(
                    0,
                    0,
                    0,
                    170
                )
            )

            # Actual title
            draw.text(
                (
                    70,
                    title_y
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

            bbox = draw.textbbox(
                (
                    0,
                    0
                ),
                line,
                font=title_font
            )

            line_height = (
                bbox[3]
                - bbox[1]
            )

            title_y += (
                line_height
                + 12
            )

        # =================================================
        # SAVE
        # =================================================

        output = io.BytesIO()

        image.convert(
            "RGB"
        ).save(
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
            "Card creation error:"
        )

        print(
            str(e)
        )

        return None


# =========================================================
# FACEBOOK POST
# =========================================================

def post_to_facebook(
    card_file,
    title,
    article_url
):

    endpoint = (
        f"https://graph.facebook.com/"
        f"{META_GRAPH_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/photos"
    )

    # =====================================================
    # CLEAN CAPTION
    # =====================================================
    #
    # NO:
    #   Source:
    #   বিস্তারিত পড়ুন:
    #   NEWS UPDATE
    #   extra generated text
    #
    # Only exact article title + URL.
    # =====================================================

    caption = (
        f"{title}\n\n"
        f"{article_url}"
    )

    files = {
        "source": (
            "news-card.jpg",
            card_file,
            "image/jpeg"
        )
    }

    data = {
        "caption": caption,
        "access_token":
            FACEBOOK_PAGE_ACCESS_TOKEN
    }

    print(
        "Posting photo card to Facebook..."
    )

    response = requests.post(
        endpoint,
        files=files,
        data=data,
        timeout=60
    )

    try:

        result = response.json()

    except Exception:

        result = {
            "response":
                response.text
        }

    if response.status_code >= 400:

        raise Exception(
            "Facebook API error: "
            + str(result)
        )

    print(
        "✓ Facebook post successful"
    )

    return result


# =========================================================
# GET UNPOSTED NEWS
# =========================================================

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


# =========================================================
# MARK POSTED
# =========================================================

def mark_posted(
    news_id,
    post_id
):

    (
        supabase
        .table("news")
        .update({
            "facebook_posted": True,
            "facebook_post_id": post_id,
            "facebook_posted_at": "now()",
            "facebook_error": None
        })
        .eq(
            "id",
            news_id
        )
        .execute()
    )

    print(
        "✓ Supabase: "
        "facebook_posted = TRUE"
    )


# =========================================================
# SAVE ERROR
# =========================================================

def save_error(
    news_id,
    error
):

    try:

        (
            supabase
            .table("news")
            .update({
                "facebook_error":
                    str(error)
            })
            .eq(
                "id",
                news_id
            )
            .execute()
        )

    except Exception as e:

        print(
            "Could not save error:"
        )

        print(
            str(e)
        )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "=========================================="
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

    # =====================================================
    # GET NEWS
    # =====================================================

    news_list = get_unposted_news()

    print(
        f"Found {len(news_list)} news."
    )

    if not news_list:

        print(
            "No eligible unposted news."
        )

        return

    posted_count = 0

    # =====================================================
    # PROCESS
    # =====================================================

    for article in news_list:

        news_id = article.get(
            "id"
        )

        title = article.get(
            "title",
            ""
        )

        source = article.get(
            "source",
            ""
        )

        stored_image = article.get(
            "image"
        )

        article_url = article.get(
            "url",
            ""
        )

        print(
            "\n------------------------------------------"
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

        print(
            f"Stored image: {stored_image}"
        )

        try:

            # =================================================
            # 1. CREATE MODERN PHOTO CARD
            # =================================================

            card = create_photo_card(
                stored_image,
                title,
                source,
                article_url
            )

            if card is None:

                raise Exception(
                    "Could not create photo card "
                    "from original article image."
                )

            # =================================================
            # 2. FACEBOOK
            # =================================================

            result = post_to_facebook(
                card,
                title,
                article_url
            )

            # =================================================
            # 3. POST ID
            # =================================================

            post_id = (
                result.get("post_id")
                or result.get("id")
            )

            print(
                f"Facebook Post ID: {post_id}"
            )

            # =================================================
            # 4. SUPABASE
            # =================================================

            mark_posted(
                news_id,
                post_id
            )

            posted_count += 1

            print(
                "✓ COMPLETE"
            )

        except Exception as e:

            print(
                "\n✗ FAILED"
            )

            print(
                str(e)
            )

            save_error(
                news_id,
                e
            )

    # =====================================================
    # FINAL
    # =====================================================

    print(
        "\n=========================================="
    )

    print(
        f"Finished. Posted: {posted_count}"
    )

    print(
        "=========================================="
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()