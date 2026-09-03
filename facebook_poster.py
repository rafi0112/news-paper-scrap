import os
import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# =========================
# Environment Variables
# =========================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")

META_GRAPH_VERSION = os.getenv(
    "META_GRAPH_VERSION",
    "v25.0"
)


# =========================
# Validate Environment
# =========================

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY are required"
    )

if not FACEBOOK_PAGE_ID or not FACEBOOK_PAGE_ACCESS_TOKEN:
    raise RuntimeError(
        "FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN are required"
    )


# =========================
# Supabase Client
# =========================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# =========================
# Get Unposted News
# =========================

def get_unposted_news():
    result = (
        supabase
        .table("news")
        .select(
            "id,source,title,image,url,published_at"
        )
        .eq("facebook_posted", False)
        .order("published_at", desc=False)
        .limit(1)
        .execute()
    )

    return result.data


# =========================
# Mark Facebook Posted
# =========================

def mark_posted(news_id, facebook_post_id):
    (
        supabase
        .table("news")
        .update({
            "facebook_posted": True,
            "facebook_post_id": facebook_post_id,
            "facebook_posted_at": "now()",
            "facebook_error": None
        })
        .eq("id", news_id)
        .execute()
    )


# =========================
# Save Facebook Error
# =========================

def mark_error(news_id, error):
    (
        supabase
        .table("news")
        .update({
            "facebook_error": str(error)[:1000]
        })
        .eq("id", news_id)
        .execute()
    )


# =========================
# Post Photo to Facebook
# =========================

def post_to_facebook(article):

    facebook_url = (
        f"https://graph.facebook.com/"
        f"{META_GRAPH_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/photos"
    )

    # Facebook post text
    message = (
        f"📰 {article['title']}\n\n"
        f"Source: {article['source']}"
    )

    # Send photo + caption to Facebook
    response = requests.post(
        facebook_url,
        data={
            "url": article["image"],
            "caption": message,
            "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
        },
        timeout=30,
    )

    # Convert response to JSON
    try:
        data = response.json()
    except Exception:
        raise RuntimeError(
            f"Facebook returned invalid response: "
            f"{response.text}"
        )

    # Check Facebook API error
    if not response.ok or "error" in data:
        raise RuntimeError(data)

    # Facebook can return either id or post_id
    facebook_post_id = (
        data.get("post_id")
        or data.get("id")
    )

    if not facebook_post_id:
        raise RuntimeError(
            f"Facebook post ID not found in response: {data}"
        )

    return facebook_post_id


# =========================
# Main
# =========================

def main():

    articles = get_unposted_news()

    # No new article
    if not articles:
        print("No unposted news found.")
        return

    article = articles[0]

    print(
        "Posting:",
        article["title"]
    )

    # Article must have image
    if not article.get("image"):
        print("No image. Skipping.")

        mark_error(
            article["id"],
            "Article has no image."
        )

        return

    try:

        # Post to Facebook
        facebook_post_id = post_to_facebook(article)

        # Mark as posted in Supabase
        mark_posted(
            article["id"],
            facebook_post_id
        )

        print(
            "Facebook post successful:",
            facebook_post_id
        )

    except Exception as e:

        print(
            "Facebook posting failed:",
            e
        )

        # Save error but keep facebook_posted = false
        mark_error(
            article["id"],
            e
        )

        # Make GitHub Actions show failure
        raise


# =========================
# Run
# =========================

if __name__ == "__main__":
    main()