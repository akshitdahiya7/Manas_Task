"""Input validation and error handling.

Every case here asserts the exact status code and that the response is never an
unhandled 500 - that is the specific robustness requirement.
"""
import pytest


def test_missing_required_field_names_the_field(client, admin_headers, valid_record):
    valid_record.pop("Age")
    response = client.post("/api/predict", json=valid_record, headers=admin_headers)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert any(detail["field"] == "Age" for detail in body["error"]["details"])


def test_unexpected_field_is_rejected(client, admin_headers, valid_record):
    """extra="forbid" - unknown fields must not be silently ignored."""
    valid_record["SmokesCigars"] = 1
    response = client.post("/api/predict", json=valid_record, headers=admin_headers)

    assert response.status_code == 422
    fields = [d["field"] for d in response.json()["error"]["details"]]
    assert "SmokesCigars" in fields


@pytest.mark.parametrize(
    "field,value",
    [
        ("BMI", 500),
        ("BMI", 5),
        ("GenHlth", 9),
        ("GenHlth", 0),
        ("MentHlth", 45),
        ("Age", 99),
        ("Education", 0),
        ("Income", 12),
        ("HighBP", 2),
        ("Sex", -1),
    ],
)
def test_out_of_range_values_are_rejected(client, admin_headers, valid_record, field, value):
    valid_record[field] = value
    response = client.post("/api/predict", json=valid_record, headers=admin_headers)

    assert response.status_code == 422
    assert any(d["field"] == field for d in response.json()["error"]["details"])


@pytest.mark.parametrize("value", ["30", "abc", None, 30.5, True, [30]])
def test_wrong_types_are_not_coerced(client, admin_headers, valid_record, value):
    """No silent coercion: a numeric string or float must not become an int."""
    valid_record["BMI"] = value
    response = client.post("/api/predict", json=valid_record, headers=admin_headers)

    assert response.status_code == 422
    assert response.status_code != 500


def test_empty_body_is_rejected(client, admin_headers):
    response = client.post("/api/predict", json={}, headers=admin_headers)
    assert response.status_code == 422
    # One error per missing feature.
    assert len(response.json()["error"]["details"]) == 21


def test_empty_batch_is_rejected(client, admin_headers):
    response = client.post("/api/predict/batch", json={"records": []}, headers=admin_headers)
    assert response.status_code == 422


def test_batch_over_row_limit_returns_413(client, admin_headers, valid_record, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_batch_rows", 5)
    payload = {"records": [valid_record] * 6}
    response = client.post("/api/predict/batch", json=payload, headers=admin_headers)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_batch_with_one_invalid_record_is_rejected(client, admin_headers, valid_record):
    """A JSON batch is schema-validated as a whole, so a bad record fails it."""
    bad = {**valid_record, "BMI": 999}
    response = client.post(
        "/api/predict/batch", json={"records": [valid_record, bad]}, headers=admin_headers
    )
    assert response.status_code == 422
    assert any("1.BMI" in d["field"] for d in response.json()["error"]["details"])


# --- CSV specific -------------------------------------------------------


def test_csv_missing_columns_returns_400(client, admin_headers):
    csv_bytes = b"HighBP,HighChol\n1,0\n"
    response = client.post(
        "/api/predict/csv",
        files={"file": ("bad.csv", csv_bytes, "text/csv")},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"
    assert "missing required columns" in response.json()["error"]["message"]


def test_empty_csv_returns_400(client, admin_headers):
    response = client.post(
        "/api/predict/csv",
        files={"file": ("empty.csv", b"", "text/csv")},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_csv_header_without_rows_returns_400(client, admin_headers, valid_record):
    header = (",".join(valid_record) + "\n").encode()
    response = client.post(
        "/api/predict/csv",
        files={"file": ("header_only.csv", header, "text/csv")},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "no data rows" in response.json()["error"]["message"]


def test_non_utf8_file_returns_400(client, admin_headers):
    response = client.post(
        "/api/predict/csv",
        files={"file": ("binary.csv", b"\xff\xfe\x00\x01rubbish", "text/csv")},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_csv_reports_bad_rows_without_failing_the_upload(client, admin_headers, valid_record):
    """Partial failure: good rows are scored, bad rows are reported per row."""
    columns = list(valid_record)
    header = ",".join(columns) + "\n"
    good = ",".join(str(valid_record[c]) for c in columns) + "\n"

    out_of_range = dict(valid_record, BMI=500)
    row_bad_range = ",".join(str(out_of_range[c]) for c in columns) + "\n"

    not_a_number = dict(valid_record, GenHlth="high")
    row_bad_type = ",".join(str(not_a_number[c]) for c in columns) + "\n"

    missing_value = dict(valid_record, Age="")
    row_missing = ",".join(str(missing_value[c]) for c in columns) + "\n"

    payload = (header + good + row_bad_range + row_bad_type + row_missing).encode()
    response = client.post(
        "/api/predict/csv",
        files={"file": ("mixed.csv", payload, "text/csv")},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 4
    assert body["success_count"] == 1
    assert body["error_count"] == 3

    results = {r["row_index"]: r for r in body["results"]}
    assert results[0]["status"] == "success"
    assert results[1]["status"] == "error"
    assert any(e["field"] == "BMI" for e in results[1]["errors"])
    assert any(e["field"] == "GenHlth" for e in results[2]["errors"])
    assert any(e["field"] == "Age" for e in results[3]["errors"])


def test_csv_fractional_value_is_an_error(client, admin_headers, valid_record):
    columns = list(valid_record)
    header = ",".join(columns) + "\n"
    fractional = dict(valid_record, BMI="30.5")
    row = ",".join(str(fractional[c]) for c in columns) + "\n"

    response = client.post(
        "/api/predict/csv",
        files={"file": ("fractional.csv", (header + row).encode(), "text/csv")},
        headers=admin_headers,
    )
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "error"
    assert any(e["type"] == "not_an_integer" for e in result["errors"])


def test_oversized_upload_returns_413(client, admin_headers, valid_record, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    header = (",".join(valid_record) + "\n").encode()
    response = client.post(
        "/api/predict/csv",
        files={"file": ("big.csv", header * 10, "text/csv")},
        headers=admin_headers,
    )
    assert response.status_code == 413


def test_unknown_route_returns_404_in_the_standard_envelope(client, admin_headers):
    response = client.get("/api/not-a-real-endpoint", headers=admin_headers)
    assert response.status_code == 404
    assert "error" in response.json()
