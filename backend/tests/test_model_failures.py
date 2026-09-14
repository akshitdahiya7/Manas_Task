"""Model load and inference failures must degrade to a clean 503."""
import pytest

from app import registry
from app.db_models import InferenceLog, ModelVersion


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    """Each test here manipulates artifacts, so start and end from a cold cache."""
    registry.clear_cache()
    yield
    registry.clear_cache()


def test_corrupt_artifact_returns_503(client, admin_headers, valid_record, db, tmp_path):
    """A corrupt model file is a service problem, not an unhandled crash."""
    corrupt = tmp_path / "corrupt.joblib"
    corrupt.write_bytes(b"this is not a joblib file")

    version = db.query(ModelVersion).filter(ModelVersion.version == "v1-rf").first()
    original_path = version.artifact_path
    version.artifact_path = str(corrupt)
    db.commit()

    try:
        response = client.post("/api/predict", json=valid_record, headers=admin_headers)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "model_load_failed"
    finally:
        version.artifact_path = original_path
        db.commit()


def test_missing_artifact_file_returns_503(client, admin_headers, valid_record, db):
    version = db.query(ModelVersion).filter(ModelVersion.version == "v1-rf").first()
    original_path = version.artifact_path
    version.artifact_path = "/nonexistent/path/model.joblib"
    db.commit()

    try:
        response = client.post("/api/predict", json=valid_record, headers=admin_headers)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "model_load_failed"
    finally:
        version.artifact_path = original_path
        db.commit()


def test_missing_scaler_returns_503(client, admin_headers, valid_record, db):
    version = db.query(ModelVersion).filter(ModelVersion.version == "v1-rf").first()
    original_path = version.scaler_path
    version.scaler_path = "/nonexistent/scaler.joblib"
    db.commit()

    try:
        response = client.post("/api/predict", json=valid_record, headers=admin_headers)
        assert response.status_code == 503
    finally:
        version.scaler_path = original_path
        db.commit()


def test_inference_exception_returns_503_and_is_logged(
    client, admin_headers, valid_record, db, monkeypatch
):
    """Simulate the model itself blowing up mid-prediction."""

    def explode(*args, **kwargs):
        raise RuntimeError("simulated model failure")

    # Warm the cache, then sabotage the loaded estimator.
    client.post("/api/predict", json=valid_record, headers=admin_headers)
    model, _ = registry._cache["v1-rf"]
    monkeypatch.setattr(model, "predict_proba", explode)

    before = db.query(InferenceLog).filter(InferenceLog.status == "error").count()
    response = client.post("/api/predict", json=valid_record, headers=admin_headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "inference_failed"
    # No stack trace leaks to the caller.
    assert "Traceback" not in response.text

    db.expire_all()
    after = db.query(InferenceLog).filter(InferenceLog.status == "error").count()
    assert after == before + 1, "the failed inference should still be logged"


def test_wrong_prediction_count_is_caught(client, admin_headers, valid_record, monkeypatch):
    """A model returning the wrong number of rows must not corrupt the response."""
    client.post("/api/predict", json=valid_record, headers=admin_headers)
    model, _ = registry._cache["v1-rf"]

    monkeypatch.setattr(model, "predict_proba", lambda X: [[0.5, 0.5], [0.4, 0.6]])

    response = client.post("/api/predict", json=valid_record, headers=admin_headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "inference_failed"


def test_unsupported_framework_returns_503(client, admin_headers, valid_record, db):
    version = db.query(ModelVersion).filter(ModelVersion.version == "v1-rf").first()
    original = version.framework
    version.framework = "pytorch-but-not-really"
    db.commit()

    try:
        response = client.post("/api/predict", json=valid_record, headers=admin_headers)
        assert response.status_code == 503
    finally:
        version.framework = original
        db.commit()


def test_registry_caches_loaded_artifacts(client, admin_headers, valid_record):
    assert not registry.is_cached("v1-rf")
    client.post("/api/predict", json=valid_record, headers=admin_headers)
    assert registry.is_cached("v1-rf")
