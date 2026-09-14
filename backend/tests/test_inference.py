"""Valid single and batch inference, including model version selection."""
from tests.conftest import LOW_RISK_RECORD


def test_single_prediction_returns_full_metadata(client, admin_headers, valid_record):
    response = client.post("/api/predict", json=valid_record, headers=admin_headers)
    assert response.status_code == 200

    body = response.json()
    assert body["predicted_class"] in (0, 1)
    assert 0.0 <= body["probability"] <= 1.0
    assert body["model_version"] == "v1-rf"
    assert body["preprocessing_version"] == "v1"
    # Enough metadata to reproduce the inference later.
    assert len(body["input_hash"]) == 64
    assert body["input"] == valid_record
    assert body["timestamp"]
    assert body["latency_ms"] >= 0
    assert body["inference_id"] > 0


def test_model_separates_high_and_low_risk(client, admin_headers, valid_record):
    """A sanity check that features reach the model in the right order."""
    high = client.post("/api/predict", json=valid_record, headers=admin_headers).json()
    low = client.post("/api/predict", json=LOW_RISK_RECORD, headers=admin_headers).json()

    assert high["probability"] > low["probability"]
    assert high["predicted_class"] == 1
    assert low["predicted_class"] == 0


def test_same_input_produces_same_hash(client, admin_headers, valid_record):
    first = client.post("/api/predict", json=valid_record, headers=admin_headers).json()
    reordered = dict(reversed(list(valid_record.items())))
    second = client.post("/api/predict", json=reordered, headers=admin_headers).json()

    assert first["input_hash"] == second["input_hash"]
    assert first["probability"] == second["probability"]


def test_batch_prediction_returns_one_result_per_record(client, admin_headers, valid_record):
    payload = {"records": [valid_record, LOW_RISK_RECORD, valid_record]}
    response = client.post("/api/predict/batch", json=payload, headers=admin_headers)
    assert response.status_code == 200

    body = response.json()
    assert body["row_count"] == 3
    assert body["success_count"] == 3
    assert body["error_count"] == 0
    assert len(body["results"]) == 3
    assert [r["row_index"] for r in body["results"]] == [0, 1, 2]
    assert all(r["status"] == "success" for r in body["results"])
    assert body["batch_id"] > 0


def test_csv_upload_scores_every_row(client, admin_headers, sample_csv_bytes):
    response = client.post(
        "/api/predict/csv",
        files={"file": ("sample_batch.csv", sample_csv_bytes, "text/csv")},
        headers=admin_headers,
    )
    assert response.status_code == 200

    body = response.json()
    assert body["row_count"] == 20
    assert body["success_count"] == 20
    assert body["error_count"] == 0
    assert all(r["predicted_class"] in (0, 1) for r in body["results"])


def test_csv_with_label_column_is_accepted(client, admin_headers, valid_record):
    """Exported data often still carries Diabetes_binary; it should be ignored."""
    header = ",".join(valid_record) + ",Diabetes_binary\n"
    row = ",".join(str(v) for v in valid_record.values()) + ",1\n"
    response = client.post(
        "/api/predict/csv",
        files={"file": ("with_label.csv", (header + row).encode(), "text/csv")},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["success_count"] == 1


def test_explicit_version_overrides_the_active_model(client, admin_headers, valid_record):
    response = client.post(
        "/api/predict?version=v2-mlp", json=valid_record, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["model_version"] == "v2-mlp"


def test_both_registered_frameworks_can_serve(client, admin_headers, valid_record):
    """The sklearn and keras loaders must both work."""
    for version in ("v1-rf", "v2-mlp"):
        response = client.post(
            f"/api/predict?version={version}", json=valid_record, headers=admin_headers
        )
        assert response.status_code == 200, f"{version} failed: {response.text}"
        assert response.json()["model_version"] == version
        assert 0.0 <= response.json()["probability"] <= 1.0


def test_unknown_version_returns_404(client, admin_headers, valid_record):
    response = client.post(
        "/api/predict?version=does-not-exist", json=valid_record, headers=admin_headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
