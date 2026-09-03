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
        result = (
            supabase
            .table("news")
            .insert({
                "source": article["source"],
                "title": article["title"],
                "description": article["description"],
                "image": article["image"],
                "url": article["url"],
                "published_at": article["published_at"],
            })
            .execute()
        )

        return bool(result.data)

    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            return False

        print("Database error:", e)
        return False