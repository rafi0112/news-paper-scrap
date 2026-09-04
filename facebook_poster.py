import os
import io
import json
import subprocess
import requests

from urllib.parse import urljoin
from PIL import Image, ImageDraw, ImageFont, ImageFilter, features
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
# ENVIRONMENT VALIDATION
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


# ============================================================
# SUPABASE
# ============================================================

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
# FONT HELPERS
# ============================================================

def find_font_file(names):
    """Find one of the requested font filenames."""

    direct_roots = [
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/opentype/noto",
        "/usr/local/share/fonts",
    ]

    for root in direct_roots:
        for name in names:
            path = os.path.join(root, name)

            if os.path.exists(path):
                return path

    for root in [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
    ]:

        if not os.path.exists(root):
            continue

        for dirpath, _, filenames in os.walk(root):

            for name in names:

                if name in filenames:

                    return os.path.join(
                        dirpath,
                        name
                    )

    return None


def get_font(size, bold=False, bengali=False):
    """
    Bengali text:
        Noto Sans Bengali

    English/numbers:
        DejaVu Sans

    We intentionally keep the fonts separate so a mixed title
    never renders English characters as missing-glyph boxes.
    """

    if bengali:

        if bold:
            names = [
                "NotoSansBengali-Bold.ttf",
                "NotoSansBengaliUI-Bold.ttf",
            ]
        else:
            names = [
                "NotoSansBengali-Regular.ttf",
                "NotoSansBengaliUI-Regular.ttf",
            ]

        font_path = find_font_file(names)

        if not font_path:
            raise RuntimeError(
                "Noto Sans Bengali was not found. "
                "Install fonts-noto-core and fonts-noto-extra."
            )

    else:

        if bold:
            names = [
                "DejaVuSans-Bold.ttf",
            ]
        else:
            names = [
                "DejaVuSans.ttf",
            ]

        font_path = find_font_file(names)

        if not font_path:
            raise RuntimeError(
                "DejaVu Sans was not found."
            )

    print(f"Font: {font_path}")

    return ImageFont.truetype(
        font_path,
        size
    )


def verify_text_rendering_support():
    """
    Verify that Pillow has RAQM support when available.

    RAQM gives proper complex-script shaping for Bengali.
    """

    try:

        if features.check("raqm"):

            print(
                "✓ Pillow RAQM support: ENABLED"
            )

        else:

            print(
                "⚠ Pillow RAQM support: NOT AVAILABLE"
            )

            print(
                "Bengali rendering may be imperfect. "
                "Install libraqm-dev before installing Pillow."
            )

    except Exception as e:

        print(
            f"⚠ Could not check RAQM support: {e}"
        )


# ============================================================
# BENGALI DETECTION
# ============================================================

def contains_bengali(text):
    if not text:
        return False

    return any(
        "\u0980" <= char <= "\u09FF"
        for char in text
    )


# ============================================================
# MIXED TEXT RUNS
# ============================================================

def get_mixed_runs(text):
    """
    Split text into Bengali and non-Bengali runs.

    Example:
        বাংলা News Update

    becomes:
        বাংলা       -> Bengali font
         News Update -> Latin font
    """

    if not text:
        return []

    runs = []

    current = ""
    current_is_bengali = None

    for char in text:

        is_bengali = (
            "\u0980" <= char <= "\u09FF"
        )

        if current_is_bengali is None:

            current = char
            current_is_bengali = is_bengali

        elif is_bengali == current_is_bengali:

            current += char

        else:

            runs.append(
                (
                    current,
                    current_is_bengali
                )
            )

            current = char
            current_is_bengali = is_bengali

    if current:

        runs.append(
            (
                current,
                current_is_bengali
            )
        )

    return runs


# ============================================================
# TEXT MEASUREMENT
# ============================================================

def text_bbox_for_run(
    draw,
    text,
    font,
    is_bengali
):
    """
    Measure one text run.

    Bengali uses language='bn' when RAQM is available.
    """

    kwargs = {}

    if features.check("raqm"):

        kwargs["direction"] = "ltr"
        kwargs["language"] = (
            "bn"
            if is_bengali
            else "en"
        )

    return draw.textbbox(
        (0, 0),
        text,
        font=font,
        **kwargs
    )


def mixed_text_width(
    draw,
    text,
    bengali_font,
    latin_font
):

    total_width = 0

    for run, is_bengali in get_mixed_runs(text):

        font = (
            bengali_font
            if is_bengali
            else latin_font
        )

        bbox = text_bbox_for_run(
            draw,
            run,
            font,
            is_bengali
        )

        total_width += (
            bbox[2] - bbox[0]
        )

    return total_width


def mixed_text_height(
    draw,
    text,
    bengali_font,
    latin_font
):

    height = 0

    for run, is_bengali in get_mixed_runs(text):

        font = (
            bengali_font
            if is_bengali
            else latin_font
        )

        bbox = text_bbox_for_run(
            draw,
            run,
            font,
            is_bengali
        )

        height = max(
            height,
            bbox[3] - bbox[1]
        )

    return height


# ============================================================
# DRAW MIXED TEXT
# ============================================================

def draw_mixed_text(
    draw,
    position,
    text,
    bengali_font,
    latin_font,
    fill
):

    x, y = position

    for run, is_bengali in get_mixed_runs(text):

        font = (
            bengali_font
            if is_bengali
            else latin_font
        )

        kwargs = {}

        if features.check("raqm"):

            kwargs["direction"] = "ltr"
            kwargs["language"] = (
                "bn"
                if is_bengali
                else "en"
            )

        draw.text(
            (x, y),
            run,
            font=font,
            fill=fill,
            **kwargs
        )

        bbox = text_bbox_for_run(
            draw,
            run,
            font,
            is_bengali
        )

        x += (
            bbox[2] - bbox[0]
        )

    return x


# ============================================================
# WRAP MIXED TEXT
# ============================================================

def wrap_text(
    draw,
    text,
    bengali_font,
    latin_font,
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

        width = mixed_text_width(
            draw,
            test,
            bengali_font,
            latin_font
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

    return lines


# ============================================================
# GENERIC IMAGE DETECTION
# ============================================================

def is_generic_image(url):

    if not url:
        return True

    lower = url.lower()

    # IMPORTANT:
    # social_share and share-image are intentionally NOT
    # considered generic because TBS can use them for real
    # article photos.

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

    return any(
        pattern in lower
        for pattern in bad_patterns
    )


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(url):

    if not url:
        return None

    try:

        print(
            f"Downloading image: {url}"
        )

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
            io.BytesIO(
                response.content
            )
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
        # OpenGraph
        # ----------------------------------------------------

        og = soup.find(
            "meta",
            property="og:image"
        )

        if (
            og
            and og.get("content")
        ):

            image_url = urljoin(
                article_url,
                og["content"].strip()
            )

            if not is_generic_image(
                image_url
            ):

                print(
                    f"✓ Found og:image: "
                    f"{image_url}"
                )

                return image_url

        # ----------------------------------------------------
        # Twitter
        # ----------------------------------------------------

        twitter = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        )

        if (
            twitter
            and twitter.get("content")
        ):

            image_url = urljoin(
                article_url,
                twitter["content"].strip()
            )

            if not is_generic_image(
                image_url
            ):

                print(
                    f"✓ Found twitter:image: "
                    f"{image_url}"
                )

                return image_url

        # ----------------------------------------------------
        # JSON-LD
        # ----------------------------------------------------

        for script in soup.find_all(
            "script",
            type="application/ld+json"
        ):

            try:

                raw = (
                    script.string
                    or script.get_text()
                )

                if not raw.strip():
                    continue

                data = json.loads(raw)

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

                    image = obj.get(
                        "image"
                    )

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

                    elif isinstance(
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

                    elif isinstance(
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
# RESOLVE ARTICLE IMAGE
# ============================================================

def resolve_article_image(
    stored_image,
    article_url
):

    # FIRST:
    # Try the stored image.
    #
    # This is important for TBS social_share images.

    if stored_image:

        print(
            f"Stored image: {stored_image}"
        )

        if not is_generic_image(
            stored_image
        ):

            print(
                "Stored image appears to be "
                "an article image."
            )

            image = download_image(
                stored_image
            )

            if image is not None:

                return image

            print(
                "Stored image download failed."
            )

        else:

            print(
                "⚠ Stored image looks like "
                "banner/logo/default."
            )

    # SECOND:
    # Search article page metadata.

    actual_url = extract_article_image(
        article_url
    )

    if actual_url:

        image = download_image(
            actual_url
        )

        if image is not None:

            return image

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

        # ----------------------------------------------------
        # Load BOTH font families.
        # ----------------------------------------------------

        title_bengali_font = get_font(
            58,
            bold=True,
            bengali=True
        )

        title_latin_font = get_font(
            58,
            bold=True,
            bengali=False
        )

        source_bengali_font = get_font(
            28,
            bold=True,
            bengali=True
        )

        source_latin_font = get_font(
            28,
            bold=True,
            bengali=False
        )

        # ----------------------------------------------------
        # Prepare image
        # ----------------------------------------------------

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
        # Background
        # ----------------------------------------------------

        background = image.copy()

        background = background.filter(
            ImageFilter.GaussianBlur(8)
        )

        dark_overlay = Image.new(
            "RGBA",
            background.size,
            (0, 0, 0, 65)
        )

        background = Image.alpha_composite(
            background.convert("RGBA"),
            dark_overlay
        )

        card = background.convert(
            "RGBA"
        )

        # Original article image
        card.alpha_composite(
            image.convert("RGBA")
        )

        # ----------------------------------------------------
        # Top gradient
        # ----------------------------------------------------

        top_gradient = Image.new(
            "RGBA",
            card.size,
            (0, 0, 0, 0)
        )

        gd = ImageDraw.Draw(
            top_gradient
        )

        for y in range(500):

            alpha = int(
                150 * (
                    1 - y / 500
                )
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
            top_gradient
        )

        # ----------------------------------------------------
        # Bottom gradient
        # ----------------------------------------------------

        bottom_gradient = Image.new(
            "RGBA",
            card.size,
            (0, 0, 0, 0)
        )

        gd2 = ImageDraw.Draw(
            bottom_gradient
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
            bottom_gradient
        )

        draw = ImageDraw.Draw(
            card
        )

        # ----------------------------------------------------
        # SOURCE BADGE
        # ----------------------------------------------------

        badge_text = source

        text_width = mixed_text_width(
            draw,
            badge_text,
            source_bengali_font,
            source_latin_font
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

        draw_mixed_text(
            draw,
            (
                badge_x + 22,
                badge_y + 8
            ),
            badge_text,
            source_bengali_font,
            source_latin_font,
            (
                20,
                20,
                20,
                255
            )
        )

        # ----------------------------------------------------
        # TITLE WRAPPING
        # ----------------------------------------------------

        max_width = 1050

        lines = wrap_text(
            draw,
            title,
            title_bengali_font,
            title_latin_font,
            max_width
        )

        max_lines = 5

        if len(lines) > max_lines:

            lines = lines[:max_lines]

            last = lines[-1]

            while last:

                test = last + "..."

                width = mixed_text_width(
                    draw,
                    test,
                    title_bengali_font,
                    title_latin_font
                )

                if width <= max_width:

                    lines[-1] = test

                    break

                last = last[:-1]

        # ----------------------------------------------------
        # TITLE HEIGHT
        # ----------------------------------------------------

        line_spacing = 12

        heights = []

        for line in lines:

            height = mixed_text_height(
                draw,
                line,
                title_bengali_font,
                title_latin_font
            )

            heights.append(
                height
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

        # ----------------------------------------------------
        # TITLE SHADOW + TITLE
        # ----------------------------------------------------

        for line, height in zip(
            lines,
            heights
        ):

            # Shadow
            draw_mixed_text(
                draw,
                (
                    63,
                    y + 4
                ),
                line,
                title_bengali_font,
                title_latin_font,
                (
                    0,
                    0,
                    0,
                    190
                )
            )

            # Main title
            draw_mixed_text(
                draw,
                (
                    60,
                    y
                ),
                line,
                title_bengali_font,
                title_latin_font,
                (
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
        # EXPORT
        # ----------------------------------------------------

        output = io.BytesIO()

        card.convert(
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

    # ONLY title + article URL.
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

        if (
            response.ok
            and data.get("id")
        ):

            return (
                data["id"],
                None
            )

        return (
            None,
            data.get(
                "error",
                data
            )
        )

    except Exception as e:

        return (
            None,
            str(e)
        )


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

    verify_text_rendering_support()

    # --------------------------------------------------------
    # Get unposted news
    # --------------------------------------------------------

    news = get_unposted_news()

    print(
        f"Found {len(news)} news."
    )

    posted_count = 0

    # --------------------------------------------------------
    # Process articles
    # --------------------------------------------------------

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

            # ------------------------------------------------
            # IMAGE
            # ------------------------------------------------

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

            # ------------------------------------------------
            # PHOTO CARD
            # ------------------------------------------------

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

            # ------------------------------------------------
            # FACEBOOK
            # ------------------------------------------------

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

    # --------------------------------------------------------
    # FINISHED
    # --------------------------------------------------------

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
