import os
import io
import json
import time
import requests

from datetime import datetime, timezone
from urllib.parse import urljoin
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, features
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from supabase import create_client, Client


# ============================================================
# CONFIG
# ============================================================

load_dotenv()


def _clean_env(value):
    """
    Strip accidental quotes/whitespace from .env values.
    This alone fixes a large share of "invalid Facebook token"
    style errors that are really just formatting mistakes.
    """
    if value is None:
        return value
    return value.strip().strip('"').strip("'")


SUPABASE_URL = _clean_env(os.getenv("SUPABASE_URL"))
SUPABASE_KEY = _clean_env(os.getenv("SUPABASE_KEY"))

FACEBOOK_PAGE_ID = _clean_env(os.getenv("FACEBOOK_PAGE_ID"))
FACEBOOK_PAGE_ACCESS_TOKEN = _clean_env(
    os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
)

META_GRAPH_VERSION = _clean_env(
    os.getenv("META_GRAPH_VERSION", "v21.0")
)

MAX_POSTS_PER_RUN = 3
REQUEST_TIMEOUT = 25
FACEBOOK_TIMEOUT = (10, 60)   # (connect, read)
FACEBOOK_MAX_RETRIES = 3

# Facebook caption is generous (~63,000 chars) but we keep it tight
# and readable regardless.
DESCRIPTION_MAX_CHARS = int(os.getenv("DESCRIPTION_MAX_CHARS", "300"))
CAPTION_MAX_CHARS = 4500

# ------------------------------------------------------------
# Card layout constants — modern "full-bleed photo" card
#
# 1080 x 1350 (4:5) is the aspect ratio Facebook/Instagram render
# at full width with NO extra cropping on both mobile and desktop
# feeds, and 1080px is their recommended upload width — so this
# gives the sharpest, most consistent result on every device.
# ------------------------------------------------------------

CARD_WIDTH = 1080
CARD_HEIGHT = 1350

SIDE_MARGIN = 56
TOP_MARGIN = 44
BOTTOM_MARGIN = 52

# Vertical bias used when cropping a photo to fill the frame.
# 0.0 = keep the top of the photo, 1.0 = keep the bottom, 0.5 = dead
# center. The photo always covers the ENTIRE card either way — this
# only controls which part gets trimmed off when the source photo's
# aspect ratio doesn't exactly match the card's. Centered by default
# so the subject of the photo is never pushed toward one edge.
CROP_VERTICAL_BIAS = 0.5

HEADLINE_FONT_SIZE = 66
HEADLINE_MIN_FONT_SIZE = 36
HEADLINE_LINE_SPACING = 14
HEADLINE_MAX_LINES = 4

HIGHLIGHT_PAD_X = 12
HIGHLIGHT_PAD_TOP = 8
HIGHLIGHT_PAD_BOTTOM = 12
HIGHLIGHT_RADIUS = 10

GAP_AFTER_HEADLINE = 22

SOURCE_FONT_SIZE = 26
CREDIT_FONT_SIZE = 18

# How tall the top/bottom dark overlays are allowed to be, as a
# fraction of the full card height, before we force the headline
# font down further so the photo never gets fully swallowed.
MAX_BOTTOM_OVERLAY_RATIO = 0.52
TOP_OVERLAY_HEIGHT = 190

# Accent colors
ACCENT_RED = (196, 44, 44)
HIGHLIGHT_GOLD = (255, 200, 20)
INK_BLACK = (24, 24, 24)
WHITE = (255, 255, 255)
OFF_WHITE = (235, 235, 232)
MUTED_LIGHT = (215, 213, 210)

# Fraction of the headline (by word count) that gets the gold
# highlight treatment, read left-to-right from the first word.
HIGHLIGHT_WORD_RATIO = float(os.getenv("HIGHLIGHT_WORD_RATIO", "0.6"))

# Bottom-left brand wordmark drawn over the photo.
BRAND_MARK = os.getenv("BRAND_MARK", "TN")
BRAND_TAGLINE = os.getenv("BRAND_TAGLINE", "NEWS • BANGLADESH")


# ============================================================
# ENVIRONMENT VALIDATION
# ============================================================

required = {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
    "FACEBOOK_PAGE_ID": FACEBOOK_PAGE_ID,
    "FACEBOOK_PAGE_ACCESS_TOKEN": FACEBOOK_PAGE_ACCESS_TOKEN,
}

missing = [key for key, value in required.items() if not value]

if missing:
    raise RuntimeError(
        "Missing environment variables: " + ", ".join(missing)
    )


# ============================================================
# SUPABASE
# ============================================================

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# HTTP SESSIONS (with retry/backoff so transient network blips
# don't turn into hard failures)
# ============================================================

def _build_session(total_retries=3):
    s = requests.Session()

    retry = Retry(
        total=total_retries,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)

    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
        ),
    })

    return s


session = _build_session()          # for scraping article pages / images
fb_session = _build_session(total_retries=FACEBOOK_MAX_RETRIES)  # for Graph API


# ============================================================
# FONT HELPERS
# ============================================================

def find_font_file(names):
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

    for root in ["/usr/share/fonts", "/usr/local/share/fonts"]:
        if not os.path.exists(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for name in names:
                if name in filenames:
                    return os.path.join(dirpath, name)

    return None


_FONT_CACHE = {}


def get_font(size, bold=False, bengali=False):
    """
    Bengali text -> Noto Sans Bengali
    English/numbers -> DejaVu Sans
    Kept separate so a mixed title never renders missing-glyph boxes.
    Cached so repeated calls (auto-shrink loop) stay fast.
    """

    cache_key = (size, bold, bengali)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]

    if bengali:
        names = (
            ["NotoSansBengali-Bold.ttf", "NotoSansBengaliUI-Bold.ttf"]
            if bold else
            ["NotoSansBengali-Regular.ttf", "NotoSansBengaliUI-Regular.ttf"]
        )
        font_path = find_font_file(names)
        if not font_path:
            raise RuntimeError(
                "Noto Sans Bengali was not found. "
                "Install fonts-noto-core and fonts-noto-extra."
            )
    else:
        names = ["DejaVuSans-Bold.ttf"] if bold else ["DejaVuSans.ttf"]
        font_path = find_font_file(names)
        if not font_path:
            raise RuntimeError("DejaVu Sans was not found.")

    font = ImageFont.truetype(font_path, size)
    _FONT_CACHE[cache_key] = font
    return font


def verify_text_rendering_support():
    try:
        if features.check("raqm"):
            print("✓ Pillow RAQM support: ENABLED")
        else:
            print("⚠ Pillow RAQM support: NOT AVAILABLE")
            print(
                "Bengali rendering may be imperfect. "
                "Install libraqm-dev before installing Pillow."
            )
    except Exception as e:
        print(f"⚠ Could not check RAQM support: {e}")


# ============================================================
# MIXED BENGALI/LATIN TEXT RUNS, MEASUREMENT, DRAWING, WRAPPING
# ============================================================

def get_mixed_runs(text):
    if not text:
        return []

    runs = []
    current = ""
    current_is_bengali = None

    for char in text:
        is_bengali = "\u0980" <= char <= "\u09FF"

        if current_is_bengali is None:
            current = char
            current_is_bengali = is_bengali
        elif is_bengali == current_is_bengali:
            current += char
        else:
            runs.append((current, current_is_bengali))
            current = char
            current_is_bengali = is_bengali

    if current:
        runs.append((current, current_is_bengali))

    return runs


def text_bbox_for_run(draw, text, font, is_bengali):
    kwargs = {}
    if features.check("raqm"):
        kwargs["direction"] = "ltr"
        kwargs["language"] = "bn" if is_bengali else "en"
    return draw.textbbox((0, 0), text, font=font, **kwargs)


def mixed_text_width(draw, text, bengali_font, latin_font):
    total_width = 0
    for run, is_bengali in get_mixed_runs(text):
        font = bengali_font if is_bengali else latin_font
        bbox = text_bbox_for_run(draw, run, font, is_bengali)
        total_width += (bbox[2] - bbox[0])
    return total_width


def mixed_text_height(draw, text, bengali_font, latin_font):
    height = 0
    for run, is_bengali in get_mixed_runs(text):
        font = bengali_font if is_bengali else latin_font
        bbox = text_bbox_for_run(draw, run, font, is_bengali)
        height = max(height, bbox[3] - bbox[1])
    return height


def draw_mixed_text(draw, position, text, bengali_font, latin_font, fill):
    x, y = position
    for run, is_bengali in get_mixed_runs(text):
        font = bengali_font if is_bengali else latin_font
        kwargs = {}
        if features.check("raqm"):
            kwargs["direction"] = "ltr"
            kwargs["language"] = "bn" if is_bengali else "en"

        draw.text((x, y), run, font=font, fill=fill, **kwargs)
        bbox = text_bbox_for_run(draw, run, font, is_bengali)
        x += (bbox[2] - bbox[0])
    return x


def wrap_text_words(draw, text, bengali_font, latin_font, max_width):
    """
    Word-aware wrap that returns a list of word-lists (one per line)
    so highlight boundaries can be re-associated with global word index.
    """
    words = text.split()
    lines = []
    current_words = []

    for word in words:
        test_words = current_words + [word]
        width = mixed_text_width(
            draw, " ".join(test_words), bengali_font, latin_font
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

    bad_patterns = [
        "banner.png", "banner.jpg", "banner.jpeg",
        "/logo.", "logo.png", "logo.jpg", "logo.jpeg",
        "default.jpg", "default.png", "default.jpeg",
        "placeholder", "og-default", "fallback",
        "avatar", "/icon.", "icon.png", "icon.jpg",
    ]

    return any(pattern in lower for pattern in bad_patterns)


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(url):
    if not url:
        return None

    try:
        print(f"Downloading image: {url}")

        response = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()

        if (
            not content_type.startswith("image/")
            and not url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
        ):
            print(f"✗ Not an image response: {content_type}")
            return None

        image = Image.open(io.BytesIO(response.content))
        image.load()

        print(f"✓ Image downloaded ({image.width}, {image.height})")
        return image.convert("RGB")

    except Exception as e:
        print(f"✗ Image download failed: {e}")
        return None


# ============================================================
# WEBSITE DESCRIPTION / SHORT EXCERPT
# ============================================================

def clean_description(text):
    if not text:
        return ""

    text = re.sub(r"\s+", " ", str(text)).strip()
    text = text.strip(" \t\r\n\"'\u201c\u201d\u2018\u2019")

    if not text:
        return ""

    if len(text) <= DESCRIPTION_MAX_CHARS:
        return text

    shortened = text[:DESCRIPTION_MAX_CHARS].rsplit(" ", 1)[0].strip()
    if not shortened:
        shortened = text[:DESCRIPTION_MAX_CHARS].strip()

    return shortened + "…"


def extract_website_description(article_url):
    if not article_url:
        return ""

    try:
        print("Opening article page to find website description...")
        response = session.get(article_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            description = clean_description(meta["content"])
            if description:
                print("✓ Website description found from meta description")
                return description

        og = soup.find("meta", property="og:description")
        if og and og.get("content"):
            description = clean_description(og["content"])
            if description:
                print("✓ Website description found from og:description")
                return description

        twitter = soup.find("meta", attrs={"name": "twitter:description"})
        if twitter and twitter.get("content"):
            description = clean_description(twitter["content"])
            if description:
                print("✓ Website description found from twitter:description")
                return description

        selectors = [
            "article p", "[itemprop='articleBody'] p", ".article-body p",
            ".article-content p", ".story-body p", ".story-content p", "main p",
        ]

        for selector in selectors:
            for paragraph in soup.select(selector):
                text = paragraph.get_text(" ", strip=True)
                text = clean_description(text)
                if len(text) >= 40:
                    print("✓ Website description found from first article paragraph")
                    return text

        print("⚠ No website description found.")
        return ""

    except Exception as e:
        print(f"⚠ Description extraction failed: {e}")
        return ""


def get_article_description(stored_description, article_url):
    description = clean_description(stored_description)
    if description:
        print(f"Stored description: {description}")
        return description
    return extract_website_description(article_url)


# ============================================================
# ARTICLE IMAGE EXTRACTION
# ============================================================

def extract_article_image(article_url):
    if not article_url:
        return None

    try:
        print("Opening article page to find actual article image...")
        response = session.get(article_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            image_url = urljoin(article_url, og["content"].strip())
            if not is_generic_image(image_url):
                print(f"✓ Found og:image: {image_url}")
                return image_url

        twitter = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter and twitter.get("content"):
            image_url = urljoin(article_url, twitter["content"].strip())
            if not is_generic_image(image_url):
                print(f"✓ Found twitter:image: {image_url}")
                return image_url

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string or script.get_text()
                if not raw.strip():
                    continue

                data = json.loads(raw)
                objects = data if isinstance(data, list) else [data]

                for obj in objects:
                    if not isinstance(obj, dict):
                        continue

                    image = obj.get("image")

                    if isinstance(image, str):
                        image_url = urljoin(article_url, image)
                        if not is_generic_image(image_url):
                            print("✓ Found JSON-LD image")
                            return image_url

                    elif isinstance(image, dict):
                        image_url = image.get("url")
                        if image_url:
                            image_url = urljoin(article_url, image_url)
                            if not is_generic_image(image_url):
                                print("✓ Found JSON-LD image")
                                return image_url

                    elif isinstance(image, list):
                        for item in image:
                            if isinstance(item, str):
                                image_url = urljoin(article_url, item)
                                if not is_generic_image(image_url):
                                    print("✓ Found JSON-LD image")
                                    return image_url

            except Exception:
                continue

        print("✗ Could not find actual article image.")
        return None

    except Exception as e:
        print(f"✗ Article page image extraction failed: {e}")
        return None


def resolve_article_image(stored_image, article_url):
    if stored_image:
        print(f"Stored image: {stored_image}")

        if not is_generic_image(stored_image):
            print("Stored image appears to be an article image.")
            image = download_image(stored_image)
            if image is not None:
                return image
            print("Stored image download failed.")
        else:
            print("⚠ Stored image looks like banner/logo/default.")

    actual_url = extract_article_image(article_url)
    if actual_url:
        image = download_image(actual_url)
        if image is not None:
            return image

    print("✗ No usable article image found.")
    return None


# ============================================================
# FULL-BLEED, COVER-CROP IMAGE PLACEMENT
#
# The whole card IS the photo — no letterbox bars, no blurred
# filler. The image is scaled up and cropped just enough to fill
# the entire CARD_WIDTH x CARD_HEIGHT frame edge-to-edge, centered
# so the photo is evenly covered top-to-bottom and side-to-side
# instead of being pushed toward one edge. Headline + meta are then
# overlaid on top with dark gradient scrims for legibility.
# ============================================================

def cover_crop_to_canvas(image, target_w, target_h, vertical_bias=CROP_VERTICAL_BIAS):
    img_ratio = image.width / image.height
    target_ratio = target_w / target_h

    if img_ratio > target_ratio:
        # Image is relatively wider than target -> match height, crop sides
        new_h = target_h
        new_w = max(target_w, round(target_h * img_ratio))
    else:
        # Image is relatively taller than target -> match width, crop top/bottom
        new_w = target_w
        new_h = max(target_h, round(target_w / img_ratio))

    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    max_x = new_w - target_w
    max_y = new_h - target_h

    left = max_x // 2
    top = round(max_y * vertical_bias)
    top = max(0, min(top, max_y))

    return resized.crop((left, top, left + target_w, top + target_h))


def make_vertical_gradient(width, height, top_alpha, bottom_alpha, color=(0, 0, 0)):
    """
    A simple RGBA gradient strip, `height` tall, fading from
    top_alpha to bottom_alpha (0-255). Composited straight onto the
    photo — this is what makes overlaid text readable on any image.
    """
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gradient)

    for i in range(height):
        t = i / max(1, height - 1)
        alpha = int(top_alpha + (bottom_alpha - top_alpha) * t)
        gd.line((0, i, width, i), fill=(*color, alpha))

    return gradient


# ============================================================
# DATE FORMATTING
# ============================================================

def format_display_date(published_at):
    dt = None

    if published_at:
        try:
            cleaned = published_at.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
        except Exception:
            dt = None

    if dt is None:
        dt = datetime.now(timezone.utc)

    return f"{dt.day} {dt.strftime('%B %Y')}".upper()


# ============================================================
# HEADLINE HIGHLIGHT SPLIT
# ============================================================

def build_highlight_flags(total_words, ratio):
    if total_words <= 0:
        return 0
    count = round(total_words * ratio)
    return max(1, min(total_words, count))


# ============================================================
# SMALL UI HELPERS (pill badges)
# ============================================================

def draw_pill(draw, xy, text, font, fg, bg, pad_x=16, pad_y=8):
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    draw.rounded_rectangle(
        (x, y, x + w + 2 * pad_x, y + h + 2 * pad_y),
        radius=(h + 2 * pad_y) // 2,
        fill=bg,
    )

    draw.text((x + pad_x, y + pad_y - bbox[1]), text, font=font, fill=fg)

    return w + 2 * pad_x, h + 2 * pad_y


# ============================================================
# DRAW ONE HEADLINE LINE (gold-highlighted + plain segments)
# ============================================================

def draw_headline_line(
    draw, words, global_start_index, highlight_count,
    x, y, line_height, bengali_font, latin_font, base_color,
):
    space_width = mixed_text_width(draw, " ", bengali_font, latin_font) or 14

    segments = []
    for i, word in enumerate(words):
        is_highlighted = (global_start_index + i) < highlight_count
        if segments and segments[-1][0] == is_highlighted:
            segments[-1][1].append(word)
        else:
            segments.append([is_highlighted, [word]])

    cursor_x = x

    for is_highlighted, seg_words in segments:
        seg_text = " ".join(seg_words)
        seg_width = mixed_text_width(draw, seg_text, bengali_font, latin_font)

        if is_highlighted:
            draw.rounded_rectangle(
                (
                    cursor_x - HIGHLIGHT_PAD_X,
                    y - HIGHLIGHT_PAD_TOP,
                    cursor_x + seg_width + HIGHLIGHT_PAD_X,
                    y + line_height + HIGHLIGHT_PAD_BOTTOM,
                ),
                radius=HIGHLIGHT_RADIUS,
                fill=HIGHLIGHT_GOLD,
            )
            text_color = INK_BLACK
        else:
            text_color = base_color

        draw_mixed_text(draw, (cursor_x, y), seg_text, bengali_font, latin_font, text_color)
        cursor_x += seg_width + space_width


# ============================================================
# HEADLINE FIT (auto-shrinks font until it fits both the line
# count AND the available vertical space over the photo)
# ============================================================

def fit_headline(measure_draw, title, max_text_width, max_block_height):
    font_size = HEADLINE_FONT_SIZE

    while True:
        bengali_font = get_font(font_size, bold=True, bengali=True)
        latin_font = get_font(font_size, bold=True, bengali=False)

        line_word_lists = wrap_text_words(
            measure_draw, title, bengali_font, latin_font, max_text_width
        )

        line_heights = [
            mixed_text_height(
                measure_draw, " ".join(words), bengali_font, latin_font
            )
            for words in line_word_lists
        ]

        block_height = (
            sum(line_heights)
            + HEADLINE_LINE_SPACING * max(0, len(line_word_lists) - 1)
        )

        fits_lines = len(line_word_lists) <= HEADLINE_MAX_LINES
        fits_height = block_height <= max_block_height

        if (fits_lines and fits_height) or font_size <= HEADLINE_MIN_FONT_SIZE:
            break

        font_size -= 3

    truncated = False
    if len(line_word_lists) > HEADLINE_MAX_LINES:
        line_word_lists = line_word_lists[:HEADLINE_MAX_LINES]
        truncated = True

    if truncated and line_word_lists and line_word_lists[-1]:
        line_word_lists[-1][-1] = line_word_lists[-1][-1] + "…"
        line_heights = line_heights[:HEADLINE_MAX_LINES]

    return line_word_lists, line_heights, bengali_font, latin_font


# ============================================================
# CREATE PHOTO CARD — modern, full-bleed editorial design
# ============================================================

def create_photo_card(image, title, source, published_at=None):
    """
    Modern, full-bleed Facebook photo card:
      - the article photo fills the ENTIRE 1080x1350 card, cropped
        (never letterboxed/blurred) to cover the whole frame — this
        is the part that was previously "sitting" inside a smaller
        boxed-in area and is now the whole card
      - a soft dark gradient at the top holds a red "LATEST NEWS"
        pill + date, and the brand wordmark
      - a taller dark gradient at the bottom holds the bold white
        headline (with a gold highlighted lead-in phrase) and the
        source/date meta line, sized to auto-fit any headline length
      - renders crisp at 1080px width, Facebook/Instagram's own
        recommended size, so it looks sharp on both mobile and
        desktop feeds without any extra platform-side cropping
    """

    try:
        source_bengali_font = get_font(SOURCE_FONT_SIZE, bold=True, bengali=True)
        source_latin_font = get_font(SOURCE_FONT_SIZE, bold=True, bengali=False)
        credit_font = get_font(CREDIT_FONT_SIZE, bold=False, bengali=False)
        brand_font = get_font(32, bold=True, bengali=False)
        tagline_font = get_font(17, bold=False, bengali=False)
        pill_font = get_font(20, bold=True, bengali=False)
        date_font = get_font(20, bold=True, bengali=False)

        measure_img = Image.new("RGB", (CARD_WIDTH, 10), (0, 0, 0))
        measure_draw = ImageDraw.Draw(measure_img)

        max_text_width = CARD_WIDTH - (2 * SIDE_MARGIN)

        # ---------------- Headline (auto-fit to available space) ----------------

        max_bottom_overlay_height = CARD_HEIGHT * MAX_BOTTOM_OVERLAY_RATIO
        # Reserve room for meta line + paddings before computing the
        # budget left for the headline block itself.
        source_line_probe_height = mixed_text_height(
            measure_draw, "Ag", source_bengali_font, source_latin_font
        )
        reserved_for_chrome = (
            BOTTOM_MARGIN + source_line_probe_height + GAP_AFTER_HEADLINE + 24
        )
        max_headline_block_height = max(
            120, max_bottom_overlay_height - reserved_for_chrome
        )

        line_word_lists, line_heights, headline_bengali_font, headline_latin_font = fit_headline(
            measure_draw, title, max_text_width, max_headline_block_height
        )

        total_words = sum(len(w) for w in line_word_lists)
        highlight_count = build_highlight_flags(total_words, HIGHLIGHT_WORD_RATIO)

        headline_block_height = (
            sum(line_heights)
            + HEADLINE_LINE_SPACING * max(0, len(line_word_lists) - 1)
        )

        # ---------------- Metadata line ----------------

        source_text = (source or "").strip().upper()
        date_text = format_display_date(published_at)
        source_line = f"{source_text}  •  {date_text}" if source_text else date_text

        source_line_height = mixed_text_height(
            measure_draw, source_line, source_bengali_font, source_latin_font
        )

        # ---------------- Full-bleed photo (fills the entire card) ----------------

        photo = cover_crop_to_canvas(image, CARD_WIDTH, CARD_HEIGHT)
        base = photo.convert("RGBA")

        # ---------------- Bottom dark gradient (headline legibility) ----------------

        bottom_content_height = (
            headline_block_height + GAP_AFTER_HEADLINE + source_line_height
        )
        bottom_overlay_height = int(
            min(
                CARD_HEIGHT * 0.92,
                bottom_content_height + BOTTOM_MARGIN + 130,
            )
        )
        bottom_overlay_height = max(bottom_overlay_height, 260)

        bottom_gradient = make_vertical_gradient(
            CARD_WIDTH, bottom_overlay_height, top_alpha=0, bottom_alpha=205
        )
        base.alpha_composite(
            bottom_gradient, (0, CARD_HEIGHT - bottom_overlay_height)
        )

        # ---------------- Top dark gradient (pill/brand legibility) ----------------

        top_gradient = make_vertical_gradient(
            CARD_WIDTH, TOP_OVERLAY_HEIGHT, top_alpha=165, bottom_alpha=0
        )
        base.alpha_composite(top_gradient, (0, 0))

        draw = ImageDraw.Draw(base)

        # thin accent line right at the top edge
        draw.rectangle((0, 0, CARD_WIDTH, 6), fill=ACCENT_RED)

        # ---------------- Top row: "LATEST NEWS" pill + date ----------------

        pill_w, pill_h = draw_pill(
            draw, (SIDE_MARGIN, TOP_MARGIN), "LATEST NEWS",
            font=pill_font, fg=WHITE, bg=ACCENT_RED,
        )

        date_bbox = draw.textbbox((0, 0), date_text, font=date_font)
        date_w = date_bbox[2] - date_bbox[0]
        draw.text(
            (CARD_WIDTH - SIDE_MARGIN - date_w, TOP_MARGIN + (pill_h - (date_bbox[3] - date_bbox[1])) // 2 - date_bbox[1]),
            date_text, font=date_font, fill=OFF_WHITE,
        )

        # ---------------- Headline block (bottom, over the photo) ----------------

        y = CARD_HEIGHT - BOTTOM_MARGIN - source_line_height - GAP_AFTER_HEADLINE - headline_block_height
        global_index = 0

        for words, height in zip(line_word_lists, line_heights):
            draw_headline_line(
                draw, words, global_index, highlight_count,
                SIDE_MARGIN, y, height,
                headline_bengali_font, headline_latin_font,
                base_color=WHITE,
            )
            global_index += len(words)
            y += height + HEADLINE_LINE_SPACING

        # thin divider between headline and meta
        divider_y = CARD_HEIGHT - BOTTOM_MARGIN - source_line_height - (GAP_AFTER_HEADLINE // 2)
        draw.line(
            (SIDE_MARGIN, divider_y, CARD_WIDTH - SIDE_MARGIN, divider_y),
            fill=(255, 255, 255, 90), width=2,
        )

        # source/date meta line
        metadata_y = CARD_HEIGHT - BOTTOM_MARGIN - source_line_height
        draw_mixed_text(
            draw, (SIDE_MARGIN, metadata_y), source_line,
            source_bengali_font, source_latin_font, MUTED_LIGHT,
        )

        dot_x = CARD_WIDTH - SIDE_MARGIN - 8
        dot_y = metadata_y + source_line_height // 2
        draw.ellipse((dot_x - 5, dot_y - 5, dot_x + 5, dot_y + 5), fill=ACCENT_RED)

        # ---------------- Brand wordmark (top-left, small & unobtrusive) ----------------

        brand_x = SIDE_MARGIN
        brand_y = TOP_MARGIN + pill_h + 14

        if BRAND_TAGLINE:
            draw.text(
                (brand_x, brand_y), BRAND_TAGLINE,
                font=tagline_font, fill=(255, 255, 255, 200),
            )

        # ---------------- "Image collected" credit, tiny, bottom-right ----------------

        if source_text:
            credit_text = f"IMAGE: COLLECTED"
            credit_bbox = draw.textbbox((0, 0), credit_text, font=credit_font)
            credit_w = credit_bbox[2] - credit_bbox[0]
            draw.text(
                (CARD_WIDTH - SIDE_MARGIN - credit_w, CARD_HEIGHT - 26),
                credit_text, font=credit_font, fill=(255, 255, 255, 150),
            )

        # ---------------- Export ----------------

        output = io.BytesIO()
        base.convert("RGB").save(output, format="JPEG", quality=95, optimize=True)
        output.seek(0)

        if output.getbuffer().nbytes == 0:
            print("✗ Generated photo card is empty.")
            return None

        print(f"✓ Photo card created ({CARD_WIDTH}x{CARD_HEIGHT}, full-bleed)")
        return output

    except Exception as e:
        print(f"✗ Photo card creation failed: {e}")
        return None


# ============================================================
# FACEBOOK POST (hardened against common failure modes)
# ============================================================

def post_to_facebook(photo_bytes, title, description, article_url):
    if not photo_bytes or photo_bytes.getbuffer().nbytes == 0:
        return None, "Photo bytes are empty — nothing to upload."

    endpoint = f"https://graph.facebook.com/{META_GRAPH_VERSION}/{FACEBOOK_PAGE_ID}/photos"

    caption_parts = [title.strip()]
    if description:
        caption_parts.append(description.strip())
    caption_parts.append(article_url.strip())

    caption = "\n\n".join(part for part in caption_parts if part)

    if len(caption) > CAPTION_MAX_CHARS:
        caption = caption[:CAPTION_MAX_CHARS].rsplit(" ", 1)[0] + "…"

    photo_bytes.seek(0)

    try:
        response = fb_session.post(
            endpoint,
            data={
                "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
                "caption": caption,
                "published": "true",
            },
            files={"source": ("news.jpg", photo_bytes, "image/jpeg")},
            timeout=FACEBOOK_TIMEOUT,
        )

        try:
            data = response.json()
        except ValueError:
            return None, f"Non-JSON response (HTTP {response.status_code}): {response.text[:500]}"

        if response.ok and data.get("id"):
            return data["id"], None

        return None, data.get("error", data)

    except requests.exceptions.Timeout:
        return None, "Facebook request timed out."
    except requests.exceptions.RequestException as e:
        return None, f"Facebook request failed: {e}"
    except Exception as e:
        return None, str(e)


# ============================================================
# GET UNPOSTED NEWS
# ============================================================

def get_unposted_news():
    result = (
        supabase.table("news")
        .select("id,title,source,image,url,description,published_at")
        .eq("facebook_posted", False)
        .neq("source", "The Daily Star")
        .not_.is_("image", "null")
        .order("published_at", desc=True)
        .limit(MAX_POSTS_PER_RUN)
        .execute()
    )

    return result.data or []


# ============================================================
# MARK POSTED / SAVE ERROR
# ============================================================

def mark_posted(news_id, post_id):
    try:
        supabase.table("news").update({
            "facebook_posted": True,
            "facebook_post_id": post_id,
            "facebook_posted_at": "now()",
            "facebook_error": None,
        }).eq("id", news_id).execute()

        print("✓ Supabase: facebook_posted = TRUE")

    except Exception as e:
        print("✗ Supabase update failed:", e)


def save_error(news_id, error):
    try:
        supabase.table("news").update({
            "facebook_error": str(error),
            "facebook_posted": False,
        }).eq("id", news_id).execute()

    except Exception as e:
        print("✗ Could not save error:", e)


# ============================================================
# MAIN
# ============================================================

def main():
    print("\n==========================================")
    print("Starting Facebook poster...")
    print("==========================================")
    print(f"Graph API: {META_GRAPH_VERSION}")
    print(f"Maximum posts: {MAX_POSTS_PER_RUN}")
    print(f"Card size: {CARD_WIDTH}x{CARD_HEIGHT} (full-bleed)")
    print("Daily Star: SKIPPED")

    verify_text_rendering_support()

    news = get_unposted_news()
    print(f"Found {len(news)} news.")

    posted_count = 0

    for article in news:
        print("\n------------------------------------------")

        news_id = article["id"]
        title = article.get("title") or "Untitled"
        source = article.get("source") or ""
        article_url = article.get("url") or ""
        stored_image = article.get("image")
        published_at = article.get("published_at")
        stored_description = article.get("description") or ""

        print(f"Processing: {title}")
        print(f"Source: {source}")
        print(f"Article URL: {article_url}")

        try:
            description = get_article_description(stored_description, article_url)
            if description:
                print(f"✓ Description ready: {description}")
            else:
                print("⚠ No description will be added.")

            image = resolve_article_image(stored_image, article_url)

            if image is None:
                error = "Could not obtain a usable original article image."
                print(f"✗ FAILED\n{error}")
                save_error(news_id, error)
                continue

            card = create_photo_card(image, title, source, published_at)

            if card is None:
                error = "Could not create photo card from original article image."
                print(f"✗ FAILED\n{error}")
                save_error(news_id, error)
                continue

            print("Posting photo card to Facebook...")
            post_id, error = post_to_facebook(card, title, description, article_url)

            if post_id:
                print("✓ Facebook post successful")
                print(f"Facebook Post ID: {post_id}")
                mark_posted(news_id, post_id)
                posted_count += 1
                print("✓ COMPLETE")
            else:
                print("✗ Facebook post failed")
                print(f"Error: {error}")
                save_error(news_id, error)

        except Exception as e:
            print(f"✗ FAILED\n{e}")
            save_error(news_id, e)

    print("\n==========================================")
    print(f"Finished. Posted: {posted_count}")
    print("==========================================")


if __name__ == "__main__":
    main()