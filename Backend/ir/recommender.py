from .retrieval import build_stage_text
from .text_processing import tfidf_vectors, cosine_similarity, query_vector


def recommend_stages(stages, activity_stage_ids, top_k=5):
    if not stages:
        return []
    texts = [build_stage_text(stage) for stage in stages]
    vectors, idf = tfidf_vectors(texts)
    id_set = {int(x) for x in activity_stage_ids}
    seed_indexes = [i for i, s in enumerate(stages) if int(s["id"]) in id_set]
    if not seed_indexes:
        return []

    profile = {}
    for idx in seed_indexes:
        for term, value in vectors[idx].items():
            profile[term] = profile.get(term, 0.0) + value
    for term in profile:
        profile[term] /= len(seed_indexes)

    results = []
    for idx, stage in enumerate(stages):
        if int(stage["id"]) in id_set:
            continue
        score = cosine_similarity(profile, vectors[idx])
        if score <= 0:
            continue
        results.append({
            "stageId": stage["id"],
            "chapterId": stage["chapter_id"],
            "stageNumber": stage["stage_number"],
            "title": stage["title"],
            "description": stage.get("description") or "",
            "score": round(min(1.0, score), 4),
            "matchPercent": round(min(100.0, score * 100), 1),
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
