import os
import io
import requests

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from dotenv import load_dotenv
from supabase import create_client


# =========================================================
# ENV
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

# First test with 1
MAX_POSTS_PER_RUN = 1

# Later:
# MAX_POSTS_PER_RUN = 3

CARD_WIDTH = 1200
CARD_HEIGHT = 1200

IMAGE_TIMEOUT = 25

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)


# =========================================================
# VALIDATE ENV
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
# FONT
# =========================================================

def get_font(size, bold=False):

    if bold:
        names = [
            "NotoSansBengali-Bold.ttf",
            "NotoSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
        ]
    else:
        names = [
            "NotoSansBengali-Regular.ttf",
            "NotoSans-Regular.ttf",
            "DejaVuSans.ttf",
        ]

    search_dirs = [
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/liberation2",
    ]

    for directory in search_dirs:

        for name in names:

            path = os.path.join(
                directory,
                name
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

    # Search repo fonts if available
    repo_font_dirs = [
        "fonts",
        "./fonts",
    ]

    for directory in repo_font_dirs:

        for name in names:

            path = os.path.join(
                directory,
                name
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
        "WARNING: No suitable font found."
    )

    return ImageFont.load_default()


# =========================================================
# TEXT MEASUREMENT
# =========================================================

def text_width(
    draw,
    text,
    font
):

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font
    )

    return bbox[2] - bbox[0]


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
            else current + " " + word
        )

        if (
            text_width(
                draw,
                test,
                font
            )
            <= max_width
        ):

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

    # Limit number of lines
    if len(lines) <= max_lines:
        return lines

    lines = lines[:max_lines]

    # Add ellipsis to final line
    last = lines[-1]

    while last:

        candidate = last + "..."

        if (
            text_width(
                draw,
                candidate,
                font
            )
            <= max_width
        ):

            lines[-1] = candidate
            break

        last = last[:-1].rstrip()

    return lines


# =========================================================
# DOWNLOAD ORIGINAL IMAGE
# =========================================================

def download_image(image_url):

    if not image_url:

        print(
            "No article image URL."
        )

        return None

    urls = [image_url]

    # HTTP fallback
    if image_url.startswith("https://"):

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

            content_type = (
                response.headers
                .get(
                    "Content-Type",
                    ""
                )
                .lower()
            )

            # Make sure it is actually an image
            if (
                "image" not in content_type
                and not url.lower().endswith(
                    (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp"
                    )
                )
            ):

                print(
                    "Response is not an image."
                )

                continue

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
# COVER IMAGE
# =========================================================

def make_cover_image(image):

    """
    Keep the original article image,
    but crop it intelligently into
    a 1200x1200 social card.
    """

    original_width, original_height = (
        image.size
    )

    target_ratio = (
        CARD_WIDTH / CARD_HEIGHT
    )

    original_ratio = (
        original_width / original_height
    )

    if original_ratio > target_ratio:

        # Image is wider
        new_height = original_height

        new_width = int(
            original_height
            * target_ratio
        )

        left = (
            original_width
            - new_width
        ) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                new_height
            )
        )

    else:

        # Image is taller
        new_width = original_width

        new_height = int(
            original_width
            / target_ratio
        )

        top = (
            original_height
            - new_height
        ) // 2

        image = image.crop(
            (
                0,
                top,
                new_width,
                top + new_height
            )
        )

    image = image.resize(
        (
            CARD_WIDTH,
            CARD_HEIGHT
        ),
        Image.Resampling.LANCZOS
    )

    return image


# =========================================================
# CREATE MODERN PHOTO CARD
# =========================================================

def create_photo_card(
    image_url,
    title,
    source
):

    # -----------------------------------------------------
    # Download ORIGINAL newspaper image
    # -----------------------------------------------------

    image = download_image(
        image_url
    )

    if image is None:

        print(
            "✗ Original image unavailable."
        )

        # IMPORTANT:
        # We do NOT create a fake image.
        # User specifically wants original image.
        return None

    try:

        # -------------------------------------------------
        # Cover
        # -------------------------------------------------

        image = make_cover_image(
            image
        )

        image = image.convert(
            "RGBA"
        )

        # -------------------------------------------------
        # Overlay layer
        # -------------------------------------------------

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

        # =================================================
        # TOP subtle dark gradient
        # =================================================

        top_height = 180

        for y in range(
            top_height
        ):

            alpha = int(
                120
                * (
                    1
                    - (
                        y / top_height
                    )
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

        # =================================================
        # BOTTOM strong gradient
        # =================================================

        bottom_start = 520

        for y in range(
            bottom_start,
            CARD_HEIGHT
        ):

            progress = (
                y - bottom_start
            ) / (
                CARD_HEIGHT
                - bottom_start
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

        # Apply overlay
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
            64,
            bold=True
        )

        small_font = get_font(
            25,
            bold=True
        )

        # =================================================
        # SOURCE PILL
        # =================================================

        source_text = (
            str(source).upper()
        )

        source_x = 70
        source_y = 700

        source_bbox = draw.textbbox(
            (
                0,
                0
            ),
            source_text,
            font=source_font
        )

        source_w = (
            source_bbox[2]
            - source_bbox[0]
        )

        source_h = (
            source_bbox[3]
            - source_bbox[1]
        )

        pill_left = (
            source_x - 20
        )

        pill_top = (
            source_y - 12
        )

        pill_right = (
            source_x
            + source_w
            + 20
        )

        pill_bottom = (
            source_y
            + source_h
            + 18
        )

        draw.rounded_rectangle(
            (
                pill_left,
                pill_top,
                pill_right,
                pill_bottom
            ),
            radius=18,
            fill=(
                255,
                255,
                255,
                245
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
        # TITLE
        # =================================================

        title_lines = wrap_text(
            draw,
            title,
            title_font,
            CARD_WIDTH - 140,
            max_lines=4
        )

        y = 790

        for line in title_lines:

            # Very subtle shadow
            draw.text(
                (
                    72,
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

            # Main title
            draw.text(
                (
                    70,
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

            y += (
                line_height
                + 12
            )

        # =================================================
        # BOTTOM BRAND LINE
        # =================================================

        line_y = 1080

        draw.rounded_rectangle(
            (
                70,
                line_y,
                270,
                line_y + 5
            ),
            radius=3,
            fill=(
                255,
                255,
                255,
                220
            )
        )

        draw.text(
            (
                70,
                1100
            ),
            "NEWS UPDATE",
            font=small_font,
            fill=(
                230,
                230,
                230,
                230
            )
        )

        # =================================================
        # EXPORT JPEG
        # =================================================

        output = io.BytesIO()

        image.convert(
            "RGB"
        ).save(
            output,
            format="JPEG",
            quality=93,
            optimize=True
        )

        output.seek(0)

        print(
            "✓ Modern photo card created"
        )

        return output

    except Exception as e:

        print(
            f"Card creation error: {e}"
        )

        return None


# =========================================================
# FACEBOOK POST
# =========================================================

def post_to_facebook(
    card_file,
    title,
    source,
    article_url
):

    endpoint = (
        f"https://graph.facebook.com/"
        f"{META_GRAPH_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/photos"
    )

    # =====================================================
    # CAPTION
    # =====================================================

    caption = (
        f"{title}\n\n"
        f"Source: {source}\n\n"
        f"🔗 বিস্তারিত পড়ুন:\n"
        f"{article_url}"
    )

    # =====================================================
    # FILE
    # =====================================================

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

    # =====================================================
    # FACEBOOK ERROR
    # =====================================================

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
        "✓ Supabase: facebook_posted = TRUE"
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
        f"Graph API: {META_GRAPH_VERSION}"
    )

    print(
        f"Maximum posts: {MAX_POSTS_PER_RUN}"
    )

    # -----------------------------------------------------
    # Get news
    # -----------------------------------------------------

    news_list = get_unposted_news()

    print(
        f"Found {len(news_list)} news."
    )

    if not news_list:

        print(
            "No unposted news."
        )

        return

    posted_count = 0

    # -----------------------------------------------------
    # Process
    # -----------------------------------------------------

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

        image_url = article.get(
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

        try:

            # =============================================
            # 1. Create modern photo card
            # =============================================

            card = create_photo_card(
                image_url,
                title,
                source
            )

            if card is None:

                raise Exception(
                    "Original article image "
                    "could not be downloaded."
                )

            # =============================================
            # 2. Facebook post
            # =============================================

            result = post_to_facebook(
                card,
                title,
                source,
                article_url
            )

            # =============================================
            # 3. Facebook ID
            # =============================================

            post_id = (
                result.get("post_id")
                or result.get("id")
            )

            print(
                f"Facebook Post ID: {post_id}"
            )

            # =============================================
            # 4. Mark posted
            # =============================================

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

    # -----------------------------------------------------
    # Final
    # -----------------------------------------------------

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