from flask import Flask, request, jsonify, session, send_from_directory, send_file, redirect
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import os
import json
import re

from ir.retrieval import make_stage_passages, make_web_passages, make_textbook_passages, build_stage_text, rank_passages
from ir.recommender import recommend_stages
from ir.crawler import fetch_page, ALLOWED_DOMAINS
from ir.textbook import ensure_textbook_index, locate_textbook
from ai.learner_service import get_learner_profile
from ai.feature_builder import build_training_matrix
from ai.autoencoder import train_autoencoder
from ai.lstm_service import get_lstm_analysis
from ai.sequence_builder import build_training_sequences
from ai.lstm_model import train_lstm

EDUCATIONAL_SOURCES = {
    "world_history": {
        "name": "World History Encyclopedia",
        "seed_url": "https://www.worldhistory.org/india/",
        "domain": "worldhistory.org",
        "max_pages": 3,
    },
    "khan_history": {
        "name": "Khan Academy – World History",
        "seed_url": "https://www.khanacademy.org/humanities/world-history/world-history-beginnings/ancient-india",
        "domain": "khanacademy.org",
        "max_pages": 3,
    },
}

# --------------------------------
# Project Paths
# --------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(PROJECT_DIR, "Frontend")

app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path=""
)

app.secret_key = os.environ.get(
    "KAALCHAKRA_SECRET_KEY",
    "change-this-secret-key-in-production"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)


# --------------------------------
# Database Connection
# --------------------------------

def get_db_connection():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="",
        database="kaalchakra_db",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )


def ensure_content_columns():
    """Ensure the chapter metadata columns required by the DB-driven API exist."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'chapters'
                  AND COLUMN_NAME IN ('source_chapter_number', 'status')
            """)
            columns = {row['COLUMN_NAME'] for row in cur.fetchall()}

            if 'source_chapter_number' not in columns:
                cur.execute("""
                    ALTER TABLE chapters
                    ADD COLUMN source_chapter_number INT NULL
                    AFTER chapter_number
                """)

            if 'status' not in columns:
                cur.execute("""
                    ALTER TABLE chapters
                    ADD COLUMN status ENUM('AVAILABLE', 'COMING_SOON', 'ENDED')
                    NOT NULL DEFAULT 'AVAILABLE'
                    AFTER is_active
                """)
    finally:
        conn.close()


# --------------------------------
# Progress Table
# --------------------------------

def ensure_progress_table():

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS player_progress (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL UNIQUE,
                    xp INT NOT NULL DEFAULT 120,
                    coins INT NOT NULL DEFAULT 25,
                    lives INT NOT NULL DEFAULT 5,
                    current_chapter INT NOT NULL DEFAULT 1,
                    completed_modes JSON NOT NULL,
                    collected_relics JSON NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,

                    CONSTRAINT fk_progress_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
                )
            """)

    finally:
        conn.close()


# ============================================================
# INFORMATION RETRIEVAL ENGINE — UNITS IV, V & VI
# ============================================================

def ensure_ir_tables():
    """Create the small IR tables used by retrieval, crawling and recommendation."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_activity (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    stage_id INT NOT NULL,
                    activity_type VARCHAR(40) NOT NULL,
                    score INT NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_activity_user (user_id),
                    INDEX idx_activity_stage (stage_id),
                    CONSTRAINT fk_activity_user FOREIGN KEY (user_id)
                        REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT fk_activity_stage FOREIGN KEY (stage_id)
                        REFERENCES stages(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS web_sources (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    source_name VARCHAR(200) NOT NULL,
                    url VARCHAR(1000) NOT NULL,
                    domain VARCHAR(255) NOT NULL,
                    UNIQUE KEY uq_web_source_url (url(191)),
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS web_documents (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    source_id INT NOT NULL,
                    url VARCHAR(1000) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    UNIQUE KEY uq_web_document_url (url(191)),
                    content LONGTEXT NOT NULL,
                    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_web_source (source_id),
                    CONSTRAINT fk_web_document_source FOREIGN KEY (source_id)
                        REFERENCES web_sources(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS textbook_documents (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    book_page INT NOT NULL,
                    pdf_page INT NOT NULL,
                    chapter_number INT NOT NULL,
                    chapter_title VARCHAR(255) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    content LONGTEXT NOT NULL,
                    source_path VARCHAR(1000) NOT NULL,
                    UNIQUE KEY uq_textbook_page (book_page),
                    INDEX idx_textbook_chapter (chapter_number)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    query_text VARCHAR(500) NOT NULL,
                    results_count INT NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_search_user (user_id),
                    CONSTRAINT fk_search_user FOREIGN KEY (user_id)
                        REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
    finally:
        conn.close()


def _load_stage_documents():
    """Build searchable historical documents directly from the existing game database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    s.id,
                    s.chapter_id,
                    s.stage_number,
                    s.title,
                    s.description,
                    s.learning_objective
                FROM stages s
                WHERE s.is_active = TRUE
                ORDER BY s.chapter_id, s.stage_number
            """)
            stages = cur.fetchall()

            cur.execute("""
                SELECT
                    sg.stage_id,
                    sg.title,
                    sg.description,
                    sg.instructions,
                    sg.game_data
                FROM stage_games sg
                INNER JOIN game_modes gm ON gm.id = sg.game_mode_id
                WHERE sg.is_active = TRUE AND gm.is_active = TRUE
                ORDER BY sg.stage_id, sg.game_order
            """)
            games = cur.fetchall()
    finally:
        conn.close()

    by_stage = {int(s["id"]): [] for s in stages}
    for game in games:
        sid = int(game["stage_id"])
        if sid not in by_stage:
            continue
        data = game.get("game_data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {}
        by_stage[sid].append({
            "title": game.get("title") or "",
            "description": game.get("description") or "",
            "instructions": game.get("instructions") or "",
            "content": data.get("content", "") if isinstance(data, dict) else "",
            "text": data.get("text", "") if isinstance(data, dict) else "",
            "explanation": data.get("explanation", "") if isinstance(data, dict) else ""
        })

    for stage in stages:
        stage["game_data"] = by_stage.get(int(stage["id"]), [])
    return stages


@app.post("/api/ir/activity")
def record_ir_activity():
    """Record a stage view/completion so Unit VI can personalize recommendations."""
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401

    data = request.get_json(silent=True) or {}
    try:
        stage_id = int(data.get("stageId"))
    except (TypeError, ValueError):
        return jsonify(success=False, error="A valid stageId is required."), 400

    activity_type = str(data.get("activityType", "VIEWED")).upper().strip()
    if activity_type not in {"VIEWED", "COMPLETED"}:
        activity_type = "VIEWED"
    try:
        score = max(0, min(100, int(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM stages WHERE id=%s AND is_active=TRUE", (stage_id,))
            if not cur.fetchone():
                return jsonify(success=False, error="Stage not found."), 404
            cur.execute("""
                INSERT INTO user_activity (user_id, stage_id, activity_type, score)
                VALUES (%s, %s, %s, %s)
            """, (session["user_id"], stage_id, activity_type, score))
    finally:
        conn.close()
    return jsonify(success=True, message="Learning activity recorded.")


@app.get("/api/search")
def historical_search():
    """Search one combined history collection, returned in student-friendly sections."""
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401

    query = str(request.args.get("q", "")).strip()
    if len(query) < 2:
        return jsonify(success=False, error="Enter at least 2 characters to search."), 400

    # Make sure the supplied Class 6 textbook is available to search.
    conn = get_db_connection()
    try:
        ensure_textbook_index(conn, PROJECT_DIR, BASE_DIR)
    finally:
        conn.close()

    stages = _load_stage_documents()
    stage_passages = make_stage_passages(stages)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, book_page, pdf_page, chapter_number, chapter_title, title, content
                FROM textbook_documents
                ORDER BY book_page
            """)
            textbook_docs = cur.fetchall()
            cur.execute("""
                SELECT wd.id, wd.url, wd.title, wd.content
                FROM web_documents wd
                INNER JOIN web_sources ws ON ws.id = wd.source_id
                WHERE ws.is_active = TRUE
                ORDER BY wd.crawled_at DESC
            """)
            web_docs = cur.fetchall()
    finally:
        conn.close()

    # Refresh curated web sources only when none have been stored yet. The visible
    # "Update sources" control can be used later when the learner wants a refresh.
    if not web_docs:
        _crawl_all_sources()
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT wd.id, wd.url, wd.title, wd.content
                    FROM web_documents wd
                    INNER JOIN web_sources ws ON ws.id = wd.source_id
                    WHERE ws.is_active = TRUE
                    ORDER BY wd.crawled_at DESC
                """)
                web_docs = cur.fetchall()
        finally:
            conn.close()

    textbook_ranked = rank_passages(query, make_textbook_passages(textbook_docs), top_k=6)
    stage_ranked = rank_passages(query, stage_passages, top_k=6)
    web_ranked = rank_passages(query, make_web_passages(web_docs), top_k=6)

    def format_result(item):
        result = {
            "sourceType": item.get("source_type"),
            "title": item.get("title"),
            "passage": item.get("text", "")[:700],
            "score": item.get("score", 0),
            "relevancePercent": round(item.get("score", 0) * 100),
        }
        if item.get("source_type") == "textbook":
            result.update({
                "bookPage": item.get("book_page"),
                "pdfPage": item.get("pdf_page"),
                "chapterNumber": item.get("chapter_number"),
                "chapterTitle": item.get("chapter_title"),
            })
        elif item.get("source_type") == "stage":
            result.update({
                "stageId": item.get("stage_id"),
                "chapterId": item.get("chapter_id"),
                "stageNumber": item.get("stage_number"),
            })
        else:
            result.update({
                "documentId": item.get("document_id"),
                "url": item.get("url"),
                "sourceName": item.get("source_name") or "Educational source",
            })
        return result

    textbook_results = [format_result(x) for x in textbook_ranked]
    stage_results = [format_result(x) for x in stage_ranked]
    web_results = [format_result(x) for x in web_ranked]
    results = textbook_results + stage_results + web_results

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO search_history (user_id, query_text, results_count)
                VALUES (%s, %s, %s)
            """, (session["user_id"], query[:500], len(results)))
    finally:
        conn.close()

    return jsonify({
        "success": True,
        "query": query,
        "sections": {
            "textbook": textbook_results,
            "kaalchakra": stage_results,
            "exploreMore": web_results,
        },
        "results": results,
        "totalResults": len(results),
    })


@app.get("/api/recommendations")
def recommendations():
    """Unit VI: content-based recommendation from the student's learning activity."""
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401

    stages = _load_stage_documents()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT stage_id, activity_type, MAX(score) AS score
                FROM user_activity
                WHERE user_id=%s
                GROUP BY stage_id, activity_type
            """, (session["user_id"],))
            activity = cur.fetchall()
    finally:
        conn.close()

    seed_ids = []
    for row in activity:
        if row["activity_type"] in {"VIEWED", "COMPLETED"}:
            seed_ids.append(int(row["stage_id"]))
    seed_ids = list(dict.fromkeys(seed_ids))

    results = recommend_stages(stages, seed_ids, top_k=5)
    return jsonify({
        "success": True,
        "unit": "IR Unit VI — Content-Based Recommendation",
        "algorithm": "TF-IDF profile + Cosine Similarity",
        "basedOnStageIds": seed_ids,
        "coldStart": not bool(seed_ids),
        "results": results
    })


def _crawl_source(source_key):
    config = EDUCATIONAL_SOURCES.get(source_key)
    if not config:
        raise ValueError("Unknown educational source.")

    queue = [config["seed_url"]]
    visited = set()
    pages = []
    errors = []

    while queue and len(pages) < config["max_pages"]:
        url = queue.pop(0).split("#")[0]
        if url in visited:
            continue
        visited.add(url)
        try:
            page = fetch_page(url)
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)})
            continue
        if page["domain"] != config["domain"]:
            continue
        pages.append(page)
        for link in page.get("links", []):
            if link not in visited and len(queue) < 20:
                queue.append(link)

    if not pages:
        return {"sourceKey": source_key, "pagesCrawled": 0, "documentsStored": 0, "errors": errors}

    conn = get_db_connection()
    stored = 0
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO web_sources (source_name, url, domain)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    source_name=VALUES(source_name), domain=VALUES(domain), is_active=1
            """, (config["name"], config["seed_url"], config["domain"]))
            cur.execute("SELECT id FROM web_sources WHERE url=%s", (config["seed_url"],))
            source_id = cur.fetchone()["id"]
            for page in pages:
                cur.execute("""
                    INSERT INTO web_documents (source_id, url, title, content)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        source_id=VALUES(source_id), title=VALUES(title),
                        content=VALUES(content), crawled_at=CURRENT_TIMESTAMP
                """, (source_id, page["url"], page["title"], page["content"]))
                stored += 1
    finally:
        conn.close()
    return {"sourceKey": source_key, "pagesCrawled": len(pages), "documentsStored": stored, "errors": errors}


def _crawl_all_sources():
    results = []
    for source_key in EDUCATIONAL_SOURCES:
        try:
            results.append(_crawl_source(source_key))
        except Exception as exc:
            results.append({"sourceKey": source_key, "pagesCrawled": 0, "documentsStored": 0, "errors": [{"error": str(exc)}]})
    return results


@app.get("/api/crawler/sources")
def crawler_sources():
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401
    sources = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for key, config in EDUCATIONAL_SOURCES.items():
                cur.execute("""
                    SELECT COUNT(wd.id) AS document_count
                    FROM web_sources ws
                    LEFT JOIN web_documents wd ON wd.source_id = ws.id
                    WHERE ws.url=%s AND ws.is_active=TRUE
                """, (config["seed_url"],))
                count = int(cur.fetchone()["document_count"] or 0)
                sources.append({
                    "key": key,
                    "source_name": config["name"],
                    "url": config["seed_url"],
                    "document_count": count,
                })
    finally:
        conn.close()
    return jsonify(success=True, sources=sources)


@app.post("/api/crawler/run-all")
def run_all_crawlers():
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401
    results = _crawl_all_sources()
    return jsonify(success=True, sources=results)


# --------------------------------
# Frontend Pages
# --------------------------------

@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/login")
def login_page():
    return send_from_directory(FRONTEND_DIR, "login.html")


@app.get("/register")
def register_page():
    return send_from_directory(FRONTEND_DIR, "register.html")


@app.get("/textbook")
def textbook_page():
    pdf_path = locate_textbook(PROJECT_DIR, BASE_DIR)
    if not pdf_path:
        return "History6.pdf not found.", 404
    return send_file(str(pdf_path), mimetype="application/pdf", conditional=True)


@app.get("/dashboard")
def dashboard_page():

    if "user_id" not in session:
        return redirect("/login")

    return send_from_directory(FRONTEND_DIR, "dashboard.html")


# --------------------------------
# Authentication
# --------------------------------

@app.post("/api/auth/register")
def register():

    data = request.get_json(silent=True) or {}

    full_name = str(data.get("student_name", "")).strip()
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))
    confirm_password = str(
        data.get("confirm_password", "")
    )

    # Validation

    if not full_name:
        return jsonify(
            success=False,
            error="Full name is required."
        ), 400

    if not username:
        return jsonify(
            success=False,
            error="Username is required."
        ), 400

    if not email:
        return jsonify(
            success=False,
            error="Email is required."
        ), 400

    if not password:
        return jsonify(
            success=False,
            error="Password is required."
        ), 400

    if len(password) < 6:
        return jsonify(
            success=False,
            error="Password must be at least 6 characters."
        ), 400

    if password != confirm_password:
        return jsonify(
            success=False,
            error="Passwords do not match."
        ), 400

    if not re.match(
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        email
    ):
        return jsonify(
            success=False,
            error="Please enter a valid email address."
        ), 400

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT id
                FROM users
                WHERE username = %s
                   OR email = %s
                """,
                (username, email)
            )

            existing = cur.fetchone()

            if existing:
                return jsonify(
                    success=False,
                    error="Username or email already exists."
                ), 409

            password_hash = generate_password_hash(password)

            cur.execute(
                """
                INSERT INTO users
                (
                    username,
                    email,
                    password_hash,
                    full_name
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    username,
                    email,
                    password_hash,
                    full_name
                )
            )

        return jsonify(
            success=True,
            message="Registration successful."
        )

    finally:
        conn.close()


@app.post("/api/auth/login")
def login():

    data = request.get_json(silent=True) or {}

    username = str(
        data.get("username", "")
    ).strip()

    password = str(
        data.get("password", "")
    )

    if not username or not password:
        return jsonify(
            success=False,
            error="Username and password are required."
        ), 400

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    full_name,
                    username,
                    email,
                    password_hash,
                    is_active
                FROM users
                WHERE username = %s
                """,
                (username,)
            )

            user = cur.fetchone()

            if not user:

                return jsonify(
                    success=False,
                    error="Invalid username or password."
                ), 401

            if not user["is_active"]:

                return jsonify(
                    success=False,
                    error="This account is inactive."
                ), 403

            if not check_password_hash(
                user["password_hash"],
                password
            ):

                return jsonify(
                    success=False,
                    error="Invalid username or password."
                ), 401

            session.clear()

            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["username"] = user["username"]
            session["email"] = user["email"]

        return jsonify(
            success=True,
            message="Login successful."
        )

    finally:
        conn.close()


@app.get("/api/auth/me")
def me():

    if "user_id" not in session:

        return jsonify(
            success=False,
            error="Not authenticated."
        ), 401

    return jsonify(
        success=True,
        user={
            "id": session["user_id"],
            "full_name": session["full_name"],
            "username": session["username"],
            "email": session["email"]
        }
    )


@app.route("/api/auth/logout", methods=["POST", "GET"])
def logout():
    session.clear()

    return jsonify({
        "success": True,
        "message": "You have safely left KaalChakra."
    })


# --------------------------------
# Progress
# --------------------------------

def get_or_create_progress(user_id):

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT *
                FROM player_progress
                WHERE user_id = %s
                """,
                (user_id,)
            )

            progress = cur.fetchone()

            if progress:
                return progress

            completed_modes = {}
            collected_relics = []

            cur.execute(
                """
                INSERT INTO player_progress
                (
                    user_id,
                    xp,
                    coins,
                    lives,
                    current_chapter,
                    completed_modes,
                    collected_relics
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    120,
                    25,
                    5,
                    1,
                    json.dumps(completed_modes),
                    json.dumps(collected_relics)
                )
            )

            cur.execute(
                """
                SELECT *
                FROM player_progress
                WHERE user_id = %s
                """,
                (user_id,)
            )

            return cur.fetchone()

    finally:
        conn.close()


@app.get("/api/progress/load")
def load_progress():

    if "user_id" not in session:

        return jsonify(
            success=False,
            error="Not authenticated."
        ), 401

    progress = get_or_create_progress(
        session["user_id"]
    )

    raw_completed = progress.get("completed_modes") if progress else {}
    if isinstance(raw_completed, str):
        try:
            parsed_completed = json.loads(raw_completed or "{}")
        except json.JSONDecodeError:
            parsed_completed = {}
    else:
        parsed_completed = raw_completed or {}

    # Normalize legacy stage-id completion keys using the actual stages table.
    # This does not change the schema; it only makes the existing JSON data
    # compatible with the current chapter-stage UI.
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, chapter_id, stage_number
                FROM stages
                WHERE is_active=TRUE
            """)
            stage_rows = cur.fetchall() or []
        normalized_completed, changed = _normalize_completed_modes(parsed_completed, stage_rows)
        parsed_completed = normalized_completed
        if changed:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE player_progress SET completed_modes=%s WHERE user_id=%s",
                    (json.dumps(parsed_completed), session["user_id"])
                )
            conn.commit()
    finally:
        conn.close()

    # Keep legacy learner records consistent with the new fixed mode rewards
    # without changing the database schema. If a learner already has a mode
    # marked completed but an older build awarded less XP, top the XP up to
    # the baseline plus the documented one-time mode rewards. Never reduce a
    # learner's existing XP.
    reward_xp_by_mode = {
        "theoretical": 75,
        "info": 75,
        "puzzle": 100,
        "mystery": 125,
    }
    expected_bonus = 0
    seen_modes = set()
    pattern = re.compile(r"^(\d+)-(\d+)_(theoretical|info|puzzle|mystery)$", re.I)
    for key, value in parsed_completed.items():
        if not value or not isinstance(key, str):
            continue
        match = pattern.match(key)
        if not match:
            continue
        chapter, stage, mode = match.groups()
        mode = mode.lower()
        canonical_mode = "theoretical" if mode == "info" else mode
        canonical = (chapter, stage, canonical_mode)
        if canonical in seen_modes:
            continue
        seen_modes.add(canonical)
        expected_bonus += reward_xp_by_mode[mode]

    progress["completed_modes"] = parsed_completed
    current_xp = int(progress.get("xp") or 0)
    minimum_xp = 120 + expected_bonus
    if current_xp < minimum_xp and expected_bonus:
        progress["xp"] = minimum_xp
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE player_progress SET xp=%s WHERE user_id=%s",
                    (minimum_xp, session["user_id"])
                )
        finally:
            conn.close()

    progress["score"] = _score_total(parsed_completed)

    return jsonify(
        success=True,
        progress=progress
    )


@app.post("/api/progress/save")
def save_progress():

    if "user_id" not in session:

        return jsonify(
            success=False,
            error="Not authenticated."
        ), 401

    data = request.get_json(silent=True) or {}

    xp = max(
        0,
        int(data.get("xp", 120))
    )

    coins = max(
        0,
        int(data.get("coins", 25))
    )

    lives = max(
        0,
        min(5, int(data.get("lives", 5)))
    )

    current_chapter = max(
        1,
        int(data.get("currentChapter", 1))
    )

    completed_modes = data.get(
        "completedModes",
        {}
    )

    collected_relics = data.get(
        "collectedRelics",
        []
    )

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO player_progress
                (
                    user_id,
                    xp,
                    coins,
                    lives,
                    current_chapter,
                    completed_modes,
                    collected_relics
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)

                ON DUPLICATE KEY UPDATE
                    xp = VALUES(xp),
                    coins = VALUES(coins),
                    lives = VALUES(lives),
                    current_chapter = VALUES(current_chapter),
                    completed_modes = VALUES(completed_modes),
                    collected_relics = VALUES(collected_relics)
                """,
                (
                    session["user_id"],
                    xp,
                    coins,
                    lives,
                    current_chapter,
                    json.dumps(completed_modes),
                    json.dumps(collected_relics)
                )
            )

        return jsonify(
            success=True,
            message="Progress saved."
        )

    finally:
        conn.close()



# ============================================================
# GAME PROGRESS / REWARDS
# No database schema changes are used here. Completion state,
# per-mode score, and rewards are stored inside the existing
# player_progress.completed_modes JSON field.
# ============================================================

MODE_REWARDS = {
    "THEORETICAL": {"score": 10, "xp": 75, "coins": 5},
    "PUZZLE": {"score": 15, "xp": 100, "coins": 15},
    "MYSTERY": {"score": 20, "xp": 125, "coins": 20},
}

HINT_COSTS = {
    "THEORETICAL": 10,
    "PUZZLE": 20,
    "MYSTERY": 25,
}


def _normalise_mode(mode):
    mode = str(mode or "").strip().upper()
    if mode == "INFO":
        mode = "THEORETICAL"
    return mode


def _completion_keys(chapter_id, stage_number, stage_id, mode):
    """Return only stage-specific completion keys.

    IMPORTANT: never use ``stage_number_mode`` by itself. Stage numbers
    repeat in different chapters, so a key such as ``3_puzzle`` would make
    Chapter 5 Stage 3 appear completed just because Chapter 1 Stage 3 was
    completed.

    The existing JSON column is preserved; only the keys we read/write are
    made unambiguous.
    """
    mode = _normalise_mode(mode).lower()
    keys = [f"{chapter_id}-{stage_number}_{mode}"]

    # Stage IDs are globally unique in the existing schema, so this is also
    # safe and keeps compatibility with progress written by earlier builds.
    if stage_id is not None:
        keys.append(f"{stage_id}_{mode}")

    # Older builds used ``info`` for the theoretical/MCQ mode. Keep that
    # compatibility alias, but still make it chapter/stage-specific.
    if mode == "theoretical":
        keys.append(f"{chapter_id}-{stage_number}_info")
        if stage_id is not None:
            keys.append(f"{stage_id}_info")

    return list(dict.fromkeys(keys))


def _mode_completed(completed_modes, keys):
    return any(bool(completed_modes.get(key)) for key in keys)


def _normalize_completed_modes(completed_modes, stage_rows):
    """Normalize legacy completion keys into chapter-stage keys.

    The database schema is intentionally unchanged. Older builds stored some
    completions as ``<stage_id>_<mode>`` while the current UI uses
    ``<chapter_id>-<stage_number>_<mode>``. Because stage IDs are unique, the
    stage table gives us a safe way to translate those legacy aliases without
    accidentally marking the same stage number in another chapter complete.
    """
    if not isinstance(completed_modes, dict):
        completed_modes = {}

    by_id = {}
    for row in stage_rows or []:
        try:
            by_id[int(row["id"])] = (int(row["chapter_id"]), int(row["stage_number"]))
        except (KeyError, TypeError, ValueError):
            continue

    normalized = dict(completed_modes)
    changed = False
    pattern = re.compile(r"^(\d+)_(theoretical|info|puzzle|mystery)$", re.I)

    for key, value in list(completed_modes.items()):
        if not value or not isinstance(key, str):
            continue
        match = pattern.match(key)
        if not match:
            continue
        stage_id, mode = match.groups()
        mapping = by_id.get(int(stage_id))
        if not mapping:
            continue
        chapter_id, stage_number = mapping
        mode = mode.lower()
        canonical = f"{chapter_id}-{stage_number}_{mode}"
        if normalized.get(canonical) is not True:
            normalized[canonical] = True
            changed = True
        if mode == "info":
            canonical_theoretical = f"{chapter_id}-{stage_number}_theoretical"
            if normalized.get(canonical_theoretical) is not True:
                normalized[canonical_theoretical] = True
                changed = True

    return normalized, changed


def _score_total(completed_modes):
    """Calculate score from the existing completed_modes JSON.

    Newer records keep an explicit ``_scores`` map. Older records may only
    contain completion keys such as ``1-1_puzzle``. Support both formats so
    existing learners do not lose their score and no schema change is needed.
    """
    if not isinstance(completed_modes, dict):
        return 0

    scores = completed_modes.get("_scores")
    if isinstance(scores, dict) and scores:
        total = 0
        for value in scores.values():
            try:
                total += int(value)
            except (TypeError, ValueError):
                pass
        return total

    reward_scores = {
        "theoretical": 10,
        "info": 10,
        "puzzle": 15,
        "mystery": 20,
    }
    # Count only canonical chapter-stage keys. This avoids double-counting
    # the stage-id aliases written by the new completion endpoint.
    total = 0
    seen = set()
    pattern = re.compile(r"^(\d+)-(\d+)_(theoretical|info|puzzle|mystery)$", re.I)
    for key, value in completed_modes.items():
        if not value or not isinstance(key, str):
            continue
        match = pattern.match(key)
        if not match:
            continue
        chapter, stage, mode = match.groups()
        mode = mode.lower()
        canonical_mode = "theoretical" if mode == "info" else mode
        canonical = (chapter, stage, canonical_mode)
        if canonical in seen:
            continue
        seen.add(canonical)
        total += reward_scores[mode]
    return total


@app.post("/api/game/complete")
def complete_game_mode():
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401

    data = request.get_json(silent=True) or {}
    try:
        chapter_id = int(data.get("chapterId"))
        stage_number = int(data.get("stageNumber"))
    except (TypeError, ValueError):
        return jsonify(success=False, error="Valid chapterId and stageNumber are required."), 400

    mode = _normalise_mode(data.get("modeCode"))
    if mode not in MODE_REWARDS:
        return jsonify(success=False, error="Invalid game mode."), 400

    conn = get_db_connection()
    conn.autocommit(False)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.id AS stage_id, s.chapter_id, s.stage_number, s.title
                FROM stages s
                WHERE s.chapter_id=%s AND s.stage_number=%s AND s.is_active=TRUE
                LIMIT 1
            """, (chapter_id, stage_number))
            stage = cur.fetchone()
            if not stage:
                conn.rollback()
                return jsonify(success=False, error="Stage not found."), 404

            cur.execute("""
                SELECT xp, coins, completed_modes
                FROM player_progress
                WHERE user_id=%s
                LIMIT 1
                FOR UPDATE
            """, (session["user_id"],))
            progress = cur.fetchone()

            if not progress:
                completed_modes = {}
                cur.execute("""
                    INSERT INTO player_progress
                    (user_id, xp, coins, lives, current_chapter, completed_modes, collected_relics)
                    VALUES (%s, 120, 25, 5, 1, %s, %s)
                """, (session["user_id"], json.dumps(completed_modes), json.dumps([])))
                xp = 120
                coins = 25
            else:
                raw = progress.get("completed_modes")
                if isinstance(raw, str):
                    try:
                        completed_modes = json.loads(raw or "{}")
                    except json.JSONDecodeError:
                        completed_modes = {}
                else:
                    completed_modes = raw or {}
                if not isinstance(completed_modes, dict):
                    completed_modes = {}
                xp = int(progress.get("xp") or 0)
                coins = int(progress.get("coins") or 0)

            # Normalize any legacy alias for the current stage before checking
            # completion/reward state. This prevents a previously completed
            # mode from being rewarded again and makes score calculation agree
            # with the stage-selection UI.
            normalized_completed, _ = _normalize_completed_modes(
                completed_modes,
                [{"id": stage["stage_id"], "chapter_id": chapter_id, "stage_number": stage_number}]
            )
            completed_modes = normalized_completed

            keys = _completion_keys(chapter_id, stage_number, stage["stage_id"], mode)
            already_completed = _mode_completed(completed_modes, keys)
            reward = MODE_REWARDS[mode]
            canonical_key = f"{chapter_id}-{stage_number}_{mode.lower()}"

            if not already_completed:
                for key in keys:
                    completed_modes[key] = True
                scores = completed_modes.get("_scores")
                if not isinstance(scores, dict):
                    scores = {}
                scores[canonical_key] = reward["score"]
                completed_modes["_scores"] = scores
                xp += reward["xp"]
                coins += reward["coins"]

                cur.execute("""
                    UPDATE player_progress
                    SET xp=%s, coins=%s, completed_modes=%s
                    WHERE user_id=%s
                """, (xp, coins, json.dumps(completed_modes), session["user_id"]))

                # Keep the existing IR activity table in sync with completion.
                try:
                    cur.execute("""
                        INSERT INTO user_activity (user_id, stage_id, activity_type, score)
                        VALUES (%s, %s, 'COMPLETED', %s)
                    """, (session["user_id"], stage["stage_id"], reward["score"]))
                except Exception:
                    # IR must never prevent gameplay completion.
                    pass

            stage_keys = {}
            for check_mode in ("THEORETICAL", "PUZZLE", "MYSTERY"):
                stage_keys[check_mode] = _completion_keys(
                    chapter_id, stage_number, stage["stage_id"], check_mode
                )
            stage_completed = all(_mode_completed(completed_modes, k) for k in stage_keys.values())

            conn.commit()

            return jsonify(
                success=True,
                alreadyCompleted=already_completed,
                completionKey=canonical_key,
                xpAwarded=0 if already_completed else reward["xp"],
                coinsAwarded=0 if already_completed else reward["coins"],
                scoreAwarded=0 if already_completed else reward["score"],
                xp=xp,
                coins=coins,
                score=_score_total(completed_modes),
                stageCompleted=stage_completed,
                chapterId=chapter_id,
                stageNumber=stage_number,
                modeCode=mode,
            )
    except Exception as exc:
        conn.rollback()
        app.logger.exception("Game completion failed")
        return jsonify(success=False, error=str(exc)), 500
    finally:
        conn.close()


@app.post("/api/game/hint")
def use_game_hint():
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401

    data = request.get_json(silent=True) or {}
    try:
        chapter_id = int(data.get("chapterId"))
        stage_number = int(data.get("stageNumber"))
    except (TypeError, ValueError):
        return jsonify(success=False, error="Valid chapterId and stageNumber are required."), 400

    mode = _normalise_mode(data.get("modeCode"))
    if mode not in HINT_COSTS:
        return jsonify(success=False, error="Invalid game mode."), 400

    cost = HINT_COSTS[mode]
    conn = get_db_connection()
    conn.autocommit(False)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT title FROM stages
                WHERE chapter_id=%s AND stage_number=%s AND is_active=TRUE
                LIMIT 1
            """, (chapter_id, stage_number))
            stage = cur.fetchone()
            if not stage:
                conn.rollback()
                return jsonify(success=False, error="Stage not found."), 404

            cur.execute("SELECT coins FROM player_progress WHERE user_id=%s LIMIT 1 FOR UPDATE", (session["user_id"],))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return jsonify(success=False, error="Player progress not found."), 404

            coins = int(row["coins"] or 0)
            if coins < cost:
                conn.rollback()
                return jsonify(success=False, error=f"Not enough Civilization Coins. You need {cost} CC."), 400

            coins -= cost
            cur.execute("UPDATE player_progress SET coins=%s WHERE user_id=%s", (coins, session["user_id"]))
            conn.commit()

            generic_hints = {
                "THEORETICAL": "Review the key facts from this stage and focus on the exact historical concept asked in the question.",
                "PUZZLE": "Look for the clue that directly connects to the stage topic. Eliminate options that are unrelated to the historical evidence.",
                "MYSTERY": "Re-examine the evidence and connect the clues before choosing your final deduction.",
            }
            return jsonify(success=True, cost=cost, coins=coins, hint=generic_hints[mode])
    except Exception as exc:
        conn.rollback()
        app.logger.exception("Hint purchase failed")
        return jsonify(success=False, error=str(exc)), 500
    finally:
        conn.close()



@app.get("/api/ai/lstm-analysis")
def ai_lstm_analysis():
    """Analyze chronological learner activity using the LSTM model."""
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401
    conn = get_db_connection()
    try:
        result = get_lstm_analysis(conn, int(session["user_id"]), BASE_DIR)
        return jsonify(result)
    except RuntimeError as exc:
        return jsonify(success=False, error=str(exc), code="DL_DEPENDENCY_MISSING"), 503
    except Exception as exc:
        app.logger.exception("LSTM analysis failed")
        return jsonify(success=False, error=str(exc)), 500
    finally:
        conn.close()


@app.post("/api/ai/lstm/train")
def train_learner_lstm():
    """Retrain the LSTM from chronological user_activity records."""
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401
    conn = get_db_connection()
    try:
        X, y, user_ids = build_training_sequences(conn)
        if len(X) < 2:
            return jsonify(success=False, error="At least 2 chronological activity samples are required for LSTM training."), 400
        meta = train_lstm(X, y, BASE_DIR)
        return jsonify(
            success=True,
            model="LSTM Learner Sequence Model",
            trainingSamples=len(X),
            trainingLearners=len(set(user_ids)),
            sequenceLength=meta.get("sequence_length"),
            featureDimension=meta.get("feature_dim"),
            loss=meta.get("loss"),
            mae=meta.get("mae"),
            warning=None if len(X) >= 30 else "Prototype dataset: collect more chronological activity for a more reliable model."
        )
    except RuntimeError as exc:
        return jsonify(success=False, error=str(exc), code="DL_DEPENDENCY_MISSING"), 503
    except Exception as exc:
        app.logger.exception("LSTM training failed")
        return jsonify(success=False, error=str(exc)), 500
    finally:
        conn.close()


# --------------------------------
# Deep Learning — Learner Autoencoder
# --------------------------------

@app.get("/api/ai/learner-profile")
def ai_learner_profile():
    """Return the current learner's Autoencoder representation and insights.

    The endpoint reads the existing player_progress/stages tables only. It does
    not create or alter any database table.
    """
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401

    conn = get_db_connection()
    try:
        result = get_learner_profile(conn, int(session["user_id"]), BASE_DIR)
        return jsonify(result)
    except RuntimeError as exc:
        return jsonify(success=False, error=str(exc), code="DL_DEPENDENCY_MISSING"), 503
    except Exception as exc:
        app.logger.exception("Learner Autoencoder profile failed")
        return jsonify(success=False, error=str(exc)), 500
    finally:
        conn.close()


@app.post("/api/ai/autoencoder/train")
def train_learner_autoencoder():
    """Retrain the learner Autoencoder from existing progress records."""
    if "user_id" not in session:
        return jsonify(success=False, error="Not authenticated."), 401

    conn = get_db_connection()
    try:
        matrix, user_ids, _ = build_training_matrix(conn)
        if not matrix:
            return jsonify(success=False, error="No learner progress data is available for training."), 400
        meta = train_autoencoder(matrix, BASE_DIR)
        return jsonify(
            success=True,
            model="Deep Learning Autoencoder",
            trainingSamples=len(user_ids),
            modelVersion=meta.get("model_version"),
            inputDimension=meta.get("input_dim"),
            latentDimension=meta.get("latent_dim"),
            loss=meta.get("loss"),
            warning=None if len(user_ids) >= 10 else "Prototype dataset: collect more learners for a more reliable model."
        )
    except RuntimeError as exc:
        return jsonify(success=False, error=str(exc), code="DL_DEPENDENCY_MISSING"), 503
    except Exception as exc:
        app.logger.exception("Learner Autoencoder training failed")
        return jsonify(success=False, error=str(exc)), 500
    finally:
        conn.close()

# --------------------------------
# Database Test
# --------------------------------

@app.get("/api/test-db")
def test_db():

    try:

        conn = get_db_connection()

        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS result")
            result = cur.fetchone()

        conn.close()

        return jsonify(
            success=True,
            database="connected",
            result=result
        )

    except Exception as e:

        return jsonify(
            success=False,
            error=str(e)
        ), 500

# ============================================================
# DATABASE CONTENT API
# ============================================================

@app.route("/api/content/chapters", methods=["GET"])
def get_chapters():

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:

            # ------------------------------------------------
            # GET CHAPTERS
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    id,
                    chapter_number,
                    source_chapter_number,
                    title,
                    description,
                    icon,
                    status,
                    is_active
                FROM chapters
                WHERE is_active = TRUE
                ORDER BY chapter_number ASC
            """)

            chapter_rows = cursor.fetchall()


            # ------------------------------------------------
            # GET STAGES
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    id,
                    chapter_id,
                    stage_number,
                    title,
                    description,
                    learning_objective,
                    is_active
                FROM stages
                WHERE is_active = TRUE
                ORDER BY chapter_id ASC, stage_number ASC
            """)

            stage_rows = cursor.fetchall()


            # ------------------------------------------------
            # GET GAMES
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    sg.id,
                    sg.stage_id,
                    sg.game_mode_id,
                    sg.game_order,
                    sg.title,
                    sg.description,
                    sg.instructions,
                    sg.xp_reward,
                    sg.coin_reward,
                    sg.game_data,
                    sg.is_active,
                    gm.mode_code,
                    gm.mode_name,
                    gm.icon AS mode_icon
                FROM stage_games sg

                INNER JOIN game_modes gm
                    ON sg.game_mode_id = gm.id

                WHERE sg.is_active = TRUE
                  AND gm.is_active = TRUE

                ORDER BY
                    sg.stage_id ASC,
                    sg.game_order ASC
            """)

            game_rows = cursor.fetchall()


        conn.close()


        # ====================================================
        # CREATE STAGE → GAMES MAP
        # ====================================================

        stage_games = {}

        for game in game_rows:

            stage_id = game["stage_id"]

            if stage_id not in stage_games:
                stage_games[stage_id] = []


            game_data = game.get("game_data")


            # MySQL JSON may arrive as string or Python object
            if isinstance(game_data, str):

                try:
                    game_data = json.loads(game_data)

                except json.JSONDecodeError:

                    game_data = {}


            if not isinstance(game_data, dict):
                game_data = {}


            game_object = {

                "id": game["id"],

                "modeCode":
                    game["mode_code"],

                "modeName":
                    game["mode_name"],

                "title":
                    game["title"],

                "description":
                    game["description"],

                "instructions":
                    game["instructions"],

                "xpReward":
                    game["xp_reward"],

                "coinReward":
                    game["coin_reward"],

                "gameData":
                    game_data

            }


            stage_games[stage_id].append(
                game_object
            )


        # ====================================================
        # CREATE STAGE MAP
        # ====================================================

        stages_by_chapter = {}


        for stage in stage_rows:

            chapter_id = stage["chapter_id"]


            if chapter_id not in stages_by_chapter:

                stages_by_chapter[chapter_id] = []


            games = stage_games.get(
                    stage["id"],
                    []
                )


            # ----------------------------------------------
            # Convert DB games into engine mode structure
            # ----------------------------------------------

            topic = {

                "id":
                    stage["id"],

                "stageId":
                    stage["id"],

                "stageNumber":
                    stage["stage_number"],

                "title":
                    stage["title"],

                "icon":
                    "📜",

                "summary":
                    stage["description"] or "",

                "learningObjective":
                    stage["learning_objective"] or "",

                "description":
                    stage["description"] or "",

                "mystery":
                    None,

                "puzzle":
                    None,

                "theoretical":
                    None

            }


            for game in games:

                mode_code = game["modeCode"]


                game_data = game["gameData"]


                # Merge database metadata with game_data
                merged_game = {

                    **game_data,

                    "id":
                        game["id"],

                    "title":
                        game["title"] or
                        game_data.get("title"),

                    "description":
                        game["description"] or
                        game_data.get("description"),

                    "instructions":
                        game["instructions"] or
                        game_data.get("instructions"),

                    "reward": {

                        "xp":
                            game["xpReward"],

                        "coins":
                            game["coinReward"]

                    }

                }


                if mode_code == "MYSTERY":

                    topic["mystery"] = merged_game


                elif mode_code == "PUZZLE":

                    topic["puzzle"] = merged_game


                elif mode_code == "THEORETICAL":

                    topic["theoretical"] = merged_game


            stages_by_chapter[
                chapter_id
            ].append(topic)


        # ====================================================
        # CREATE FINAL CHAPTER OBJECTS
        # ====================================================

        chapters = []


        for chapter in chapter_rows:

            chapter_object = {

                "id":
                    chapter["id"],

                "number":
                    chapter["chapter_number"],

                "sourceChapterNumber":
                    chapter["source_chapter_number"],

                "title":
                    chapter["title"],

                "description":
                    chapter["description"] or "",

                "subtitle":
                    chapter["description"] or "",

                "icon":
                    chapter["icon"] or "📜",

                "portalIcon":
                    chapter["icon"] or "📜",

                "status":
                    chapter["status"],

                "comingSoon":
                    chapter["status"] ==
                    "COMING_SOON",

                "isComingSoon":
                    chapter["status"] ==
                    "COMING_SOON",

                "ended":
                    chapter["status"] ==
                    "ENDED",

                "isActive":
                    bool(
                        chapter["is_active"]
                    ),

                "topics":
                    stages_by_chapter.get(
                        chapter["id"],
                        []
                    )

            }


            chapters.append(
                chapter_object
            )


        # ====================================================
        # RESPONSE
        # ====================================================

        return jsonify({

            "success": True,

            "chapters": chapters,

            "totalChapters":
                len(chapters)

        })


    except Exception as e:

        print(
            "Content API error:",
            str(e)
        )

        return jsonify({

            "success": False,

            "message":
                "Could not load chapter content."

        }), 500




# --------------------------------
# Start Server
# --------------------------------

if __name__ == "__main__":

    ensure_progress_table()
    ensure_content_columns()
    ensure_ir_tables()
    try:
        conn = get_db_connection()
        try:
            print("Textbook index:", ensure_textbook_index(conn, PROJECT_DIR, BASE_DIR))
        finally:
            conn.close()
    except Exception as exc:
        print("Textbook index warning:", exc)

    print("\n===================================")
    print("      KAALCHAKRA FLASK SERVER")
    print("===================================")
    print("Server: http://127.0.0.1:5000")
    print("===================================\n")

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )
