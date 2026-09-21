from .text_processing import split_passages, tfidf_vectors, query_vector, cosine_similarity, tokenize


def build_stage_text(stage):
    parts = [stage.get("title", ""), stage.get("description", ""), stage.get("learning_objective", "")]
    game_data = stage.get("game_data") or []
    if isinstance(game_data, dict):
        game_data = [game_data]
    for game in game_data:
        if not isinstance(game, dict):
            continue
        for key in ("title", "description", "instructions", "content", "text", "question", "explanation", "success"):
            value = game.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(x) for x in value if isinstance(x, (str, int, float)))
    return "\n".join(str(p) for p in parts if p)


def rank_passages(query, passages, top_k=10):
    if not query.strip() or not passages:
        return []
    texts = [p["text"] for p in passages]
    vectors, idf = tfidf_vectors(texts)
    qvec = query_vector(query, idf)
    query_terms = set(tokenize(query))
    ranked = []
    for idx, passage in enumerate(passages):
        score = cosine_similarity(qvec, vectors[idx])
        terms = set(tokenize(passage["text"]))
        overlap = len(query_terms & terms) / max(len(query_terms), 1)
        phrase_boost = 0.08 if query.lower().strip() in passage["text"].lower() else 0.0
        final_score = min(1.0, score * 0.85 + overlap * 0.15 + phrase_boost)
        if final_score > 0:
            item = dict(passage)
            item["score"] = round(final_score, 4)
            ranked.append(item)
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]


def make_stage_passages(stages):
    passages = []
    for stage in stages:
        text = build_stage_text(stage)
        for passage in split_passages(text):
            passages.append({
                "source_type": "stage",
                "stage_id": stage.get("id"),
                "chapter_id": stage.get("chapter_id"),
                "stage_number": stage.get("stage_number"),
                "title": stage.get("title") or "Historical Stage",
                "url": None,
                "text": passage,
            })
    return passages


def make_web_passages(documents):
    passages = []
    for doc in documents:
        for passage in split_passages(doc.get("content", "")):
            passages.append({
                "source_type": "web",
                "document_id": doc.get("id"),
                "source_name": doc.get("source_name"),
                "title": doc.get("title") or "Educational Source",
                "url": doc.get("url"),
                "text": passage,
            })
    return passages


def make_textbook_passages(documents):
    passages = []
    for doc in documents:
        content = doc.get("content", "")
        for passage in split_passages(content):
            passages.append({
                "source_type": "textbook",
                "book_page": doc.get("book_page"),
                "pdf_page": doc.get("pdf_page"),
                "chapter_number": doc.get("chapter_number"),
                "chapter_title": doc.get("chapter_title"),
                "title": doc.get("title") or doc.get("chapter_title") or "History Textbook",
                "text": passage,
            })
    return passages
