import os
import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")

META_GRAPH_VERSION = os.getenv(
    "META_GRAPH_VERSION",
    "v26.0"
)

# --------------------------------------------------
# Validate environment variables
# --------------------------------------------------

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY are required"
    )

if not FACEBOOK_PAGE_ID or not FACEBOOK_PAGE_ACCESS_TOKEN:
    raise RuntimeError(
        "FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN are required"
    )

# --------------------------------------------------
# Supabase client
# --------------------------------------------------

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# --------------------------------------------------
# Get ALL unposted news
# --------------------------------------------------

def get_unposted_news():

    result = (
        supabase
        .table("news")
        .select(
            "id,source,title,image,url,published_at"
        )
        .eq("facebook_posted", False)
        .order("published_at", desc=False)
        .execute()
    )

    return result.data or []


# --------------------------------------------------
# Mark successful post
# --------------------------------------------------

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


# --------------------------------------------------
# Mark failed post
# --------------------------------------------------

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


# --------------------------------------------------
# Post one article to Facebook
# --------------------------------------------------

def post_to_facebook(article):

    facebook_url = (
        f"https://graph.facebook.com/"
        f"{META_GRAPH_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/photos"
    )

    caption = (
        f"📰 {article['title']}\n\n"
        f"Source: {article['source']}"
    )

    response = requests.post(
        facebook_url,
        data={
            "url": article["image"],
            "caption": caption,
            "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
        },
        timeout=30,
    )

    try:
        data = response.json()

    except Exception:
        raise RuntimeError(
            f"Facebook returned invalid response: "
            f"{response.text}"
        )

    if not response.ok or "error" in data:
        raise RuntimeError(data)

    facebook_post_id = (
        data.get("post_id")
        or data.get("id")
    )

    if not facebook_post_id:
        raise RuntimeError(
            f"Facebook post ID not found in response: {data}"
        )

    return facebook_post_id


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    articles = get_unposted_news()

    if not articles:

        print(
            "No unposted news found."
        )

        return

    print(
        f"Found {len(articles)} unposted news."
    )

    successful = 0
    failed = 0
    skipped = 0

    # ----------------------------------------------
    # Post ALL unposted articles
    # ----------------------------------------------

    for index, article in enumerate(
        articles,
        start=1
    ):

        print(
            f"\n[{index}/{len(articles)}] "
            f"Posting: {article['title']}"
        )

        # ------------------------------------------
        # Check image
        # ------------------------------------------

        if not article.get("image"):

            print(
                "No image. Skipping."
            )

            mark_error(
                article["id"],
                "Article has no image."
            )

            skipped += 1

            continue

        # ------------------------------------------
        # Post to Facebook
        # ------------------------------------------

        try:

            facebook_post_id = post_to_facebook(
                article
            )

            mark_posted(
                article["id"],
                facebook_post_id
            )

            successful += 1

            print(
                "Facebook post successful:",
                facebook_post_id
            )

        except Exception as e:

            failed += 1

            print(
                "Facebook posting failed:",
                e
            )

            mark_error(
                article["id"],
                e
            )

            # --------------------------------------
            # IMPORTANT:
            # Don't stop.
            # Continue with next news.
            # --------------------------------------

            continue

    # ----------------------------------------------
    # Final summary
    # ----------------------------------------------

    print("\n===================================")
    print("Facebook posting completed")
    print("===================================")
    print(
        "Total found:",
        len(articles)
    )
    print(
        "Successful:",
        successful
    )
    print(
        "Failed:",
        failed
    )
    print(
        "Skipped:",
        skipped
    )
    print("===================================")


# --------------------------------------------------
# Run
# --------------------------------------------------

if __name__ == "__main__":
    main()