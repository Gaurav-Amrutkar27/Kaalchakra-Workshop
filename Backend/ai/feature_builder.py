"""Build learner feature vectors for the KaalChakra autoencoder.

This module intentionally uses the existing database schema. It reads
player_progress.completed_modes plus XP/coins and does not create or alter
any tables.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

# KaalChakra currently plans five Class-6 chapters with up to five stages each.
# Keeping a fixed layout makes the neural network input size stable as learners
# progress through the game. Missing stages simply remain zero-valued features.
MAX_CHAPTERS = 5
MAX_STAGES_PER_CHAPTER = 5
MODES = ("THEORETICAL", "PUZZLE", "MYSTERY")
FEATURE_VERSION = "v1_5x5x3"


def _parse_json(value: Any, default: Any):
    if isinstance(value, str):
        try:
            value = json.loads(value or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            return default
    return value if value is not None else default


def _mode_name(value: str) -> str:
    value = str(value or "").upper().strip()
    aliases = {
        "MCQ": "THEORETICAL",
        "INFO": "THEORETICAL",
        "INFORMATION": "THEORETICAL",
        "THEORY": "THEORETICAL",
        "THEORETICAL": "THEORETICAL",
        "PUZZLE": "PUZZLE",
        "MYSTERY": "MYSTERY",
    }
    return aliases.get(value, value)


def _completion_candidates(chapter_id: int, stage_number: int, stage_id: int, mode: str) -> List[str]:
    mode = _mode_name(mode)
    lower = mode.lower()
    return [
        f"{chapter_id}-{stage_number}_{lower}",
        f"{chapter_id}_{lower}",
        f"{stage_id}_{lower}",
        f"{chapter_id}-{stage_number}_{mode}",
        f"{chapter_id}_{mode}",
        f"{stage_id}_{mode}",
    ]


def _is_completed(completed: Dict[str, Any], candidates: List[str]) -> bool:
    for key in candidates:
        if completed.get(key) is True or completed.get(key) == 1 or completed.get(key) == "true":
            return True
    return False


def _score_for(completed: Dict[str, Any], chapter_id: int, stage_number: int, stage_id: int, mode: str) -> float:
    scores = completed.get("_scores")
    if not isinstance(scores, dict):
        scores = {}
    mode = _mode_name(mode)
    canonical = f"{chapter_id}-{stage_number}_{mode.lower()}"
    for key in [canonical, f"{chapter_id}_{mode.lower()}", f"{stage_id}_{mode.lower()}"]:
        value = scores.get(key)
        if value is not None:
            try:
                return max(0.0, min(100.0, float(value)))
            except (TypeError, ValueError):
                pass
    # If an old progress record has completion but no score metadata, use the
    # current mode reward as a deterministic proxy for the behavior feature.
    rewards = {"THEORETICAL": 10.0, "PUZZLE": 15.0, "MYSTERY": 20.0}
    return rewards.get(mode, 0.0) if _is_completed(completed, _completion_candidates(chapter_id, stage_number, stage_id, mode)) else 0.0


def get_active_stage_map(conn) -> List[Dict[str, int]]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, chapter_id, stage_number
            FROM stages
            WHERE is_active=TRUE
            ORDER BY chapter_id, stage_number
        """)
        rows = cur.fetchall() or []
    return [
        {"id": int(r["id"]), "chapter_id": int(r["chapter_id"]), "stage_number": int(r["stage_number"])}
        for r in rows
        if 1 <= int(r["chapter_id"]) <= MAX_CHAPTERS and 1 <= int(r["stage_number"]) <= MAX_STAGES_PER_CHAPTER
    ]


def build_user_vector(progress: Dict[str, Any], stages: List[Dict[str, int]]) -> Tuple[List[float], Dict[str, Any]]:
    """Return a fixed-length [completion, score, aggregate] vector."""
    completed = _parse_json(progress.get("completed_modes"), {})
    if not isinstance(completed, dict):
        completed = {}

    completion_features: List[float] = []
    score_features: List[float] = []
    completed_count = 0
    score_sum = 0.0
    mode_counts = {m: 0 for m in MODES}

    by_slot = {(s["chapter_id"], s["stage_number"]): s for s in stages}
    for chapter_id in range(1, MAX_CHAPTERS + 1):
        for stage_number in range(1, MAX_STAGES_PER_CHAPTER + 1):
            stage = by_slot.get((chapter_id, stage_number))
            stage_id = int(stage["id"]) if stage else (chapter_id * 100 + stage_number)
            for mode in MODES:
                candidates = _completion_candidates(chapter_id, stage_number, stage_id, mode)
                done = _is_completed(completed, candidates) if stage else False
                score = _score_for(completed, chapter_id, stage_number, stage_id, mode) if stage else 0.0
                completion_features.append(1.0 if done else 0.0)
                score_features.append(score / 20.0)  # reward score scale to roughly 0..1
                if done:
                    completed_count += 1
                    mode_counts[mode] += 1
                    score_sum += score

    xp = max(0.0, float(progress.get("xp") or 0.0))
    coins = max(0.0, float(progress.get("coins") or 0.0))
    # Aggregate features are normalized for stable neural-network training.
    max_possible = MAX_CHAPTERS * MAX_STAGES_PER_CHAPTER * len(MODES)
    completion_ratio = completed_count / max_possible if max_possible else 0.0
    avg_score = (score_sum / completed_count) / 20.0 if completed_count else 0.0
    xp_signal = min(xp / 3000.0, 1.0)
    coin_signal = min(coins / 500.0, 1.0)
    puzzle_ratio = mode_counts["PUZZLE"] / (MAX_CHAPTERS * MAX_STAGES_PER_CHAPTER)
    mystery_ratio = mode_counts["MYSTERY"] / (MAX_CHAPTERS * MAX_STAGES_PER_CHAPTER)
    theoretical_ratio = mode_counts["THEORETICAL"] / (MAX_CHAPTERS * MAX_STAGES_PER_CHAPTER)

    vector = completion_features + score_features + [
        completion_ratio,
        avg_score,
        xp_signal,
        coin_signal,
        puzzle_ratio,
        mystery_ratio,
        theoretical_ratio,
    ]
    meta = {
        "completed_modes": completed_count,
        "max_modes": max_possible,
        "completion_ratio": completion_ratio,
        "average_score": avg_score * 20.0,
        "xp": xp,
        "coins": coins,
        "mode_completion": {
            "THEORETICAL": mode_counts["THEORETICAL"],
            "PUZZLE": mode_counts["PUZZLE"],
            "MYSTERY": mode_counts["MYSTERY"],
        },
        "feature_version": FEATURE_VERSION,
    }
    return vector, meta


def build_training_matrix(conn) -> Tuple[List[List[float]], List[int], List[Dict[str, Any]]]:
    """Build one vector per learner from existing player_progress records."""
    stages = get_active_stage_map(conn)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT user_id, xp, coins, completed_modes
            FROM player_progress
            ORDER BY user_id
        """)
        rows = cur.fetchall() or []

    matrix: List[List[float]] = []
    user_ids: List[int] = []
    metas: List[Dict[str, Any]] = []
    for row in rows:
        vector, meta = build_user_vector(row, stages)
        matrix.append(vector)
        user_ids.append(int(row["user_id"]))
        metas.append(meta)
    return matrix, user_ids, metas
