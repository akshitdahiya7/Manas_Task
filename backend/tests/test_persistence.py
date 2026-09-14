"""Inference results, batches and logs must survive in the database."""
from app.db_models import InferenceLog, UploadBatch


def test_single_inference_is_persisted_with_metadata(client, admin_headers, valid_record, db):
    response = client.post("/api/predict", json=valid_record, headers=admin_headers)
    inference_id = response.json()["inference_id"]

    log = db.query(InferenceLog).filter(InferenceLog.id == inference_id).first()
    assert log is not None
    assert log.request_type == "single"
    assert log.requested_by == "admin"
    assert log.status == "success"
    assert log.input_hash == response.json()["input_hash"]
    assert log.input_json == valid_record
    assert log.predicted_class == response.json()["predicted_class"]
    assert log.latency_ms is not None
    assert log.model_version.version == response.json()["model_version"]


def test_batch_rows_share_one_batch_id(client, admin_headers, valid_record, db):
    payload = {"records": [valid_record, valid_record, valid_record]}
    batch_id = client.post("/api/predict/batch", json=payload, headers=admin_headers).json()[
        "batch_id"
    ]

    logs = db.query(InferenceLog).filter(InferenceLog.batch_id == batch_id).all()
    assert len(logs) == 3
    assert sorted(log.row_index for log in logs) == [0, 1, 2]
    assert all(log.request_type == "batch" for log in logs)


def test_csv_upload_is_recorded_as_a_batch(client, admin_headers, sample_csv_bytes, db):
    response = client.post(
        "/api/predict/csv",
        files={"file": ("sample_batch.csv", sample_csv_bytes, "text/csv")},
        headers=admin_headers,
    )
    batch_id = response.json()["batch_id"]

    batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id).first()
    assert batch.filename == "sample_batch.csv"
    assert batch.source == "csv"
    assert batch.uploaded_by == "admin"
    assert batch.row_count == 20
    assert batch.success_count == 20


def test_logs_endpoint_returns_recent_inferences(client, admin_headers, valid_record):
    client.post("/api/predict", json=valid_record, headers=admin_headers)
    response = client.get("/api/logs?limit=5", headers=admin_headers)

    assert response.status_code == 200
    logs = response.json()
    assert len(logs) <= 5
    assert logs[0]["requested_by"]
    assert logs[0]["model_version"]
    # Newest first.
    assert logs == sorted(logs, key=lambda log: log["created_at"], reverse=True)


def test_logs_can_be_filtered_by_version_and_status(client, admin_headers, valid_record):
    client.post("/api/predict?version=v2-mlp", json=valid_record, headers=admin_headers)

    filtered = client.get("/api/logs?version=v2-mlp", headers=admin_headers).json()
    assert filtered, "expected at least one v2-mlp inference"
    assert all(log["model_version"] == "v2-mlp" for log in filtered)

    successes = client.get("/api/logs?status=success", headers=admin_headers).json()
    assert all(log["status"] == "success" for log in successes)


def test_batches_endpoint_lists_uploads(client, admin_headers, sample_csv_bytes):
    client.post(
        "/api/predict/csv",
        files={"file": ("history_check.csv", sample_csv_bytes, "text/csv")},
        headers=admin_headers,
    )
    batches = client.get("/api/batches", headers=admin_headers).json()

    assert any(b["filename"] == "history_check.csv" for b in batches)


def test_batch_detail_returns_every_row(client, admin_headers, valid_record):
    batch_id = client.post(
        "/api/predict/batch", json={"records": [valid_record, valid_record]}, headers=admin_headers
    ).json()["batch_id"]

    response = client.get(f"/api/batches/{batch_id}", headers=admin_headers)
    assert response.status_code == 200

    body = response.json()
    assert body["row_count"] == 2
    assert len(body["logs"]) == 2
    assert body["logs"][0]["input_json"] == valid_record


def test_unknown_batch_returns_404(client, admin_headers):
    response = client.get("/api/batches/999999", headers=admin_headers)
    assert response.status_code == 404


def test_mine_filter_scopes_to_the_current_user(client, viewer_headers, valid_record):
    client.post("/api/predict", json=valid_record, headers=viewer_headers)
    logs = client.get("/api/logs?mine=true", headers=viewer_headers).json()

    assert logs
    assert all(log["requested_by"] == "viewer" for log in logs)


def test_metrics_summary_reports_aggregates(client, admin_headers, valid_record):
    client.post("/api/predict", json=valid_record, headers=admin_headers)
    response = client.get("/api/metrics/summary", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_inferences"] > 0
    assert body["inferences_last_24h"] > 0
    assert 0.0 <= body["error_rate"] <= 1.0
    assert body["latency_ms"]["avg"] is not None
    assert body["latency_ms"]["p95"] >= body["latency_ms"]["p50"]
    assert set(body["prediction_distribution"]) == {"negative", "positive"}
    assert body["drift"]["status"] in {"ok", "alert", "no_data"}
    assert any(entry["version"] for entry in body["by_version"])


def test_health_endpoint_reports_database_connectivity(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True}
