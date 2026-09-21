"""Train the KaalChakra learner LSTM from existing user_activity."""
from app import get_db_connection, BASE_DIR
from ai.sequence_builder import build_training_sequences
from ai.lstm_model import train_lstm
def main():
    conn=get_db_connection()
    try:
        seq,target,users=build_training_sequences(conn)
        if not seq: raise SystemExit("Not enough chronological user_activity records. Need at least 2 chronological activities for a learner.")
        meta=train_lstm(seq,target,BASE_DIR)
        print("KaalChakra learner LSTM trained successfully.")
        print(f"Training sequences : {len(seq)}")
        print(f"Sequence length    : {meta['sequence_length']}")
        print(f"Feature dimension   : {meta['feature_dim']}")
        print(f"Final MSE loss     : {meta['loss']:.6f}")
        if len(set(users))<10: print("WARNING: Prototype model; collect more learner activity/users for stronger results.")
    finally: conn.close()
if __name__=="__main__": main()
