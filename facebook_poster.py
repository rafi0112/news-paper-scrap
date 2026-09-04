import os
import io
import requests

from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# =========================
# CONFIG
# =========================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv(
    "FACEBOOK_PAGE_ACCESS_TOKEN"
)

GRAPH_VERSION = os.getenv(
    "META_GRAPH_VERSION",
    "v26.0"
)

# প্রথমে 1 দিয়ে test করো
MAX_POSTS_PER_RUN = 1

CARD_SIZE = 1200

FONT_REGULAR = "fonts/NotoSansBengali-Regular.ttf"
FONT_BOLD = "fonts/NotoSansBengali-Bold.ttf"


# =========================
# SUPABASE
# =========================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# =========================
# FONT
# =========================

def get_font(path, size):
    return ImageFont.truetype(path, size)


# =========================
# TEXT WRAP
# =========================

def wrap_text(draw, text, font, max_width):

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


# =========================
# CREATE PHOTO CARD
# =========================

def create_photo_card(
    image_url,
    title,
    source
):

    try:

        response = requests.get(
            image_url,
            timeout=20,
            headers={
                "User-Agent":
                "Mozilla/5.0"
            }
        )

        response.raise_for_status()

        image = Image.open(
            io.BytesIO(response.content)
        ).convert("RGB")

        # --------------------------------
        # Center crop → 1200x1200
        # --------------------------------

        width, height = image.size

        target_ratio = 1

        current_ratio = width / height

        if current_ratio > target_ratio:

            new_width = int(
                height * target_ratio
            )

            left = (
                width - new_width
            ) // 2

            image = image.crop(
                (
                    left,
                    0,
                    left + new_width,
                    height
                )
            )

        else:

            new_height = int(
                width / target_ratio
            )

            top = (
                height - new_height
            ) // 2

            image = image.crop(
                (
                    0,
                    top,
                    width,
                    top + new_height
                )
            )

        image = image.resize(
            (CARD_SIZE, CARD_SIZE),
            Image.Resampling.LANCZOS
        )

        # --------------------------------
        # Overlay
        # --------------------------------

        overlay = Image.new(
            "RGBA",
            image.size,
            (0, 0, 0, 0)
        )

        overlay_draw = ImageDraw.Draw(
            overlay
        )

        # Clean dark gradient at bottom
        gradient_height = 500

        for y in range(
            CARD_SIZE - gradient_height,
            CARD_SIZE
        ):

            alpha = int(
                220 *
                (
                    y -
                    (CARD_SIZE - gradient_height)
                )
                / gradient_height
            )

            overlay_draw.line(
                [
                    (
                        0,
                        y
                    ),
                    (
                        CARD_SIZE,
                        y
                    )
                ],
                fill=(0, 0, 0, alpha)
            )

        image = Image.alpha_composite(
            image.convert("RGBA"),
            overlay
        )

        draw = ImageDraw.Draw(image)

        # --------------------------------
        # Fonts
        # --------------------------------

        source_font = get_font(
            FONT_BOLD,
            42
        )

        title_font = get_font(
            FONT_BOLD,
            68
        )

        # --------------------------------
        # Source
        # --------------------------------

        source_text = source.upper()

        source_x = 70
        source_y = 735

        bbox = draw.textbbox(
            (0, 0),
            source_text,
            font=source_font
        )

        source_width = (
            bbox[2] - bbox[0]
        )

        # Source badge
        draw.rounded_rectangle(
            (
                source_x - 18,
                source_y - 12,
                source_x + source_width + 18,
                source_y + 52
            ),
            radius=12,
            fill=(255, 255, 255, 235)
        )

        draw.text(
            (
                source_x,
                source_y
            ),
            source_text,
            font=source_font,
            fill=(20, 20, 20)
        )

        # --------------------------------
        # Title
        # --------------------------------

        title_lines = wrap_text(
            draw,
            title,
            title_font,
            CARD_SIZE - 140
        )

        # Keep maximum 4 lines
        title_lines = title_lines[:4]

        y = 825

        for line in title_lines:

            draw.text(
                (
                    70,
                    y
                ),
                line,
                font=title_font,
                fill="white",
                stroke_width=1,
                stroke_fill=(0, 0, 0)
            )

            bbox = draw.textbbox(
                (0, 0),
                line,
                font=title_font
            )

            line_height = (
                bbox[3] - bbox[1]
            )

            y += line_height + 12

        # --------------------------------
        # Save
        # --------------------------------

        output = io.BytesIO()

        image.convert("RGB").save(
            output,
            format="JPEG",
            quality=92,
            optimize=True
        )

        output.seek(0)

        return output

    except Exception as e:

        print(
            "Card creation error:",
            e
        )

        return None


# =========================
# FACEBOOK POST
# =========================

def post_to_facebook(
    card_file,
    title,
    source,
    article_url
):

    url = (
        f"https://graph.facebook.com/"
        f"{GRAPH_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/photos"
    )

    caption = (
        f"{title}\n\n"
        f"Source: {source}\n\n"
        f"🔗 বিস্তারিত পড়ুন:\n"
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

    response = requests.post(
        url,
        files=files,
        data=data,
        timeout=60
    )

    result = response.json()

    if response.status_code >= 400:

        raise Exception(
            f"Facebook error: {result}"
        )

    return result


# =========================
# GET UNPOSTED NEWS
# =========================

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
        .not_.is_(
            "image",
            "null"
        )
        .order(
            "published_at",
            desc=True
        )
        .limit(MAX_POSTS_PER_RUN)
        .execute()
    )

    return result.data or []


# =========================
# MARK POSTED
# =========================

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
            "facebook_posted_at":
                "now()",
            "facebook_error": None
        })
        .eq(
            "id",
            news_id
        )
        .execute()
    )


# =========================
# SAVE ERROR
# =========================

def save_error(
    news_id,
    error
):

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


# =========================
# MAIN
# =========================

def main():

    print(
        "Starting Facebook poster..."
    )

    news_list = get_unposted_news()

    print(
        f"Found {len(news_list)} news."
    )

    posted = 0

    for article in news_list:

        news_id = article["id"]
        title = article["title"]
        source = article["source"]
        image_url = article["image"]
        article_url = article["url"]

        print(
            f"\nProcessing: {title}"
        )

        try:

            # 1. Create photo card
            card = create_photo_card(
                image_url,
                title,
                source
            )

            if not card:

                raise Exception(
                    "Could not create photo card"
                )

            # 2. Post to Facebook
            result = post_to_facebook(
                card,
                title,
                source,
                article_url
            )

            # Facebook returns post/photo ID
            post_id = (
                result.get("post_id")
                or result.get("id")
            )

            # 3. Mark successful
            mark_posted(
                news_id,
                post_id
            )

            posted += 1

            print(
                "✓ Facebook post successful"
            )

            print(
                "Post ID:",
                post_id
            )

        except Exception as e:

            print(
                "✗ Failed:",
                e
            )

            save_error(
                news_id,
                e
            )

    print(
        f"\nFinished. Posted: {posted}"
    )


if __name__ == "__main__":
    main()