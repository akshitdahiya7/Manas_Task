"""Inference endpoints: single record, JSON batch and CSV upload."""
import csv
import io
import logging
import time

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.db_models import InferenceLog, ModelVersion, UploadBatch, User, utcnow
from app.errors import BadRequestError, PayloadTooLargeError
from app.features import FEATURE_ORDER, PREPROCESSING_VERSION, TARGET_COLUMN
from app.predictor import ensure_loaded, input_hash, label_for, predict
from app.schemas import (
    BatchRequest,
    BatchResponse,
    PatientFeatures,
    PredictionResponse,
    RowResult,
)
from app.security import get_current_user
from app.services import resolve_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["inference"])


def flatten_errors(exc: ValidationError) -> list[dict]:
    """Flatten pydantic errors to one entry per field."""
    return [
        {
            "field": ".".join(str(part) for part in err["loc"]) or "body",
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]


@router.post("/predict", response_model=PredictionResponse)
def predict_single(
    payload: PatientFeatures,
    version: str | None = Query(None, description="Model version; defaults to the active one"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Predict for one patient record."""
    model_version = resolve_model(db, version)
    record = payload.model_dump()
    digest = input_hash(record)

    # Outside the timer so latency measures inference, not disk IO.
    ensure_loaded(model_version)

    started = time.perf_counter()
    try:
        predicted_class, probability = predict(model_version, [record])[0]
    except Exception as exc:
        _log_failure(db, model_version, user, record, digest, exc)
        raise
    latency_ms = (time.perf_counter() - started) * 1000

    log = InferenceLog(
        model_version_id=model_version.id,
        requested_by=user.username,
        request_type="single",
        input_json=record,
        input_hash=digest,
        predicted_class=predicted_class,
        probability=probability,
        latency_ms=latency_ms,
        status="success",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return PredictionResponse(
        inference_id=log.id,
        predicted_class=predicted_class,
        predicted_label=label_for(predicted_class),
        probability=probability,
        model_version=model_version.version,
        preprocessing_version=PREPROCESSING_VERSION,
        timestamp=log.created_at,
        input_hash=digest,
        latency_ms=latency_ms,
        input=record,
    )


def _log_failure(db, model_version, user, record, digest, exc) -> None:
    """Log a failed inference before it becomes an error response."""
    db.rollback()
    db.add(
        InferenceLog(
            model_version_id=model_version.id,
            requested_by=user.username,
            request_type="single",
            input_json=record,
            input_hash=digest,
            status="error",
            error_message=str(exc)[:1000],
        )
    )
    db.commit()


@router.post("/predict/batch", response_model=BatchResponse)
def predict_batch(
    payload: BatchRequest,
    version: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Predict for a JSON array of records."""
    if len(payload.records) > settings.max_batch_rows:
        raise PayloadTooLargeError(
            f"Batch has {len(payload.records)} rows; the limit is {settings.max_batch_rows}"
        )

    model_version = resolve_model(db, version)
    records = [record.model_dump() for record in payload.records]
    return _run_batch(
        db=db,
        user=user,
        model_version=model_version,
        rows=[(index, record, None) for index, record in enumerate(records)],
        filename=f"json-batch-{utcnow():%Y%m%d-%H%M%S}",
        source="json",
    )


@router.post("/predict/csv", response_model=BatchResponse)
def predict_csv(
    file: UploadFile = File(...),
    version: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Predict for every row of an uploaded CSV.

    Rows are validated individually: a bad row is reported in the response
    rather than failing the whole upload.
    """
    raw = file.file.read()
    if len(raw) > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            f"File is {len(raw)} bytes; the limit is {settings.max_upload_bytes}"
        )
    if not raw.strip():
        raise BadRequestError("The uploaded file is empty")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise BadRequestError("File is not valid UTF-8 text; expected a CSV")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise BadRequestError("Could not read a header row from the CSV")

    # Exported data often still carries the label column; ignore it.
    headers = [h.strip() for h in reader.fieldnames if h and h.strip() != TARGET_COLUMN]
    missing = [name for name in FEATURE_ORDER if name not in headers]
    if missing:
        raise BadRequestError(
            f"CSV is missing required columns: {', '.join(missing)}",
            details=[{"field": name, "message": "required column missing"} for name in missing],
        )

    rows = []
    for index, raw_row in enumerate(reader):
        cleaned, errors = _clean_csv_row(raw_row)
        rows.append((index, cleaned, errors))

    if not rows:
        raise BadRequestError("The CSV has a header but no data rows")
    if len(rows) > settings.max_batch_rows:
        raise PayloadTooLargeError(
            f"CSV has {len(rows)} rows; the limit is {settings.max_batch_rows}"
        )

    model_version = resolve_model(db, version)
    return _run_batch(
        db=db,
        user=user,
        model_version=model_version,
        rows=rows,
        filename=file.filename or "upload.csv",
        source="csv",
    )


def _clean_csv_row(raw_row: dict) -> tuple[dict | None, list[dict] | None]:
    """Parse one CSV row of strings into validated integers.

    Only exact integers are accepted: "30" is fine, "30.5" and "abc" are errors
    rather than something to round.
    """
    parsed: dict = {}
    errors: list[dict] = []

    for name in FEATURE_ORDER:
        value = (raw_row.get(name) or "").strip()
        if value == "":
            errors.append({"field": name, "message": "value is missing", "type": "missing"})
            continue
        try:
            number = float(value)
        except ValueError:
            errors.append(
                {
                    "field": name,
                    "message": f"{value!r} is not a number",
                    "type": "not_a_number",
                }
            )
            continue
        if not number.is_integer():
            errors.append(
                {
                    "field": name,
                    "message": f"{value!r} is not a whole number",
                    "type": "not_an_integer",
                }
            )
            continue
        parsed[name] = int(number)

    if errors:
        return None, errors

    try:
        return PatientFeatures(**parsed).model_dump(), None
    except ValidationError as exc:
        return None, flatten_errors(exc)


def _run_batch(db, user, model_version: ModelVersion, rows, filename: str, source: str):
    """Score the valid rows and persist the outcome of every row."""
    valid = [(index, record) for index, record, errors in rows if errors is None]

    ensure_loaded(model_version)

    started = time.perf_counter()
    predictions = predict(model_version, [record for _, record in valid])
    latency_ms = (time.perf_counter() - started) * 1000
    per_row_latency = latency_ms / len(valid) if valid else 0.0

    batch = UploadBatch(
        filename=filename,
        source=source,
        uploaded_by=user.username,
        model_version_id=model_version.id,
        row_count=len(rows),
        success_count=len(valid),
        error_count=len(rows) - len(valid),
    )
    db.add(batch)
    db.flush()

    by_index = {index: prediction for (index, _), prediction in zip(valid, predictions)}
    results: list[RowResult] = []

    for index, record, errors in rows:
        if errors is not None:
            db.add(
                InferenceLog(
                    batch_id=batch.id,
                    row_index=index,
                    model_version_id=model_version.id,
                    requested_by=user.username,
                    request_type="batch",
                    input_json=record,
                    status="error",
                    error_message="; ".join(e["message"] for e in errors)[:1000],
                )
            )
            results.append(RowResult(row_index=index, status="error", errors=errors))
            continue

        predicted_class, probability = by_index[index]
        digest = input_hash(record)
        db.add(
            InferenceLog(
                batch_id=batch.id,
                row_index=index,
                model_version_id=model_version.id,
                requested_by=user.username,
                request_type="batch",
                input_json=record,
                input_hash=digest,
                predicted_class=predicted_class,
                probability=probability,
                latency_ms=per_row_latency,
                status="success",
            )
        )
        results.append(
            RowResult(
                row_index=index,
                status="success",
                predicted_class=predicted_class,
                predicted_label=label_for(predicted_class),
                probability=probability,
                input_hash=digest,
            )
        )

    db.commit()
    db.refresh(batch)

    return BatchResponse(
        batch_id=batch.id,
        model_version=model_version.version,
        preprocessing_version=PREPROCESSING_VERSION,
        timestamp=batch.created_at,
        row_count=batch.row_count,
        success_count=batch.success_count,
        error_count=batch.error_count,
        results=results,
    )
