"""Model registry, promotion, rollback and the RBAC that gates them."""
from app.db_models import STATUS_PRODUCTION, ModelVersion


def test_both_versions_are_registered(client, admin_headers):
    response = client.get("/api/models", headers=admin_headers)
    assert response.status_code == 200

    versions = {m["version"]: m for m in response.json()}
    assert {"v1-rf", "v2-mlp"} <= versions.keys()
    assert versions["v1-rf"]["framework"] == "sklearn"
    assert versions["v2-mlp"]["framework"] == "keras"
    assert versions["v1-rf"]["metrics"]["recall"] > 0


def test_active_version_is_reported(client, admin_headers):
    response = client.get("/api/models/active", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["status"] == STATUS_PRODUCTION


def test_promotion_switches_the_serving_model(client, admin_headers, valid_record, db):
    assert client.get("/api/models/active", headers=admin_headers).json()["version"] == "v1-rf"

    response = client.post(
        "/api/models/v2-mlp/promote",
        json={"reason": "Higher recall on the held-out set"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == STATUS_PRODUCTION

    prediction = client.post("/api/predict", json=valid_record, headers=admin_headers)
    assert prediction.json()["model_version"] == "v2-mlp"

    # Exactly one production model.
    db.expire_all()
    in_production = db.query(ModelVersion).filter(ModelVersion.status == STATUS_PRODUCTION).all()
    assert len(in_production) == 1
    assert in_production[0].version == "v2-mlp"


def test_promotion_is_recorded_in_history(client, admin_headers):
    client.post(
        "/api/models/v2-mlp/promote", json={"reason": "audit trail check"}, headers=admin_headers
    )
    history = client.get("/api/models/promotions", headers=admin_headers).json()

    promotions = [e for e in history if e["version"] == "v2-mlp" and e["action"] == "promote"]
    assert promotions, "promotion should be recorded"
    assert promotions[0]["performed_by"] == "admin"
    assert promotions[0]["to_status"] == STATUS_PRODUCTION
    assert promotions[0]["reason"] == "audit trail check"


def test_rollback_restores_the_previous_version(client, admin_headers, valid_record):
    client.post("/api/models/v2-mlp/promote", json={"reason": "deploy"}, headers=admin_headers)
    assert client.get("/api/models/active", headers=admin_headers).json()["version"] == "v2-mlp"

    response = client.post(
        "/api/models/rollback", json={"reason": "latency regression"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["version"] == "v1-rf"

    prediction = client.post("/api/predict", json=valid_record, headers=admin_headers)
    assert prediction.json()["model_version"] == "v1-rf"


def test_promoting_the_active_version_is_rejected(client, admin_headers):
    response = client.post(
        "/api/models/v1-rf/promote", json={"reason": "already live"}, headers=admin_headers
    )
    assert response.status_code == 400
    assert "already in production" in response.json()["error"]["message"]


def test_promoting_an_unknown_version_returns_404(client, admin_headers):
    response = client.post(
        "/api/models/v9-imaginary/promote", json={"reason": "nope"}, headers=admin_headers
    )
    assert response.status_code == 404


def test_promotion_does_not_mutate_artifacts(client, admin_headers, db):
    """Promotion changes status only; the files on disk are untouched."""
    before = {
        m.version: (m.artifact_path, m.scaler_path)
        for m in db.query(ModelVersion).all()
    }
    client.post("/api/models/v2-mlp/promote", json={"reason": "check"}, headers=admin_headers)

    db.expire_all()
    after = {
        m.version: (m.artifact_path, m.scaler_path)
        for m in db.query(ModelVersion).all()
    }
    assert before == after


# --- RBAC ---------------------------------------------------------------


def test_viewer_cannot_promote(client, viewer_headers):
    response = client.post(
        "/api/models/v2-mlp/promote", json={"reason": "should fail"}, headers=viewer_headers
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_viewer_cannot_rollback(client, viewer_headers):
    response = client.post("/api/models/rollback", json={"reason": "no"}, headers=viewer_headers)
    assert response.status_code == 403


def test_viewer_can_still_predict_and_read(client, viewer_headers, valid_record):
    assert client.post("/api/predict", json=valid_record, headers=viewer_headers).status_code == 200
    assert client.get("/api/models", headers=viewer_headers).status_code == 200
    assert client.get("/api/logs", headers=viewer_headers).status_code == 200


def test_requests_without_a_token_are_rejected(client, valid_record):
    assert client.post("/api/predict", json=valid_record).status_code == 401
    assert client.get("/api/models").status_code == 401
    assert client.post("/api/models/v2-mlp/promote", json={}).status_code == 401


def test_invalid_token_is_rejected(client, valid_record):
    headers = {"Authorization": "Bearer not.a.real.token"}
    response = client.post("/api/predict", json=valid_record, headers=headers)
    assert response.status_code == 401


def test_login_with_wrong_password_fails(client):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert "Incorrect username or password" in response.json()["error"]["message"]


def test_login_returns_the_role(client):
    response = client.post(
        "/api/auth/login", json={"username": "viewer", "password": "viewer-test-pw"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
