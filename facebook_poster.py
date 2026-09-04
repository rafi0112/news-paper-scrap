
import io
import json
import subprocess
import requests

from datetime import datetime
from urllib.parse import urljoin
import re
from PIL import Image, ImageDraw, ImageFont, features
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

REQUEST_TIMEOUT = 25

# Maximum description/excerpt length in the Facebook caption.
# This keeps the post concise instead of copying the full article.
DESCRIPTION_MAX_CHARS = int(
    os.getenv("DESCRIPTION_MAX_CHARS", "300")
)

# ------------------------------------------------------------
# Card layout constants (the "photo card" look)
# ------------------------------------------------------------

CARD_WIDTH = 1200

# The photo sits below the header, cropped to a square.
PHOTO_SIZE = 1200

SIDE_MARGIN = 64
TOP_MARGIN = 56

HEADLINE_FONT_SIZE = 56
HEADLINE_LINE_SPACING = 12
HEADLINE_MAX_LINES = 4

# Vertical highlighter padding around the highlighted text
HIGHLIGHT_PAD_X = 10
HIGHLIGHT_PAD_TOP = 6
HIGHLIGHT_PAD_BOTTOM = 12

GAP_AFTER_HEADLINE = 22

SOURCE_FONT_SIZE = 24
GAP_AFTER_SOURCE = 34

# Brand accent used for the headline highlight + logo mark.
ACCENT_COLOR = (196, 44, 44)

WHITE = (255, 255, 255)
BLACK = (20, 20, 20)
GRAY = (120, 120, 120)

# Fraction of the headline (by word count) that gets the red
# highlight treatment, read left-to-right from the first word.
# Tune with HIGHLIGHT_WORD_RATIO in the environment if needed.
HIGHLIGHT_WORD_RATIO = float(
    os.getenv("HIGHLIGHT_WORD_RATIO", "0.65")
)

# Small watermark drawn in the bottom-right corner of the photo.
BRAND_MARK = os.getenv("BRAND_MARK", "TN")


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
# WRAP MIXED TEXT (word-aware, keeps word boundaries so we can
# later figure out which words fall in the "highlighted" prefix)
# ============================================================

def wrap_text_words(
    draw,
    text,
    bengali_font,
    latin_font,
    max_width
):
    """
    Same wrapping behaviour as before, but returns a list of
    *word lists* (one list per line) instead of joined strings,
    so the caller can re-associate each word with its global
    index in the headline.
    """

    words = text.split()

    lines = []
    current_words = []

    for word in words:

        test_words = current_words + [word]

        test = " ".join(test_words)

        width = mixed_text_width(
            draw,
            test,
            bengali_font,
            latin_font
        )

        if width <= max_width or not current_words:

            current_words = test_words

        else:

            lines.append(current_words)

            current_words = [word]

    if current_words:

        lines.append(current_words)

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
# WEBSITE DESCRIPTION / SHORT EXCERPT
# ============================================================

def clean_description(text):
    """
    Clean a website description/excerpt and keep it short.
    """

    if not text:
        return ""

    text = re.sub(
        r"\s+",
        " ",
        str(text)
    ).strip()

    text = text.strip(
        " \t\r\n\"'“”‘’"
    )

    if not text:
        return ""

    if len(text) <= DESCRIPTION_MAX_CHARS:
        return text

    shortened = text[
        :DESCRIPTION_MAX_CHARS
    ].rsplit(" ", 1)[0].strip()

    if not shortened:
        shortened = text[
            :DESCRIPTION_MAX_CHARS
        ].strip()

    return shortened + "…"


def extract_website_description(article_url):
    """
    Extract a short description from the article page.

    Priority:
      1. meta[name='description']
      2. og:description
      3. twitter:description
      4. first meaningful article paragraph
    """

    if not article_url:
        return ""

    try:

        print(
            "Opening article page to find "
            "website description..."
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
        # Standard meta description
        # ----------------------------------------------------

        meta = soup.find(
            "meta",
            attrs={
                "name": "description"
            }
        )

        if meta and meta.get("content"):

            description = clean_description(
                meta["content"]
            )

            if description:

                print(
                    "✓ Website description found "
                    "from meta description"
                )

                return description

        # ----------------------------------------------------
        # OpenGraph description
        # ----------------------------------------------------

        og = soup.find(
            "meta",
            property="og:description"
        )

        if og and og.get("content"):

            description = clean_description(
                og["content"]
            )

            if description:

                print(
                    "✓ Website description found "
                    "from og:description"
                )

                return description

        # ----------------------------------------------------
        # Twitter description
        # ----------------------------------------------------

        twitter = soup.find(
            "meta",
            attrs={
                "name": "twitter:description"
            }
        )

        if twitter and twitter.get("content"):

            description = clean_description(
                twitter["content"]
            )

            if description:

                print(
                    "✓ Website description found "
                    "from twitter:description"
                )

                return description

        # ----------------------------------------------------
        # Fallback: first meaningful article paragraph
        # ----------------------------------------------------

        selectors = [
            "article p",
            "[itemprop='articleBody'] p",
            ".article-body p",
            ".article-content p",
            ".story-body p",
            ".story-content p",
            "main p",
        ]

        for selector in selectors:

            for paragraph in soup.select(
                selector
            ):

                text = paragraph.get_text(
                    " ",
                    strip=True
                )

                text = clean_description(
                    text
                )

                # Ignore very short UI labels/captions.
                if len(text) >= 40:

                    print(
                        "✓ Website description found "
                        "from first article paragraph"
                    )

                    return text

        print(
            "⚠ No website description found."
        )

        return ""

    except Exception as e:

        print(
            f"⚠ Description extraction failed: {e}"
        )

        return ""


def get_article_description(
    stored_description,
    article_url
):
    """
    Prefer the description already stored in Supabase.
    If it is missing, fetch it from the article page.
    """

    description = clean_description(
        stored_description
    )

    if description:

        print(
            f"Stored description: {description}"
        )

        return description

    return extract_website_description(
        article_url
    )


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
# DATE FORMATTING
# ============================================================

def format_display_date(published_at):
    """
    Turns a Supabase timestamp (ISO 8601, e.g.
    '2026-09-03T10:15:00+00:00') into the display form used on
    the card, e.g. '3 SEPTEMBER 2026'.

    Falls back to today's date if parsing fails or the value is
    missing.
    """

    dt = None

    if published_at:

        try:

            cleaned = published_at.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)

        except Exception:

            dt = None

    if dt is None:
        dt = datetime.utcnow()

    return f"{dt.day} {dt.strftime('%B %Y')}".upper()


# ============================================================
# HEADLINE HIGHLIGHT SPLIT
# ============================================================

def build_highlight_flags(total_words, ratio):
    """
    Returns the number of leading words (out of total_words)
    that should get the red-highlight treatment.
    """

    if total_words <= 0:
        return 0

    count = round(total_words * ratio)

    return max(1, min(total_words, count))


# ============================================================
# DRAW ONE HEADLINE LINE (mixes highlighted + plain segments)
# ============================================================

def draw_headline_line(
    draw,
    words,
    global_start_index,
    highlight_count,
    x,
    y,
    line_height,
    bengali_font,
    latin_font
):
    """
    Draws a single wrapped headline line, switching between a
    red-highlighted run (white text on a red box) and plain
    black text, based on each word's position in the overall
    headline.
    """

    space_width = mixed_text_width(
        draw, " ", bengali_font, latin_font
    ) or 12

    # Group consecutive words that share the same highlight
    # state into segments so each segment is drawn (and boxed)
    # as one continuous run.
    segments = []

    for i, word in enumerate(words):

        is_highlighted = (
            (global_start_index + i) < highlight_count
        )

        if segments and segments[-1][0] == is_highlighted:

            segments[-1][1].append(word)

        else:

            segments.append([is_highlighted, [word]])

    cursor_x = x

    for is_highlighted, seg_words in segments:

        seg_text = " ".join(seg_words)

        seg_width = mixed_text_width(
            draw, seg_text, bengali_font, latin_font
        )

        if is_highlighted:

            draw.rectangle(
                (
                    cursor_x - HIGHLIGHT_PAD_X,
                    y - HIGHLIGHT_PAD_TOP,
                    cursor_x + seg_width + HIGHLIGHT_PAD_X,
                    y + line_height + HIGHLIGHT_PAD_BOTTOM,
                ),
                fill=ACCENT_COLOR,
            )

            text_color = WHITE

        else:

            text_color = BLACK

        draw_mixed_text(
            draw,
            (cursor_x, y),
            seg_text,
            bengali_font,
            latin_font,
            text_color,
        )

        cursor_x += seg_width + space_width


# ============================================================
# CREATE PHOTO CARD (white header + red-highlight headline
# + source/date line + plain square photo + logo mark)
# ============================================================

def create_photo_card(
    image,
    title,
    source,
    published_at=None
):
    """
    Premium editorial-style Facebook photo card.

    Layout:
      - clean warm-white editorial header
      - subtle red premium accent
      - small source/date metadata
      - original article photo, edge-to-edge
      - dark cinematic photo treatment near the bottom
      - elegant TN brand mark
      - mixed Bengali + English typography

    The actual article image is kept as the visual foundation.
    """

    try:

        # ----------------------------------------------------
        # Fonts
        # ----------------------------------------------------

        headline_bengali_font = get_font(
            HEADLINE_FONT_SIZE,
            bold=True,
            bengali=True
        )

        headline_latin_font = get_font(
            HEADLINE_FONT_SIZE,
            bold=True,
            bengali=False
        )

        source_bengali_font = get_font(
            SOURCE_FONT_SIZE,
            bold=True,
            bengali=True
        )

        source_latin_font = get_font(
            SOURCE_FONT_SIZE,
            bold=True,
            bengali=False
        )

        small_latin_font = get_font(
            19,
            bold=False,
            bengali=False
        )

        brand_font = get_font(
            32,
            bold=True,
            bengali=False
        )

        # ----------------------------------------------------
        # Measurement canvas
        # ----------------------------------------------------

        measure_img = Image.new(
            "RGB",
            (CARD_WIDTH, 10),
            WHITE
        )

        measure_draw = ImageDraw.Draw(
            measure_img
        )

        max_text_width = (
            CARD_WIDTH
            - (2 * SIDE_MARGIN)
        )

        # ----------------------------------------------------
        # Headline wrapping
        # ----------------------------------------------------

        line_word_lists = wrap_text_words(
            measure_draw,
            title,
            headline_bengali_font,
            headline_latin_font,
            max_text_width
        )

        truncated = False

        if len(line_word_lists) > HEADLINE_MAX_LINES:

            line_word_lists = (
                line_word_lists[
                    :HEADLINE_MAX_LINES
                ]
            )

            truncated = True

        if truncated and line_word_lists:

            last_line = line_word_lists[-1]

            if last_line:

                last_line[-1] = (
                    last_line[-1]
                    + "..."
                )

        total_words = sum(
            len(words)
            for words in line_word_lists
        )

        highlight_count = (
            build_highlight_flags(
                total_words,
                HIGHLIGHT_WORD_RATIO
            )
        )

        line_heights = [
            mixed_text_height(
                measure_draw,
                " ".join(words),
                headline_bengali_font,
                headline_latin_font
            )
            for words in line_word_lists
        ]

        headline_block_height = (
            sum(line_heights)
            + HEADLINE_LINE_SPACING
            * max(
                0,
                len(line_word_lists) - 1
            )
        )

        # ----------------------------------------------------
        # Metadata
        # ----------------------------------------------------

        source_text = (
            (source or "")
            .strip()
            .upper()
        )

        date_text = format_display_date(
            published_at
        )

        source_line = (
            f"{source_text}  •  {date_text}"
        )

        source_line_height = (
            mixed_text_height(
                measure_draw,
                source_line,
                source_bengali_font,
                source_latin_font
            )
        )

        # ----------------------------------------------------
        # Premium header sizing
        # ----------------------------------------------------

        accent_bar_height = 7

        header_height = (
            TOP_MARGIN
            + 18
            + headline_block_height
            + GAP_AFTER_HEADLINE
            + source_line_height
            + GAP_AFTER_SOURCE
            + 18
        )

        photo_height = PHOTO_SIZE

        card_height = (
            header_height
            + photo_height
        )

        # ----------------------------------------------------
        # Premium white editorial canvas
        # ----------------------------------------------------

        card = Image.new(
            "RGB",
            (
                CARD_WIDTH,
                int(card_height)
            ),
            (250, 249, 247)
        )

        draw = ImageDraw.Draw(card)

        # ----------------------------------------------------
        # Very subtle top accent
        # ----------------------------------------------------

        draw.rectangle(
            (
                0,
                0,
                CARD_WIDTH,
                accent_bar_height
            ),
            fill=ACCENT_COLOR
        )

        # Small editorial label
        label_font = get_font(
            18,
            bold=True,
            bengali=False
        )

        label_text = "LATEST NEWS"

        draw.text(
            (
                SIDE_MARGIN,
                TOP_MARGIN
            ),
            label_text,
            font=label_font,
            fill=(
                150,
                150,
                150
            )
        )

        # ----------------------------------------------------
        # Headline
        # ----------------------------------------------------

        y = (
            TOP_MARGIN
            + 34
        )

        global_index = 0

        for words, height in zip(
            line_word_lists,
            line_heights
        ):

            draw_headline_line(
                draw,
                words,
                global_index,
                highlight_count,
                SIDE_MARGIN,
                y,
                height,
                headline_bengali_font,
                headline_latin_font
            )

            global_index += len(words)

            y += (
                height
                + HEADLINE_LINE_SPACING
            )

        # ----------------------------------------------------
        # Thin editorial divider
        # ----------------------------------------------------

        divider_y = (
            y
            + 2
        )

        draw.line(
            (
                SIDE_MARGIN,
                divider_y,
                CARD_WIDTH - SIDE_MARGIN,
                divider_y
            ),
            fill=(
                220,
                220,
                220
            ),
            width=2
        )

        # ----------------------------------------------------
        # Source/date metadata
        # ----------------------------------------------------

        metadata_y = (
            divider_y
            + 22
        )

        draw_mixed_text(
            draw,
            (
                SIDE_MARGIN,
                metadata_y
            ),
            source_line,
            source_bengali_font,
            source_latin_font,
            (
                105,
                105,
                105
            )
        )

        # ----------------------------------------------------
        # Small red accent dot
        # ----------------------------------------------------

        dot_x = (
            CARD_WIDTH
            - SIDE_MARGIN
            - 10
        )

        dot_y = (
            metadata_y
            + max(
                10,
                source_line_height // 2
            )
        )

        draw.ellipse(
            (
                dot_x - 6,
                dot_y - 6,
                dot_x + 6,
                dot_y + 6
            ),
            fill=ACCENT_COLOR
        )

        # ----------------------------------------------------
        # Photo
        # ----------------------------------------------------

        photo = crop_to_square(
            image
        )

        photo = photo.resize(
            (
                PHOTO_SIZE,
                PHOTO_SIZE
            ),
            Image.Resampling.LANCZOS
        )

        photo_y = int(
            header_height
        )

        card.paste(
            photo,
            (
                0,
                photo_y
            )
        )

        # ----------------------------------------------------
        # Premium photo overlay
        #
        # The original image remains underneath.
        # Only subtle gradients are added for readability.
        # ----------------------------------------------------

        overlay = Image.new(
            "RGBA",
            (
                CARD_WIDTH,
                PHOTO_SIZE
            ),
            (
                0,
                0,
                0,
                0
            )
        )

        od = ImageDraw.Draw(
            overlay
        )

        # Top soft vignette
        for i in range(180):

            alpha = int(
                40
                * (
                    1
                    - i / 180
                )
            )

            od.line(
                (
                    0,
                    i,
                    CARD_WIDTH,
                    i
                ),
                fill=(
                    0,
                    0,
                    0,
                    alpha
                )
            )

        # Bottom cinematic gradient
        gradient_start = 720

        for y2 in range(
            gradient_start,
            PHOTO_SIZE
        ):

            progress = (
                y2 - gradient_start
            ) / (
                PHOTO_SIZE
                - gradient_start
            )

            alpha = int(
                8
                + 145 * progress
            )

            od.line(
                (
                    0,
                    y2,
                    CARD_WIDTH,
                    y2
                ),
                fill=(
                    0,
                    0,
                    0,
                    alpha
                )
            )

        card = Image.alpha_composite(
            card.convert("RGBA"),
            Image.new(
                "RGBA",
                (
                    CARD_WIDTH,
                    photo_y
                ),
                (
                    0,
                    0,
                    0,
                    0
                )
            )
        )

        # Re-create composite cleanly so the photo stays untouched.
        base = Image.new(
            "RGBA",
            (
                CARD_WIDTH,
                int(card_height)
            ),
            (
                250,
                249,
                247,
                255
            )
        )

        # Header from original card
        header_crop = card.crop(
            (
                0,
                0,
                CARD_WIDTH,
                photo_y
            )
        )

        base.alpha_composite(
            header_crop,
            (
                0,
                0
            )
        )

        # Original photo
        base.paste(
            photo.convert("RGBA"),
            (
                0,
                photo_y
            )
        )

        # Photo overlay
        base.alpha_composite(
            overlay,
            (
                0,
                photo_y
            )
        )

        draw = ImageDraw.Draw(
            base
        )

        # ----------------------------------------------------
        # Photo top hairline
        # ----------------------------------------------------

        draw.rectangle(
            (
                0,
                photo_y,
                CARD_WIDTH,
                photo_y + 3
            ),
            fill=ACCENT_COLOR
        )

        # ----------------------------------------------------
        # Premium bottom source mark
        # ----------------------------------------------------

        mark_text = (
            BRAND_MARK
            or "TN"
        )

        bbox = draw.textbbox(
            (0, 0),
            mark_text,
            font=brand_font
        )

        mark_w = (
            bbox[2]
            - bbox[0]
        )

        mark_h = (
            bbox[3]
            - bbox[1]
        )

        mark_margin = 34
        mark_pad_x = 18
        mark_pad_y = 12

        badge_x1 = (
            CARD_WIDTH
            - mark_margin
        )

        badge_y1 = (
            photo_y
            + PHOTO_SIZE
            - mark_margin
        )

        badge_x0 = (
            badge_x1
            - mark_w
            - 2 * mark_pad_x
        )

        badge_y0 = (
            badge_y1
            - mark_h
            - 2 * mark_pad_y
        )

        # translucent premium badge
        draw.rounded_rectangle(
            (
                badge_x0,
                badge_y0,
                badge_x1,
                badge_y1
            ),
            radius=14,
            fill=(
                0,
                0,
                0,
                145
            ),
            outline=(
                255,
                255,
                255,
                90
            ),
            width=1
        )

        draw.text(
            (
                badge_x0
                + mark_pad_x,
                badge_y0
                + mark_pad_y
                - 2
            ),
            mark_text,
            font=brand_font,
            fill=WHITE
        )

        # ----------------------------------------------------
        # Tiny editorial line at bottom-left
        # ----------------------------------------------------

        tiny_text = "NEWS • BANGLADESH"

        tiny_bbox = draw.textbbox(
            (0, 0),
            tiny_text,
            font=small_latin_font
        )

        tiny_w = (
            tiny_bbox[2]
            - tiny_bbox[0]
        )

        tiny_h = (
            tiny_bbox[3]
            - tiny_bbox[1]
        )

        tiny_x = 36

        tiny_y = (
            photo_y
            + PHOTO_SIZE
            - 38
            - tiny_h
        )

        # soft translucent background
        draw.rounded_rectangle(
            (
                tiny_x - 12,
                tiny_y - 8,
                tiny_x + tiny_w + 12,
                tiny_y + tiny_h + 8
            ),
            radius=10,
            fill=(
                0,
                0,
                0,
                105
            )
        )

        draw.text(
            (
                tiny_x,
                tiny_y
            ),
            tiny_text,
            font=small_latin_font,
            fill=(
                255,
                255,
                255,
                225
            )
        )

        # ----------------------------------------------------
        # Export
        # ----------------------------------------------------

        output = io.BytesIO()

        base.convert(
            "RGB"
        ).save(
            output,
            format="JPEG",
            quality=95,
            optimize=True
        )

        output.seek(0)

        print(
            "✓ Premium photo card created"
        )

        return output

    except Exception as e:

        print(
            f"✗ Premium photo card creation "
            f"failed: {e}"
        )

        return None


# ============================================================
# FACEBOOK POST
# ============================================================

def post_to_facebook(
    photo_bytes,
    title,
    description,
    article_url
):

    endpoint = (
        f"https://graph.facebook.com/"
        f"{META_GRAPH_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/photos"
    )

    # Facebook caption:
    # exact title + short website description + article URL.
    caption_parts = [
        title.strip()
    ]

    if description:
        caption_parts.append(
            description.strip()
        )

    caption_parts.append(
        article_url.strip()
    )

    caption = "\n\n".join(
        caption_parts
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
            "id,title,source,image,url,description,published_at"
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

        published_at = (
            article.get("published_at")
        )

        stored_description = (
            article.get("description")
            or ""
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
            # WEBSITE DESCRIPTION
            # ------------------------------------------------

            description = get_article_description(
                stored_description,
                article_url
            )

            if description:
                print(
                    f"✓ Description ready: {description}"
                )
            else:
                print(
                    "⚠ No description will be added."
                )

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
                source,
                published_at
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
                    description,
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