import os
import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
META_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v23.0")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")

if not FACEBOOK_PAGE_ID or not FACEBOOK_PAGE_ACCESS_TOKEN:
    raise RuntimeError(
        "FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN are required"
    )

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_unposted_news():
    result = (
        supabase
        .table("news")
        .select("id,source,title,image,url,published_at")
        .eq("facebook_posted", False)
        .order("published_at", desc=False)
        .limit(1)
        .execute()
    )

    return result.data


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


def post_to_facebook(article):
    url = (
        f"https://graph.facebook.com/"
        f"{META_GRAPH_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/photos"
    )

    message = (
        f"📰 {article['title']}\n\n"
        f"Source: {article['source']}"
    )

    response = requests.post(
        url,
        data={
            "url": article["image"],
            "message": message,
            "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
        },
        timeout=30,
    )

    data = response.json()

    if not response.ok or "error" in data:
        raise RuntimeError(data)

    return data.get("post_id") or data.get("id")


def main():
    articles = get_unposted_news()

    if not articles:
        print("No unposted news found.")
        return

    article = articles[0]

    print("Posting:", article["title"])

    if not article.get("image"):
        print("No image. Skipping.")
        mark_error(article["id"], "Article has no image.")
        return

    try:
        facebook_post_id = post_to_facebook(article)

        mark_posted(
            article["id"],
            facebook_post_id
        )

        print("Facebook post successful:", facebook_post_id)

    except Exception as e:
        print("Facebook posting failed:", e)
        mark_error(article["id"], e)
        raise


if __name__ == "__main__":
    main()