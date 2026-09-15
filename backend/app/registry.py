"""Loading and caching of model artifacts.

Artifacts are immutable files on disk; the database decides which one is
active. Loaded objects are cached per version so a 21 MB forest is only read
once per process.
"""
import logging
import os
import threading

# Must be set before keras is imported anywhere.
os.environ.setdefault("KERAS_BACKEND", "numpy")

import joblib  # noqa: E402

from app.db_models import ModelVersion  # noqa: E402
from app.errors import ModelLoadError  # noqa: E402

logger = logging.getLogger(__name__)

FRAMEWORK_SKLEARN = "sklearn"
FRAMEWORK_KERAS = "keras"

_cache: dict[str, tuple[object, object]] = {}
_lock = threading.Lock()


def _load_scaler(path: str):
    try:
        return joblib.load(path)
    except Exception as exc:
        raise ModelLoadError(f"Could not load scaler from {path}: {exc}") from exc


def _load_model_file(framework: str, path: str):
    try:
        if framework == FRAMEWORK_SKLEARN:
            return joblib.load(path)
        if framework == FRAMEWORK_KERAS:
            import keras

            return keras.saving.load_model(path)
        raise ModelLoadError(f"Unsupported framework '{framework}'")
    except ModelLoadError:
        raise
    except Exception as exc:
        raise ModelLoadError(f"Could not load {framework} model from {path}: {exc}") from exc


def load(model_version: ModelVersion) -> tuple[object, object]:
    """Return (model, scaler) for a registered version, loading on first use."""
    key = model_version.version
    cached = _cache.get(key)
    if cached is not None:
        return cached

    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            return cached

        logger.info("Loading model artifacts for version %s", key)
        model = _load_model_file(model_version.framework, model_version.artifact_path)
        scaler = _load_scaler(model_version.scaler_path)
        _cache[key] = (model, scaler)
        return model, scaler


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def is_cached(version: str) -> bool:
    return version in _cache
