"""Loading and caching of model artifacts.

Artifacts are immutable files on disk; the database decides which one is
active. Loaded objects are cached per version so a 21 MB forest is only read
once per process, and a load failure surfaces as a 503 rather than a crash.
"""
import logging
import threading

# Keras 3 can run a plain Dense network on its inference-only numpy backend,
# so the image does not need TensorFlow. This must be set before keras is
# imported anywhere, hence the assignment at module import time.
import os

os.environ.setdefault("KERAS_BACKEND", "numpy")

import joblib  # noqa: E402

from app.db_models import ModelVersion  # noqa: E402
from app.errors import ModelLoadError  # noqa: E402

logger = logging.getLogger(__name__)

FRAMEWORK_SKLEARN = "sklearn"
FRAMEWORK_KERAS = "keras"

# version string -> (model, scaler)
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
        # Re-check: another thread may have populated it while we waited.
        cached = _cache.get(key)
        if cached is not None:
            return cached

        logger.info("Loading model artifacts for version %s", key)
        model = _load_model_file(model_version.framework, model_version.artifact_path)
        scaler = _load_scaler(model_version.scaler_path)
        _cache[key] = (model, scaler)
        return model, scaler


def clear_cache() -> None:
    """Drop cached artifacts. Used by the tests."""
    with _lock:
        _cache.clear()


def is_cached(version: str) -> bool:
    return version in _cache
