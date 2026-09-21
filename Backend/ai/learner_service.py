"""Application service around the learner autoencoder."""

from __future__ import annotations

from typing import Any, Dict

from .autoencoder import encode_and_reconstruct, load_or_train
from .feature_builder import (
    build_training_matrix,
    build_user_vector,
    get_active_stage_map,
)


# Minimum amount of gameplay required before showing
# an AI-generated learner profile.
MIN_PROFILE_MODES = 3


def get_learner_profile(
    conn,
    user_id: int,
    base_dir: str
) -> Dict[str, Any]:

    # ---------------------------------------------------------
    # 1. GET ONLY THE CURRENT PLAYER'S PROGRESS
    # ---------------------------------------------------------

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id, xp, coins, completed_modes
            FROM player_progress
            WHERE user_id=%s
            LIMIT 1
            """,
            (user_id,),
        )
        progress = cur.fetchone()

    if not progress:
        raise ValueError("Player progress not found.")

    # ---------------------------------------------------------
    # 2. BUILD CURRENT PLAYER VECTOR
    # ---------------------------------------------------------

    stages = get_active_stage_map(conn)

    vector, learner_meta = build_user_vector(
        progress,
        stages
    )

    completed_modes = int(
        learner_meta.get("completed_modes", 0)
    )

    # ---------------------------------------------------------
    # 3. TRAINING DATA
    #
    # This intentionally uses ALL learners.
    # These learners are for training the AI model,
    # NOT for calculating the current player's statistics.
    # ---------------------------------------------------------

    matrix, user_ids, _ = build_training_matrix(conn)

    if not matrix:
        raise ValueError(
            "No learner progress data is available "
            "for Autoencoder training."
        )

    # ---------------------------------------------------------
    # 4. LOAD / TRAIN AUTOENCODER
    # ---------------------------------------------------------

    model, model_meta, trained_now = load_or_train(
        matrix,
        base_dir
    )

    # ---------------------------------------------------------
    # 5. BASIC PLAYER INFORMATION
    # ---------------------------------------------------------

    learner_data = {
        "xp": learner_meta["xp"],
        "coins": learner_meta["coins"],
        "completedModes": completed_modes,
        "maxModes": learner_meta["max_modes"],
        "modeCompletion": learner_meta["mode_completion"],
    }

    # ---------------------------------------------------------
    # 6. NEW PLAYER / NOT ENOUGH DATA
    # ---------------------------------------------------------

    if completed_modes < MIN_PROFILE_MODES:

        return {
            "success": True,

            "model": "Deep Learning Autoencoder",

            "modelVersion": model_meta.get(
                "model_version"
            ),

            "featureVersion": learner_meta.get(
                "feature_version"
            ),

            "latentDimension": int(
                model_meta.get("latent_dim", 8)
            ),

            # No meaningful AI reconstruction score yet.
            "reconstructionError": None,

            "trainedNow": trained_now,

            # This is MODEL training information.
            "trainingSamples": len(matrix),

            "dataQuality": {
                "trainingSamples": len(matrix),
                "warning": (
                    None
                    if len(matrix) >= 10
                    else
                    "Prototype dataset: collect more "
                    "learner activity for a more reliable model."
                ),
            },

            "learner": learner_data,

            "insights": {
                "engagement": round(
                    min(
                        1.0,
                        0.65
                        * learner_meta["completion_ratio"]
                        + 0.35
                        * min(
                            learner_meta["average_score"] / 20.0,
                            1.0,
                        ),
                    )
                    * 100,
                    1,
                ),

                # Important:
                # Do NOT manufacture a consistency percentage
                # for a new learner.
                "completionConsistency": None,

                "averageScore": round(
                    learner_meta["average_score"],
                    1,
                ),

                "status": "insufficient_data",

                "message": (
                    "Play at least 3 activities to build "
                    "your personalized AI learning profile."
                ),
            },

            # Do not display latent representation yet.
            "latentFeatures": [],
        }

    # ---------------------------------------------------------
    # 7. ENOUGH DATA → GENERATE AI PROFILE
    # ---------------------------------------------------------

    latent, _, reconstruction_error = encode_and_reconstruct(
        vector,
        model,
        model_meta,
    )

    # ---------------------------------------------------------
    # 8. INTERPRETABLE PLAYER INDICATORS
    # ---------------------------------------------------------

    completion = learner_meta["completion_ratio"]

    avg_score = min(
        learner_meta["average_score"] / 20.0,
        1.0,
    )

    engagement = min(
        1.0,
        0.65 * completion
        + 0.35 * avg_score,
    )

    # This is an autoencoder-based reconstruction indicator.
    # It should not be interpreted as literal completion
    # consistency for the player.
    consistency = max(
        0.0,
        min(
            1.0,
            1.0 - reconstruction_error * 8.0,
        ),
    )

    # ---------------------------------------------------------
    # 9. RETURN PERSONALIZED PROFILE
    # ---------------------------------------------------------

    return {
        "success": True,

        "model": "Deep Learning Autoencoder",

        "modelVersion": model_meta.get(
            "model_version"
        ),

        "featureVersion": learner_meta.get(
            "feature_version"
        ),

        "latentDimension": int(
            model_meta.get("latent_dim", 8)
        ),

        "reconstructionError": round(
            reconstruction_error,
            6,
        ),

        "trainedNow": trained_now,

        # Number of learners used to train the model.
        "trainingSamples": len(matrix),

        "dataQuality": {
            "trainingSamples": len(matrix),
            "warning": (
                None
                if len(matrix) >= 10
                else
                "Prototype dataset: collect more "
                "learner activity for a more reliable model."
            ),
        },

        # ONLY CURRENT PLAYER
        "learner": learner_data,

        "insights": {
            "engagement": round(
                engagement * 100,
                1,
            ),

            "completionConsistency": round(
                consistency * 100,
                1,
            ),

            "averageScore": round(
                learner_meta["average_score"],
                1,
            ),

            "status": "active_profile",

            "message": (
                "Your AI learning profile is being "
                "generated from your gameplay."
            ),
        },

        "latentFeatures": [
            round(float(x), 5)
            for x in latent
        ],
    }