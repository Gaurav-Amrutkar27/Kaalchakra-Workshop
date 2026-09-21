"""Service layer for KaalChakra's LSTM learner sequence model."""
from __future__ import annotations
from typing import Any, Dict
from .lstm_model import load_lstm, predict_next_score, train_lstm
from .sequence_builder import build_training_sequences, get_user_sequence


def get_lstm_analysis(conn, user_id: int, base_dir: str) -> Dict[str, Any]:
    sequence, seq_meta = get_user_sequence(conn, user_id)
    X, y, user_ids = build_training_sequences(conn)
    if not X:
        return {
            'success': True,
            'model': 'LSTM Learner Sequence Model',
            'trained': False,
            'message': 'Not enough chronological learner activity yet. Complete or view at least two activities to create a sequence.',
            'trainingSamples': 0,
            'sequence': seq_meta,
            'prediction': None,
        }
    model, meta = load_lstm(base_dir)
    trained_now = False
    if model is None:
        meta = train_lstm(X, y, base_dir)
        model, _ = load_lstm(base_dir)
        trained_now = True
    predicted = predict_next_score(sequence, model, meta) if sequence else None
    actual_recent = None
    if sequence:
        actual_recent = round(float(sequence[-1][3]) * 100.0, 1)
    trend = 'insufficient data'
    if predicted is not None and actual_recent is not None:
        if predicted > actual_recent + 5:
            trend = 'expected to improve'
        elif predicted < actual_recent - 5:
            trend = 'may need attention'
        else:
            trend = 'stable'
    return {
        'success': True,
        'model': 'LSTM Learner Sequence Model',
        'modelVersion': meta.get('model_version'),
        'trained': True,
        'trainedNow': trained_now,
        'trainingSamples': len(X),
        'trainingLearners': len(set(user_ids)),
        'sequence': seq_meta,
        'prediction': {
            'nextScore': round(predicted, 1) if predicted is not None else None,
            'recentScore': actual_recent,
            'trend': trend,
        },
        'metrics': {
            'loss': round(float(meta.get('loss', 0)), 6),
            'mae': round(float(meta.get('mae', 0)), 6),
        },
        'dataQuality': {
            'warning': None if len(X) >= 30 else 'Prototype dataset: collect more chronological learner activity for a more reliable LSTM.'
        }
    }
