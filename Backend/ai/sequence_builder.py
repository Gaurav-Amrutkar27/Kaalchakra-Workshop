"""Build chronological learner activity sequences from the existing user_activity table.
No database changes are required.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime

MAX_SEQUENCE_LENGTH = 10
FEATURES_PER_STEP = 5


def _activity_code(value: Any) -> float:
    value = str(value or '').upper()
    return {'VIEWED': 0.25, 'COMPLETED': 1.0}.get(value, 0.5)


def fetch_user_activity(conn, user_id: int) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ua.stage_id, ua.activity_type, ua.score, ua.created_at,
                   s.chapter_id, s.stage_number
            FROM user_activity ua
            LEFT JOIN stages s ON s.id = ua.stage_id
            WHERE ua.user_id=%s
            ORDER BY ua.created_at ASC, ua.id ASC
        """, (user_id,))
        return cur.fetchall() or []


def _rows_to_steps(rows: List[Dict[str, Any]]) -> List[List[float]]:
    if not rows:
        return []
    steps: List[List[float]] = []
    previous_time = None
    for row in rows:
        chapter = float(row.get('chapter_id') or 0) / 5.0
        stage = float(row.get('stage_number') or 0) / 5.0
        score = max(0.0, min(100.0, float(row.get('score') or 0))) / 100.0
        activity = _activity_code(row.get('activity_type'))
        current_time = row.get('created_at')
        gap = 0.0
        if previous_time is not None and current_time is not None:
            try:
                seconds = max(0.0, (current_time - previous_time).total_seconds())
                gap = min(seconds / 86400.0, 1.0)
            except Exception:
                gap = 0.0
        previous_time = current_time
        # [chapter position, stage position, activity type, score, time gap]
        steps.append([chapter, stage, activity, score, gap])
    return steps


def get_user_sequence(conn, user_id: int) -> Tuple[List[List[float]], Dict[str, Any]]:
    rows = fetch_user_activity(conn, user_id)
    steps = _rows_to_steps(rows)
    if len(steps) > MAX_SEQUENCE_LENGTH:
        steps = steps[-MAX_SEQUENCE_LENGTH:]
    meta = {
        'activityCount': len(rows),
        'sequenceLength': len(steps),
        'maxSequenceLength': MAX_SEQUENCE_LENGTH,
    }
    return steps, meta


def build_training_sequences(conn) -> Tuple[List[List[List[float]]], List[float], List[int]]:
    """Create sliding-window next-score samples from all learners."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT user_id FROM user_activity ORDER BY user_id")
        users = [int(r['user_id']) for r in (cur.fetchall() or [])]

    X: List[List[List[float]]] = []
    y: List[float] = []
    user_ids: List[int] = []
    for uid in users:
        rows = fetch_user_activity(conn, uid)
        steps = _rows_to_steps(rows)
        if len(steps) < 2:
            continue
        # Use up to MAX_SEQUENCE_LENGTH previous events to predict the next score.
        for end in range(1, len(steps)):
            history = steps[max(0, end - MAX_SEQUENCE_LENGTH):end]
            target = steps[end][3]
            padded = [[0.0] * FEATURES_PER_STEP for _ in range(MAX_SEQUENCE_LENGTH)]
            start = MAX_SEQUENCE_LENGTH - len(history)
            for i, step in enumerate(history):
                padded[start + i] = step
            X.append(padded)
            y.append(float(target))
            user_ids.append(uid)
    return X, y, user_ids
