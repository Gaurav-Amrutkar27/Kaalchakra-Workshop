"""LSTM next-score model for KaalChakra learner activity sequences."""
from __future__ import annotations
import json
import os
from typing import Any, Dict, List, Tuple

MODEL_FILENAME = 'learner_lstm.keras'
META_FILENAME = 'learner_lstm_meta.json'
SEQUENCE_LENGTH = 10
FEATURE_DIM = 5


def _tf():
    try:
        import tensorflow as tf
        return tf
    except Exception as exc:
        raise RuntimeError('TensorFlow is required for the LSTM. Install requirements-dl.txt.') from exc


def model_paths(base_dir: str) -> Tuple[str, str]:
    model_dir = os.path.join(base_dir, 'models')
    os.makedirs(model_dir, exist_ok=True)
    return os.path.join(model_dir, MODEL_FILENAME), os.path.join(model_dir, META_FILENAME)


def train_lstm(X: List[List[List[float]]], y: List[float], base_dir: str) -> Dict[str, Any]:
    if len(X) < 2:
        raise ValueError('At least 2 chronological activity samples are required to train the LSTM.')
    tf = _tf()
    import numpy as np
    X_np = np.asarray(X, dtype='float32')
    y_np = np.asarray(y, dtype='float32')

    tf.keras.utils.set_random_seed(42)
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(SEQUENCE_LENGTH, FEATURE_DIM)),
        tf.keras.layers.Masking(mask_value=0.0),
        tf.keras.layers.LSTM(32, return_sequences=True),
        tf.keras.layers.Dropout(0.1),
        tf.keras.layers.LSTM(16),
        tf.keras.layers.Dense(8, activation='relu', name='sequence_embedding'),
        tf.keras.layers.Dense(1, activation='sigmoid', name='next_score')
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.001), loss='mse', metrics=['mae'])
    history = model.fit(X_np, y_np, epochs=35, batch_size=min(16, len(X_np)), verbose=0, shuffle=False)
    model_path, meta_path = model_paths(base_dir)
    model.save(model_path)
    meta = {
        'model_version': 'lstm_next_score_v1',
        'sequence_length': SEQUENCE_LENGTH,
        'feature_dim': FEATURE_DIM,
        'samples': int(len(X)),
        'loss': float(history.history['loss'][-1]),
        'mae': float(history.history['mae'][-1]),
    }
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    return meta


def load_lstm(base_dir: str):
    tf = _tf()
    model_path, meta_path = model_paths(base_dir)
    if not os.path.exists(model_path) or not os.path.exists(meta_path):
        return None, None
    model = tf.keras.models.load_model(model_path, compile=False)
    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    return model, meta


def predict_next_score(sequence: List[List[float]], model, meta: Dict[str, Any]) -> float:
    import numpy as np
    padded = [[0.0] * FEATURE_DIM for _ in range(SEQUENCE_LENGTH)]
    history = sequence[-SEQUENCE_LENGTH:]
    start = SEQUENCE_LENGTH - len(history)
    for i, step in enumerate(history):
        padded[start + i] = step
    pred = model.predict(np.asarray([padded], dtype='float32'), verbose=0)[0][0]
    return max(0.0, min(100.0, float(pred) * 100.0))
