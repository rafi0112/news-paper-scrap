import os

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client


# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY are required"
    )


# --------------------------------------------------
# Supabase client
# --------------------------------------------------

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# --------------------------------------------------
# FastAPI app
# --------------------------------------------------

app = FastAPI(title="News Hub API")


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Frontend
# --------------------------------------------------

@app.get("/")
def home():
    return FileResponse("index.html")


# --------------------------------------------------
# Get news
# --------------------------------------------------

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
            count_query = count_query.eq(
                "source",
                source
            )

        if search:
            keyword = f"%{search}%"

            count_query = count_query.or_(
                f"title.ilike.{keyword},"
                f"description.ilike.{keyword}"
            )

        count_result = count_query.execute()

        total = count_result.count or 0


        # ------------------------------------------------
        # Pagination
        # ------------------------------------------------

        offset = (page - 1) * limit
        end = offset + limit - 1


        # ------------------------------------------------
        # Fetch news
        # ------------------------------------------------

        query = (
            supabase
            .table("news")
            .select(
                "id,source,title,description,image,url,published_at"
            )
        )

        if source:
            query = query.eq(
                "source",
                source
            )

        if search:
            keyword = f"%{search}%"

            query = query.or_(
                f"title.ilike.{keyword},"
                f"description.ilike.{keyword}"
            )


        # ------------------------------------------------
        # Order + pagination
        # ------------------------------------------------

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


        # ------------------------------------------------
        # Total pages
        # ------------------------------------------------

        total_pages = (
            (total + limit - 1) // limit
            if total > 0
            else 0
        )


        # ------------------------------------------------
        # Response
        # ------------------------------------------------

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


# --------------------------------------------------
# Get available sources
# --------------------------------------------------

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


# --------------------------------------------------
# Get latest news
# --------------------------------------------------

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
            return {
                "news": None
            }


        return {
            "news": result.data[0]
        }


    except Exception as e:

        print("Latest API error:", e)

        return {
            "news": None
        }