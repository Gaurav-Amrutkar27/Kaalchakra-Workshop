"""TensorFlow/Keras autoencoder for KaalChakra learner behavior."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

import numpy as np

MODEL_VERSION = "kaalchakra-learner-autoencoder-v1"
LATENT_DIM = 8


def _tensorflow():
    try:
        import tensorflow as tf  # type: ignore
        return tf
    except ImportError as exc:
        raise RuntimeError(
            "TensorFlow is not installed. Run `pip install -r requirements-dl.txt` "
            "inside your virtual environment."
        ) from exc


def model_paths(base_dir: str) -> Tuple[str, str]:
    model_dir = os.path.join(base_dir, "models")
    os.makedirs(model_dir, exist_ok=True)
    return (
        os.path.join(model_dir, "learner_autoencoder.keras"),
        os.path.join(model_dir, "learner_autoencoder_meta.json"),
    )


def build_autoencoder(input_dim: int, latent_dim: int = LATENT_DIM):
    tf = _tensorflow()
    keras = tf.keras
    inputs = keras.Input(shape=(input_dim,), name="learner_features")
    x = keras.layers.Dense(64, activation="relu", name="encoder_dense_1")(inputs)
    x = keras.layers.Dense(24, activation="relu", name="encoder_dense_2")(x)
    latent = keras.layers.Dense(latent_dim, activation="linear", name="latent")(x)
    x = keras.layers.Dense(24, activation="relu", name="decoder_dense_1")(latent)
    x = keras.layers.Dense(64, activation="relu", name="decoder_dense_2")(x)
    outputs = keras.layers.Dense(input_dim, activation="sigmoid", name="reconstruction")(x)

    model = keras.Model(inputs, outputs, name="kaalchakra_learner_autoencoder")
    encoder = keras.Model(inputs, latent, name="kaalchakra_learner_encoder")
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=0.001), loss="mse")
    return model, encoder


def _normalize_matrix(matrix: List[List[float]]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(matrix, dtype=np.float32)
    if x.ndim != 2 or x.shape[0] == 0:
        raise ValueError("No learner feature vectors are available for training.")
    # Features are already mostly 0..1. Keep the transform simple and persist
    # it so inference uses exactly the same scaling.
    minimum = x.min(axis=0)
    maximum = x.max(axis=0)
    span = maximum - minimum
    span[span < 1e-8] = 1.0
    normalized = (x - minimum) / span
    return normalized.astype(np.float32), minimum.astype(np.float32), span.astype(np.float32)


def train_autoencoder(matrix: List[List[float]], base_dir: str, epochs: int = 80) -> Dict[str, Any]:
    tf = _tensorflow()
    x, minimum, span = _normalize_matrix(matrix)
    input_dim = int(x.shape[1])
    model, _ = build_autoencoder(input_dim)

    # With a small prototype dataset, use all available rows for reconstruction.
    # The warning is surfaced to the API instead of pretending this is a large
    # statistically representative learner population.
    batch_size = max(1, min(16, x.shape[0]))
    validation_split = 0.0 if x.shape[0] < 5 else 0.2
    history = model.fit(
        x,
        x,
        epochs=epochs,
        batch_size=batch_size,
        validation_split=validation_split,
        shuffle=True,
        verbose=0,
    )

    model_path, meta_path = model_paths(base_dir)
    model.save(model_path)
    final_loss = float(history.history["loss"][-1])
    meta = {
        "model_version": MODEL_VERSION,
        "input_dim": input_dim,
        "latent_dim": LATENT_DIM,
        "minimum": minimum.tolist(),
        "span": span.tolist(),
        "training_samples": int(x.shape[0]),
        "epochs": int(epochs),
        "loss": final_loss,
        "tensorflow_version": getattr(tf, "__version__", "unknown"),
    }
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def _load(base_dir: str):
    model_path, meta_path = model_paths(base_dir)
    if not (os.path.exists(model_path) and os.path.exists(meta_path)):
        return None, None
    tf = _tensorflow()
    model = tf.keras.models.load_model(model_path, compile=False)
    with open(meta_path, "r", encoding="utf-8") as fh:
        meta = json.load(fh)
    return model, meta


def load_or_train(matrix: List[List[float]], base_dir: str, epochs: int = 80):
    model, meta = _load(base_dir)
    input_dim = len(matrix[0]) if matrix else 0
    if model is not None and int(meta.get("input_dim", -1)) == input_dim:
        return model, meta, False
    meta = train_autoencoder(matrix, base_dir, epochs=epochs)
    model, _ = _load(base_dir)
    return model, meta, True


def encode_and_reconstruct(vector: List[float], model, meta: Dict[str, Any]):
    x = np.asarray(vector, dtype=np.float32).reshape(1, -1)
    minimum = np.asarray(meta["minimum"], dtype=np.float32)
    span = np.asarray(meta["span"], dtype=np.float32)
    x_norm = np.clip((x - minimum) / span, 0.0, 1.0)
    reconstruction = model.predict(x_norm, verbose=0)
    # Rebuild the encoder with the same model graph.
    tf = _tensorflow()
    encoder = tf.keras.Model(model.input, model.get_layer("latent").output)
    latent = encoder.predict(x_norm, verbose=0)[0]
    error = float(np.mean(np.square(x_norm - reconstruction)))
    return latent.tolist(), reconstruction[0].tolist(), error
