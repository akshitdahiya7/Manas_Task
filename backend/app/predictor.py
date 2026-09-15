"""Preprocessing and prediction."""
import hashlib
import json
import logging

import numpy as np
import pandas as pd

from app.db_models import ModelVersion
from app.errors import InferenceError
from app.features import FEATURE_ORDER
from app.registry import FRAMEWORK_KERAS, FRAMEWORK_SKLEARN, load

logger = logging.getLogger(__name__)

LABELS = {0: "No diabetes", 1: "Diabetes or prediabetes"}
DECISION_THRESHOLD = 0.5


def input_hash(record: dict) -> str:
    """Stable digest of one record. sort_keys keeps it independent of field order."""
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _to_frame(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=FEATURE_ORDER).astype("float64")


def _probabilities(model_version: ModelVersion, model, scaled: np.ndarray) -> np.ndarray:
    if model_version.framework == FRAMEWORK_SKLEARN:
        # classes_ is [0., 1.], so column 1 is P(diabetes).
        return np.asarray(model.predict_proba(scaled))[:, 1]

    if model_version.framework == FRAMEWORK_KERAS:
        # Single sigmoid unit: the output is already P(diabetes).
        return np.asarray(model.predict(scaled, verbose=0)).ravel()

    raise InferenceError(f"Unsupported framework '{model_version.framework}'")


def ensure_loaded(model_version: ModelVersion) -> None:
    """Load the artifacts up front so a cold load is not timed as inference."""
    load(model_version)


def predict(model_version: ModelVersion, records: list[dict]) -> list[tuple[int, float]]:
    """Run inference on validated records, returning (class, probability) per row."""
    if not records:
        return []

    model, scaler = load(model_version)
    try:
        frame = _to_frame(records)
        scaled = scaler.transform(frame)
        probabilities = _probabilities(model_version, model, scaled)
    except InferenceError:
        raise
    except Exception as exc:
        logger.exception("Inference failed for version %s", model_version.version)
        raise InferenceError(
            f"Model '{model_version.version}' failed during inference: {exc}"
        ) from exc

    if len(probabilities) != len(records):
        raise InferenceError(
            f"Model returned {len(probabilities)} predictions for {len(records)} rows"
        )

    results = []
    for probability in probabilities:
        probability = float(probability)
        if not np.isfinite(probability):
            raise InferenceError("Model returned a non-finite probability")
        results.append((int(probability >= DECISION_THRESHOLD), probability))
    return results


def label_for(predicted_class: int) -> str:
    return LABELS.get(predicted_class, "Unknown")
