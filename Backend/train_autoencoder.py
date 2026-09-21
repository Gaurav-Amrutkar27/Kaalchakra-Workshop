"""Train the KaalChakra learner Autoencoder from the existing MySQL database.

Run from Backend after installing requirements-dl.txt:
    python train_autoencoder.py
"""
from app import get_db_connection, BASE_DIR
from ai.feature_builder import build_training_matrix
from ai.autoencoder import train_autoencoder


def main():
    conn = get_db_connection()
    try:
        matrix, user_ids, _ = build_training_matrix(conn)
        if not matrix:
            raise SystemExit("No learner progress records found in player_progress.")
        meta = train_autoencoder(matrix, BASE_DIR)
        print("KaalChakra learner Autoencoder trained successfully.")
        print(f"Training samples : {len(user_ids)}")
        print(f"Input dimension  : {meta['input_dim']}")
        print(f"Latent dimension : {meta['latent_dim']}")
        print(f"Final MSE loss   : {meta['loss']:.6f}")
        if len(user_ids) < 10:
            print("WARNING: This is a prototype model. Collect more learner records for stronger results.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
