"""Shared pytest fixtures.

Tests run against a throwaway SQLite file and the real model artifacts.
"""
import os
import tempfile
from pathlib import Path

import pytest

TEST_DB = Path(tempfile.gettempdir()) / "manas_test.db"

# Must happen before importing app: env vars take precedence over .env.
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin-test-pw"
os.environ["VIEWER_USERNAME"] = "viewer"
os.environ["VIEWER_PASSWORD"] = "viewer-test-pw"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
SAMPLE_CSV = BACKEND_DIR / "tests" / "data" / "sample_batch.csv"

VALID_RECORD = {
    "HighBP": 1,
    "HighChol": 1,
    "CholCheck": 1,
    "BMI": 42,
    "Smoker": 1,
    "Stroke": 1,
    "HeartDiseaseorAttack": 1,
    "PhysActivity": 0,
    "Fruits": 0,
    "Veggies": 0,
    "HvyAlcoholConsump": 0,
    "AnyHealthcare": 1,
    "NoDocbcCost": 1,
    "GenHlth": 5,
    "MentHlth": 25,
    "PhysHlth": 28,
    "DiffWalk": 1,
    "Sex": 1,
    "Age": 12,
    "Education": 2,
    "Income": 1,
}

LOW_RISK_RECORD = {
    **VALID_RECORD,
    "HighBP": 0,
    "HighChol": 0,
    "BMI": 22,
    "Smoker": 0,
    "Stroke": 0,
    "HeartDiseaseorAttack": 0,
    "PhysActivity": 1,
    "GenHlth": 1,
    "MentHlth": 0,
    "PhysHlth": 0,
    "DiffWalk": 0,
    "Age": 3,
    "Education": 6,
    "Income": 8,
}


@pytest.fixture(scope="session")
def client():
    """One app instance per session; the context manager runs startup."""
    if TEST_DB.exists():
        TEST_DB.unlink()

    with TestClient(app) as test_client:
        yield test_client

    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _token(client, username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'admin', 'admin-test-pw')}"}


@pytest.fixture(scope="session")
def viewer_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'viewer', 'viewer-test-pw')}"}


@pytest.fixture
def valid_record():
    return dict(VALID_RECORD)


@pytest.fixture
def sample_csv_bytes():
    return SAMPLE_CSV.read_bytes()


@pytest.fixture(autouse=True)
def _reset_production_model(client, admin_headers):
    """Put v1-rf back after tests that promote something else."""
    yield
    active = client.get("/api/models/active", headers=admin_headers)
    if active.status_code == 200 and active.json()["version"] != "v1-rf":
        client.post("/api/models/v1-rf/promote", json={"reason": "test cleanup"}, headers=admin_headers)


__all__ = ["Base", "VALID_RECORD", "LOW_RISK_RECORD"]
