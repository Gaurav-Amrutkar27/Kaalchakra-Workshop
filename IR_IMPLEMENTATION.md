# KaalChakra IR Extension

This update adds the three concepts written in the project form:

- **IR Unit IV:** Passage Retrieval + Ranking
- **IR Unit V:** Web Crawler
- **IR Unit VI:** Content-Based Recommendation

## Run

1. Activate the Python environment used by the project.
2. Install the two new crawler dependencies if needed:

```powershell
pip install requests beautifulsoup4
```

3. If your existing database is already populated, you can run `kaalchakra_ir_migration.sql` once. The Flask startup migration also creates the new IR tables automatically. For a fresh database, the updated `kaalchakra_db.sql` already contains them.
4. Start `Backend/app.py`.
5. Log in and open **HISTORICAL KNOWLEDGE** from the dashboard.

## Features

### Unit IV
The Passage Search tab searches existing KaalChakra stage/game content and crawled web content. It uses TF-IDF vectors, cosine similarity, keyword overlap and a small exact-phrase boost, then returns the highest-ranked passages.

### Unit V
The Web Explorer tab accepts a public HTTP/HTTPS page and performs a focused same-domain crawl of up to 3 pages. Requests downloads the HTML and BeautifulSoup extracts headings, paragraphs and list items. Extracted pages are stored in `web_documents`.

### Unit VI
Stage views and completions are recorded in `user_activity`. The recommendation engine builds a TF-IDF profile from the learner's viewed/completed stages and recommends unvisited stages using cosine similarity.

## New API endpoints

- `GET /api/search?q=...`
- `POST /api/ir/activity`
- `GET /api/recommendations`
- `GET /api/crawler/sources`
- `POST /api/crawler/run`

## New database tables

- `user_activity`
- `web_sources`
- `web_documents`
- `search_history`
