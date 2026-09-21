"""
KaalChakra textbook indexer.

Indexes the supplied Class VI History PDF into MySQL so the normal search
endpoint can rank textbook passages together with KaalChakra stages and
selected educational web sources.
"""
import os
import re
from pathlib import Path

BOOK_PAGES = [
    (1, "What, Where, How and When?"),
    (11, "On the Trail of the Earliest People"),
    (22, "From Gathering to Growing Food"),
    (32, "In the Earliest Cities"),
    (43, "What Books and Burials Tell Us"),
    (54, "Kingdoms, Kings and an Early Republic"),
    (65, "New Questions and Ideas"),
    (75, "Ashoka, the Emperor Who Gave Up War"),
    (87, "Vital Villages, Thriving Towns"),
    (99, "Traders, Kings and Pilgrims"),
    (111, "New Empires and Kingdoms"),
    (122, "Buildings, Paintings and Books"),
]
BOOK_END_PAGE = 136

def chapter_for_page(book_page):
    current = BOOK_PAGES[0]
    for start, title in BOOK_PAGES:
        if book_page >= start:
            current = (start, title)
        else:
            break
    chapter_number = BOOK_PAGES.index(current) + 1
    return chapter_number, current[1]

def locate_textbook(project_dir, base_dir):
    candidates = [
        Path(project_dir) / "History6.pdf",
        Path(project_dir) / "History6(1).pdf",
        Path(base_dir) / "History6.pdf",
        Path(base_dir) / "History6(1).pdf",
        Path(project_dir) / "Frontend" / "History6.pdf",
        Path(project_dir) / "Frontend" / "History6(1).pdf",
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None

def _extract_book_page(text):
    # The supplied NCERT PDF uses "1 /square6", "/square6 2", etc.
    patterns = [
        r"(?m)^\s*(\d{1,3})\s*/square6\b",
        r"(?m)^\s*/square6\s*(\d{1,3})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            number = int(match.group(1))
            if 1 <= number <= BOOK_END_PAGE:
                return number
    return None

def _clean_text(text):
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text).strip()
    # Remove the PDF's recurring page marker.
    text = re.sub(r"/square6", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()

def _make_title(text, chapter_title):
    # Prefer the first short heading-like line after cleaning.
    raw_lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines()]
    candidates = []
    for line in raw_lines:
        line = re.sub(r"/square6", "", line, flags=re.I).strip()
        if not line or re.fullmatch(r"\d{1,3}", line) or line.upper() == "OUR PASTS– I":
            continue
        if 2 <= len(line) <= 100:
            candidates.append(line)
    return candidates[0] if candidates else chapter_title

def index_textbook(conn, pdf_path):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Textbook indexing requires pypdf. Run: pip install pypdf"
        ) from exc

    reader = PdfReader(str(pdf_path))
    rows = []
    seen_pages = set()

    for pdf_page_number, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        book_page = _extract_book_page(raw)
        if book_page is None or book_page in seen_pages:
            continue
        cleaned = _clean_text(raw)
        if len(cleaned) < 80:
            continue

        chapter_number, chapter_title = chapter_for_page(book_page)
        title = chapter_title
        rows.append((
            book_page,
            pdf_page_number,
            chapter_number,
            chapter_title,
            title[:255],
            cleaned[:50000],
            str(pdf_path),
        ))
        seen_pages.add(book_page)

    with conn.cursor() as cur:
        cur.execute("DELETE FROM textbook_documents")
        cur.executemany(
            """
            INSERT INTO textbook_documents
            (book_page, pdf_page, chapter_number, chapter_title, title, content, source_path)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            rows,
        )
    return len(rows)

def ensure_textbook_index(conn, project_dir, base_dir, force=False):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM textbook_documents")
        count = int(cur.fetchone()["count"])

    if count > 0 and not force:
        return {"indexed": False, "pages": count, "reason": "already-indexed"}

    pdf_path = locate_textbook(project_dir, base_dir)
    if not pdf_path:
        return {
            "indexed": False,
            "pages": 0,
            "reason": "History6.pdf not found",
        }

    pages = index_textbook(conn, pdf_path)
    return {
        "indexed": True,
        "pages": pages,
        "reason": "indexed",
        "path": str(pdf_path),
    }
