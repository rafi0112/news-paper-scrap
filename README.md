<div align="center">

# 📰 Automated Bengali News Scraper & Facebook Publisher

**A lightweight Python automation pipeline that scrapes Bangladeshi newspapers, stores article metadata in Supabase, and auto-publishes photo-cards to a Facebook Page — entirely on GitHub Actions.**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/Automation-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)
![Supabase](https://img.shields.io/badge/Database-Supabase-3ECF8E?logo=supabase&logoColor=white)
![Facebook Graph API](https://img.shields.io/badge/Publishing-Facebook%20Graph%20API-0866FF?logo=facebook&logoColor=white)
![Pillow](https://img.shields.io/badge/Image%20Rendering-Pillow-FFB000)
![License](https://img.shields.io/badge/status-active-brightgreen)

</div>

> **📌 Content policy / copyright note:** This project works with article **metadata and links only** — it does not republish full copyrighted article bodies. Each Facebook post uses the article title, source attribution, the original article photo styled as a card, and a link back to the source. Make sure your use of source images/content complies with the relevant publisher's terms or your own redistribution rights.

---

## 📑 Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [Architecture](#2-architecture)
3. [Project Structure](#3-project-structure)
4. [How the Automation Works](#4-how-the-automation-works)
5. [News Scraping](#5-news-scraping)
6. [Supabase Database](#6-supabase-database)
7. [Facebook Tracking Columns](#7-facebook-tracking-columns)
8. [One-Day Automatic Deletion](#8-one-day-automatic-deletion)
9. [Facebook Publishing Logic](#9-facebook-publishing-logic)
10. [The Daily Star Is Skipped](#10-the-daily-star-is-skipped)
11. [Real Article Photo Handling](#11-real-article-photo-handling)
12. [TBS Example](#12-tbs-example)
13. [Original Photo-Card Design](#13-original-photo-card-design)
14. [Photo-Card Layout](#14-photo-card-layout)
15. [Bengali + English Titles](#15-bengali--english-titles)
16. [Facebook Caption](#16-facebook-caption)
17. [Why the Title Appears Twice](#17-why-the-article-title-appears-twice)
18. [Facebook API](#18-facebook-api)
19. [Facebook Page](#19-facebook-page)
20. [GitHub Secrets](#20-github-secrets)
21. [.gitignore](#21-gitignore)
22. [requirements.txt](#22-requirementstxt)
23. [GitHub Actions Workflow](#23-github-actions-workflow)
24. [Posting Limit](#24-posting-limit)
25. [What Happens During a Normal Run](#25-what-happens-during-a-normal-run)
26. [If Image Download Fails](#26-what-happens-if-image-download-fails)
27. [If Facebook Fails](#27-what-happens-if-facebook-fails)
28. [Duplicate Article Handling](#28-what-happens-if-the-same-article-is-encountered-again)
29. [Manual Testing](#29-manual-testing)
30. [Troubleshooting](#30-troubleshooting)
31. [Security](#31-security)
32. [Local Development](#32-local-development)
33. [Why GitHub Actions Instead of a VPS](#33-why-github-actions-is-used-instead-of-a-vps)
34. [Role of Vercel](#34-role-of-vercel)
35. [Complete System Summary](#35-complete-system-summary)
36. [Final Expected Result](#36-final-expected-result)
37. [Maintenance Checklist](#37-maintenance-checklist)
38. [Current Project Status](#38-current-project-status)

---

## 1. What This Project Does

The complete flow:

```text
News Websites
     ↓
GitHub Actions
     ↓
scraper.py
     ↓
Supabase PostgreSQL
     ↓
facebook_poster.py
     ↓
Find real article image
     ↓
Pillow creates modern photo-card
     ↓
Facebook Page
```

**Current Facebook sources:**

| Source | Posted to Facebook? |
|---|:---:|
| bdnews24 | ✅ |
| Prothom Alo | ✅ |
| The Business Standard (TBS) | ✅ |
| Daily Amar Desh | ✅ |
| The Daily Star | ❌ (intentionally excluded) |

> The Daily Star is still allowed to exist in the news database if the scraper collects it — `facebook_poster.py` simply ignores rows whose source is exactly `The Daily Star`.

---

## 2. Architecture

![System Architecture](https://github.com/user-attachments/assets/8e3009d8-ccbf-4612-ab69-06346c34227b)

### Main Components

| Component | Purpose |
|---|---|
| Newspaper websites | Original source of news |
| `scraper.py` | Finds recent articles and extracts metadata |
| Supabase | Stores articles and Facebook posting status |
| `facebook_poster.py` | Selects unposted news and publishes cards |
| Pillow | Creates the modern photo-card |
| GitHub Actions | Runs the automation on a schedule |
| Facebook Graph API | Publishes the final photo post |
| Supabase scheduled function | Deletes news older than 1 day |

---

## 3. Project Structure

```text
NEWS PAPER SCRAP/
│
├── scraper.py
├── database.py
├── facebook_poster.py
├── requirements.txt
├── .gitignore
│
├── .github/
│   └── workflows/
│       └── news.yml
│
└── README.md
```

> No `fonts/` folder is required — the GitHub Actions workflow installs the Noto font package directly.

---

## 4. How the Automation Works

### Step 1 — GitHub Actions starts

```yaml
on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch:
```

This means:
- Scheduled execution approximately every 5 minutes
- Manual execution is also available from the GitHub Actions tab

> GitHub scheduled workflows use cron syntax, and scheduled runs use the default branch. The shortest supported schedule interval documented by GitHub is 5 minutes.

### Step 2 — GitHub creates a temporary runner

GitHub Actions spins up an Ubuntu virtual machine for the workflow, which:

1. Checks out the repository
2. Installs Python
3. Installs Linux fonts
4. Installs Python dependencies
5. Runs `scraper.py`
6. Runs `facebook_poster.py`

The runner is temporary — your personal PC never needs to stay on.

---

## 5. News Scraping

`scraper.py` collects article information. For each article, the database stores:

```text
id
source
title
description
image
url
published_at
created_at
```

The scraper is designed to:
- Inspect the configured newspaper pages
- Find probable article URLs
- Extract article titles, dates, and images
- Ignore articles outside the configured recent-news window
- Save new URLs only

The article `url` is unique in Supabase, so the same article is never inserted twice.

---

## 6. Supabase Database

The project uses **Supabase PostgreSQL**, which provides a full Postgres database accessible via dashboard, SQL editor, APIs, and client libraries.

### Main table

```sql
create table news (
    id bigint generated by default as identity primary key,
    source text not null,
    title text not null,
    description text,
    image text,
    url text unique not null,
    published_at timestamptz,
    created_at timestamptz default now()
);
```

### Indexes

```sql
create index idx_news_published
on news(published_at desc);

create index idx_news_source
on news(source);
```

---

## 7. Facebook Tracking Columns

```sql
ALTER TABLE news
ADD COLUMN IF NOT EXISTS facebook_posted BOOLEAN DEFAULT FALSE;

ALTER TABLE news
ADD COLUMN IF NOT EXISTS facebook_post_id TEXT;

ALTER TABLE news
ADD COLUMN IF NOT EXISTS facebook_posted_at TIMESTAMPTZ;

ALTER TABLE news
ADD COLUMN IF NOT EXISTS facebook_error TEXT;

CREATE INDEX IF NOT EXISTS idx_news_facebook_posted
ON news(facebook_posted);
```

| Column | Meaning |
|---|---|
| `facebook_posted` | `FALSE` = not yet posted successfully · `TRUE` = post succeeded |
| `facebook_post_id` | The Facebook post ID returned by the Graph API |
| `facebook_posted_at` | Timestamp of the successful post |
| `facebook_error` | The most recent Facebook/card/image error, if any |

This makes the system able to **retry failed articles later** instead of permanently losing them.

---

## 8. One-Day Automatic Deletion

The project intentionally keeps recent news only.

```sql
create or replace function delete_old_news()
returns void
language sql
as $$
    delete from news
    where published_at is not null
      and published_at < now() - interval '1 day';
$$;
```

**Scheduled job:**

| Field | Value |
|---|---|
| Job name | `delete-old-news` |
| Schedule | `0 * * * *` (every hour) |
| Command | `select delete_old_news();` |

This deletes any row whose `published_at` is older than 1 day — **regardless** of whether `facebook_posted` is `TRUE` or `FALSE`.

> Supabase supports database functions through its SQL editor, and PostgreSQL functions can perform this kind of database-side cleanup logic natively.

---

## 9. Facebook Publishing Logic

`facebook_poster.py` performs the following sequence:

```text
Get latest unposted news
        ↓
Ignore The Daily Star
        ↓
Check stored image
        ↓
Detect banner/logo/default image
        ↓
Find actual article image
        ↓
Download original photo
        ↓
Create modern photo-card
        ↓
Upload photo to Facebook
        ↓
Save Facebook post ID
        ↓
Set facebook_posted = TRUE
```

---

## 10. The Daily Star Is Skipped

The Facebook query contains:

```python
.neq("source", "The Daily Star")
```

| Source | Result |
|---|:---:|
| bdnews24 | ✅ |
| Prothom Alo | ✅ |
| The Business Standard | ✅ |
| The Daily Star | ❌ |

This also means a Daily Star article never consumes one of the available Facebook posting slots.

---

## 11. Real Article Photo Handling

This is an important part of the system. Sometimes a newspaper's scraper returns something like:

```text
banner.png
logo.png
ds-logo-share.jpeg
default.jpg
```

...instead of the actual article photo.

The Facebook poster checks the stored image URL against known **generic image name patterns**:

```text
banner · logo · default · placeholder
share-image · og-default · fallback · avatar · icon
```

If the stored image looks generic, the program opens the actual article page and searches for:

```text
og:image
twitter:image
JSON-LD image
```

The best usable article image is then downloaded.

---

## 12. TBS Example

Suppose the scraper stores:

```text
https://tbsnews.net/sites/all/themes/sloth/banner.png
```

The publisher page is opened, and the program searches the article HTML for the actual article image. Instead of posting `banner.png`, it resolves and uses the **actual article photo** — preventing a site-wide banner/logo from becoming the Facebook image.

---

## 13. Original Photo-Card Design

The system does **not** generate an artificial news image. The original article photo is used as the background, and Pillow adds a lightweight UI layer:

```text
Original article photo
        +
   bottom gradient
        +
    source pill
        +
 exact article title
        =
  modern photo-card
```

**Target output:** `1200 × 1200` JPEG — the original photograph remains the visual base.

---

## 14. Photo-Card Layout

```text
┌──────────────────────────────────┐
│                                   │
│                                   │
│         ORIGINAL ARTICLE         │
│              PHOTO               │
│                                   │
│                                   │
│                                   │
│   ┌────────────────────────┐     │
│   │ The Business Standard  │     │
│   └────────────────────────┘     │
│                                   │
│   Exact article title goes       │
│   here in large readable text    │
│                                   │
└──────────────────────────────────┘
```

The card never adds fabricated news facts.

---

## 15. Bengali + English Titles

The workflow installs Noto fonts:

```yaml
sudo apt-get update
sudo apt-get install -y fonts-noto-core
```

`facebook_poster.py` searches the Ubuntu font directories for Bengali-capable Noto fonts, allowing titles containing both **বাংলা** and **English** to render correctly on the card.

---

## 16. Facebook Caption

The caption is intentionally minimal:

```text
EXACT ARTICLE TITLE
ARTICLE URL
```

**Example:**

```text
Nine days after disaster, two pulled alive from Nepal hydropower tunnel
https://tbsnews.net/...
```

There is **no**:
- Generated description
- Full article text
- First comment
- "NEWS UPDATE" label
- "বিস্তারিত পড়ুন:" text
- Extra source paragraph

The source is already displayed on the photo-card itself.

---

## 17. Why the Article Title Appears Twice

| Location | Purpose |
|---|---|
| **Inside the photo-card** | Rendered directly onto the original article image |
| **Facebook caption** | Included as plain text, followed by the source URL |

This makes the post readable even if someone doesn't look closely at the image.

---

## 18. Facebook API

The program posts the generated JPEG to:

```text
/{PAGE_ID}/photos
```

with:

```text
caption
source
access_token
```

The Page access token is stored as a **GitHub Secret** and is never hard-coded in the repository.

---

## 19. Facebook Page

All automatic posts are published to this Facebook Page:

> **Facebook Page:** [View Page](https://www.facebook.com/profile.php?id=61593758413778)

The public Page URL is for documentation/navigation only — it is **not a secret** and does not replace the Page ID or Page Access Token used by the Graph API.

The automation uses:

```text
FACEBOOK_PAGE_ID
FACEBOOK_PAGE_ACCESS_TOKEN
```

**🔒 Security:** Never put the Page Access Token in the README or public repository.

---

## 20. GitHub Secrets

Navigate to:

```text
GitHub → Repository → Settings → Secrets and variables → Actions
```

Create the following secrets:

```text
SUPABASE_URL
SUPABASE_KEY
FACEBOOK_PAGE_ID
FACEBOOK_PAGE_ACCESS_TOKEN
```

The workflow passes these to Python as environment variables. **Never** put these values directly inside `scraper.py`, `database.py`, or `facebook_poster.py`, and never commit `.env`.

---

## 21. `.gitignore`

```gitignore
.env
__pycache__/
*.pyc
news.db
.venv/
venv/
```

---

## 22. `requirements.txt`

```text
fastapi
uvicorn
requests
beautifulsoup4
supabase
python-dotenv
Pillow
```

---

## 23. GitHub Actions Workflow

```yaml
name: Automatic News Scraper and Facebook Poster

on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch:

jobs:
  scrape-and-post:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y fonts-noto-core
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run News Scraper
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: |
          python scraper.py

      - name: Post News to Facebook
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          FACEBOOK_PAGE_ID: ${{ secrets.FACEBOOK_PAGE_ID }}
          FACEBOOK_PAGE_ACCESS_TOKEN: ${{ secrets.FACEBOOK_PAGE_ACCESS_TOKEN }}
          META_GRAPH_VERSION: "v25.0"
        run: |
          python facebook_poster.py
```

---

## 24. Posting Limit

For your **first test**, inside `facebook_poster.py`:

```python
MAX_POSTS_PER_RUN = 1
```

**After successful testing**, the recommended production value is:

```python
MAX_POSTS_PER_RUN = 3
```

Each workflow run can then publish up to 3 eligible articles. The Daily Star is never intentionally published.

---

## 25. What Happens During a Normal Run

```text
GitHub Actions starts
        ↓
scraper.py
        ↓
5 newspaper websites checked
        ↓
new articles saved to Supabase
        ↓
facebook_poster.py
        ↓
latest unposted eligible article selected
        ↓
The Daily Star excluded
        ↓
real article image resolved
        ↓
Pillow creates 1200×1200 card
        ↓
Facebook photo post
        ↓
Facebook returns post ID
        ↓
Supabase: facebook_posted = TRUE
```

---

## 26. What Happens if Image Download Fails

The system intentionally does **not** create a fake image.

```text
Image unavailable
        ↓
Card creation fails
        ↓
Facebook post is NOT created
        ↓
facebook_error is saved
        ↓
facebook_posted remains FALSE
```

This is intentional — the requirement is to always use the real article photo.

---

## 27. What Happens if Facebook Fails

```text
Card created
     ↓
Facebook API error
     ↓
facebook_posted remains FALSE
     ↓
facebook_error = error message
```

The article remains eligible for a later retry.

---

## 28. What Happens if the Same Article Is Encountered Again

Since `url` is unique:

```sql
url text unique not null
```

...the scraper never creates duplicate rows for the same article URL. Additionally, the Facebook poster only selects rows where:

```python
facebook_posted = False
```

```text
same URL → same database row → already posted? → TRUE → not posted again
```

---

## 29. Manual Testing

After pushing your code:

```text
GitHub → Actions → Automatic News Scraper and Facebook Poster → Run workflow
```

For the first test, set:

```python
MAX_POSTS_PER_RUN = 1
```

**Expected log output:**

```text
Starting Facebook poster...
Found 1 news.
Processing: ...
Downloading image: ...
✓ Image downloaded
✓ Modern photo card created
Posting photo card to Facebook...
✓ Facebook post successful
Facebook Post ID: ...
✓ Supabase: facebook_posted = TRUE
Finished. Posted: 1
```

---

## 30. Troubleshooting

<details>
<summary><strong>Problem: <code>Found 0 news</code></strong></summary>

Check Supabase. Possible reasons:
- All eligible articles already have `facebook_posted = TRUE`
- Only The Daily Star articles are available
- No recent news exists
- `image` is `NULL`

</details>

<details>
<summary><strong>Problem: <code>Image download failed</code></strong></summary>

Check the image URL. The publisher's image server may:
- Block automated requests
- Be temporarily unavailable
- Have a DNS problem
- Return a non-image response

The program will not invent a replacement image.

</details>

<details>
<summary><strong>Problem: <code>banner.png</code> appears</strong></summary>

The article page's actual image metadata was not successfully found. Check `og:image`, `twitter:image`, and JSON-LD in the article HTML.

</details>

<details>
<summary><strong>Problem: Bengali text appears as boxes</strong></summary>

Make sure the workflow contains `sudo apt-get install -y fonts-noto-core` and that `Pillow` is installed.

</details>

<details>
<summary><strong>Problem: Facebook API error</strong></summary>

Check `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`, and `META_GRAPH_VERSION`. Also verify the Page access token is still valid and that Meta isn't temporarily rate-limiting posts.

</details>

<details>
<summary><strong>Problem: Post succeeds but database is not updated</strong></summary>

Check `SUPABASE_URL` and `SUPABASE_KEY`, and inspect the workflow log after the Facebook success line.

</details>

---

## 31. Security

Never commit `.env`. Never put `FACEBOOK_PAGE_ACCESS_TOKEN` or `SUPABASE_KEY` inside source code — always use **GitHub Actions Secrets**.

For local development, use a `.env` file:

```env
SUPABASE_URL=...
SUPABASE_KEY=...
FACEBOOK_PAGE_ID=...
FACEBOOK_PAGE_ACCESS_TOKEN=...
```

Keep `.env` in `.gitignore` at all times.

---

## 32. Local Development

```bash
# Install dependencies
pip install -r requirements.txt
```

Create `.env`:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
FACEBOOK_PAGE_ID=your_page_id
FACEBOOK_PAGE_ACCESS_TOKEN=your_page_access_token
META_GRAPH_VERSION=v25.0
```

Run the scraper and poster:

```bash
python scraper.py
python facebook_poster.py
```

---

## 33. Why GitHub Actions Is Used Instead of a VPS

For this project's current workload, the automation is lightweight — it only needs to `start → scrape → database → create cards → post → finish`. There's no requirement for a continuously running server.

GitHub Actions provides hosted runners that execute workflow jobs on a schedule, so the local PC never needs to stay powered on.

---

## 34. Role of Vercel

If the project also contains a Vercel/FastAPI frontend or API, its role is separate from the scheduled Facebook pipeline:

```text
GitHub Actions
    │
    ├── scraper
    └── Facebook poster
             │
             ▼
        Supabase
             ▲
             │
        Vercel API
             │
             ▼
          Frontend
```

| Layer | Role |
|---|---|
| **GitHub Actions** | Automation |
| **Supabase** | Database |
| **Facebook Graph API** | Publishing |
| **Vercel** | Web/API interface (if enabled) |

---

## 35. Complete System Summary

```text
                  ┌──────────────────────┐
                  │    NEWS WEBSITES     │
                  │                      │
                  │ bdnews24             │
                  │ Prothom Alo          │
                  │ Daily Star           │
                  │ TBS                  │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │   GITHUB ACTIONS     │
                  │   Every ~5 minutes   │
                  └──────────┬───────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
             ┌─────────────┐   ┌───────────────┐
             │ scraper.py  │   │ Dependencies  │
             └──────┬──────┘   └───────────────┘
                    │
                    ▼
             ┌─────────────┐
             │  SUPABASE   │
             │ PostgreSQL  │
             └──────┬──────┘
                    │
                    │ unposted news
                    ▼
          ┌──────────────────────┐
          │ facebook_poster.py   │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │ Real Image Resolver  │
          │ og:image / JSON-LD   │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │       Pillow         │
          │ Modern Photo Card    │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │    FACEBOOK PAGE     │
          │                      │
          │ Photo Card           │
          │ Exact Title          │
          │ Article URL          │
          └──────────────────────┘
```

---

## 36. Final Expected Result

**For an eligible article:**

```text
ORIGINAL ARTICLE PHOTO
        +
   modern overlay
        +
   exact title
        +
   source badge
```

**Facebook caption:**

```text
Exact Article Title
https://source-article-url
```

**Database state:**

```text
facebook_posted    = TRUE
facebook_post_id   = ...
facebook_posted_at = ...
facebook_error     = NULL
```

**For The Daily Star:** Facebook publishing is skipped.
**For an article older than 1 day:** it is removed by the Supabase cleanup job.

---

## 37. Maintenance Checklist

- [ ] GitHub Actions runs
- [ ] Facebook Page posts
- [ ] Supabase `news` table
- [ ] `facebook_error` column
- [ ] Facebook access token validity
- [ ] Newspaper HTML structure (sites change layouts over time)
- [ ] Image extraction accuracy
- [ ] GitHub Actions workflow file

> If a newspaper changes its website's HTML structure, the scraper may need an update.

---

## 38. Current Project Status

### ✅ Implemented

- [x] Multi-source scraping
- [x] Supabase storage
- [x] Duplicate URL prevention
- [x] Recent-news filtering
- [x] 1-day database retention
- [x] GitHub Actions scheduling
- [x] Facebook Page publishing
- [x] Facebook posted-state tracking
- [x] Error tracking
- [x] The Daily Star Facebook exclusion
- [x] Real article-image detection
- [x] Banner/logo image rejection
- [x] Original-photo based card generation
- [x] Bengali + English title support
- [x] Minimal Facebook caption
- [x] Article URL in caption
- [x] No first-comment link
- [x] Maximum-post limit per workflow run

### 🎯 Recommended Final Setting

```python
MAX_POSTS_PER_RUN = 3
```

---

<div align="center">

*Built to keep readers informed — automatically, respectfully, and without republishing full articles.*

</div>