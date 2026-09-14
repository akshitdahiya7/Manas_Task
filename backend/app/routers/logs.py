"""Read-only views over stored inferences and uploaded batches."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import InferenceLog, ModelVersion, UploadBatch, User
from app.errors import NotFoundError
from app.schemas import (
    BatchDetailResponse,
    BatchSummaryResponse,
    InferenceLogResponse,
)
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["history"])


def _to_log_response(log: InferenceLog) -> InferenceLogResponse:
    return InferenceLogResponse(
        id=log.id,
        batch_id=log.batch_id,
        row_index=log.row_index,
        model_version=log.model_version.version,
        requested_by=log.requested_by,
        request_type=log.request_type,
        predicted_class=log.predicted_class,
        probability=log.probability,
        latency_ms=log.latency_ms,
        status=log.status,
        error_message=log.error_message,
        input_hash=log.input_hash,
        input_json=log.input_json,
        created_at=log.created_at,
    )


def _to_batch_summary(batch: UploadBatch) -> BatchSummaryResponse:
    return BatchSummaryResponse(
        id=batch.id,
        filename=batch.filename,
        source=batch.source,
        uploaded_by=batch.uploaded_by,
        model_version=batch.model_version.version,
        row_count=batch.row_count,
        success_count=batch.success_count,
        error_count=batch.error_count,
        created_at=batch.created_at,
    )


@router.get("/logs", response_model=list[InferenceLogResponse])
def list_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    version: str | None = Query(None, description="Filter by model version"),
    status: str | None = Query(None, description="success or error"),
    mine: bool = Query(False, description="Only show the current user's inferences"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Recent inferences, newest first."""
    query = db.query(InferenceLog).join(ModelVersion)

    if version:
        query = query.filter(ModelVersion.version == version)
    if status:
        query = query.filter(InferenceLog.status == status)
    if mine:
        query = query.filter(InferenceLog.requested_by == user.username)

    logs = (
        query.order_by(InferenceLog.created_at.desc(), InferenceLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_log_response(log) for log in logs]


@router.get("/batches", response_model=list[BatchSummaryResponse])
def list_batches(
    limit: int = Query(50, ge=1, le=200),
    mine: bool = Query(False, description="Only show the current user's uploads"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Uploaded CSV / JSON batches, newest first."""
    query = db.query(UploadBatch)
    if mine:
        query = query.filter(UploadBatch.uploaded_by == user.username)

    batches = query.order_by(UploadBatch.created_at.desc(), UploadBatch.id.desc()).limit(limit).all()
    return [_to_batch_summary(batch) for batch in batches]


@router.get("/batches/{batch_id}", response_model=BatchDetailResponse)
def batch_detail(
    batch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One batch with every row's result."""
    batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id).first()
    if batch is None:
        raise NotFoundError(f"No batch with id {batch_id}")

    logs = (
        db.query(InferenceLog)
        .filter(InferenceLog.batch_id == batch_id)
        .order_by(InferenceLog.row_index.asc())
        .all()
    )

    summary = _to_batch_summary(batch)
    return BatchDetailResponse(**summary.model_dump(), logs=[_to_log_response(log) for log in logs])
