import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY are required"
    )

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


def init_db():
    print("Supabase database ready.")


def save_news(article):
    try:

        published_at = article.get(
            "published_at"
        )

        if published_at and hasattr(
            published_at,
            "isoformat"
        ):
            published_at = published_at.isoformat()

        result = (
            supabase
            .table("news")
            .insert({
                "source": article["source"],
                "title": article["title"],
                "description": article.get(
                    "description",
                    ""
                ),
                "image": article.get(
                    "image"
                ),
                "url": article["url"],
                "published_at": published_at,
            })
            .execute()
        )

        return bool(result.data)

    except Exception as e:

        error_text = str(e).lower()

        if (
            "duplicate" in error_text
            or "unique" in error_text
        ):
            return False

        print(
            "Database error:",
            e
        )

        return False