import os

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
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

app = FastAPI(title="News Hub API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "status": "running",
        "message": "News Hub API is working"
    }


@app.get("/api/news")
def get_news(
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    source: str | None = None,
    search: str | None = None
):
    try:
        # ------------------------------------------------
        # Get total number of matching articles
        # ------------------------------------------------

        count_query = (
            supabase
            .table("news")
            .select("id", count="exact")
        )

        if source:
            count_query = count_query.eq("source", source)

        if search:
            keyword = f"%{search}%"
            count_query = count_query.or_(
                f"title.ilike.{keyword},description.ilike.{keyword}"
            )

        count_result = count_query.execute()

        total = count_result.count or 0

        # ------------------------------------------------
        # Pagination
        # ------------------------------------------------

        offset = (page - 1) * limit
        end = offset + limit - 1

        query = (
            supabase
            .table("news")
            .select(
                "id,source,title,description,image,url,published_at"
            )
        )

        if source:
            query = query.eq("source", source)

        if search:
            keyword = f"%{search}%"
            query = query.or_(
                f"title.ilike.{keyword},description.ilike.{keyword}"
            )

        result = (
            query
            .order(
                "published_at",
                desc=True,
                nullsfirst=False
            )
            .range(offset, end)
            .execute()
        )

        news = result.data or []

        total_pages = (
            (total + limit - 1) // limit
            if total > 0
            else 0
        )

        return {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "news": news
        }

    except Exception as e:
        print("API error:", e)

        return {
            "page": page,
            "limit": limit,
            "total": 0,
            "total_pages": 0,
            "news": [],
            "error": "Unable to fetch news"
        }


@app.get("/api/sources")
def get_sources():
    try:
        result = (
            supabase
            .table("news")
            .select("source")
            .execute()
        )

        sources = sorted(
            {
                row["source"]
                for row in (result.data or [])
                if row.get("source")
            }
        )

        return sources

    except Exception as e:
        print("Source API error:", e)
        return []


@app.get("/api/latest")
def get_latest():
    try:
        result = (
            supabase
            .table("news")
            .select(
                "id,source,title,description,image,url,published_at"
            )
            .order(
                "published_at",
                desc=True,
                nullsfirst=False
            )
            .limit(1)
            .execute()
        )

        if not result.data:
            return {"news": None}

        return {"news": result.data[0]}

    except Exception as e:
        print("Latest API error:", e)
        return {"news": None}