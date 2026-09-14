"""Database tables.

Five tables cover everything the assignment asks to persist: who can act
(users), what can serve traffic (model_versions), how the active model changed
over time (promotion_events), what files were uploaded (upload_batches) and
every individual inference (inference_logs).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Model lifecycle states.
STATUS_CANDIDATE = "candidate"
STATUS_PRODUCTION = "production"
STATUS_ARCHIVED = "archived"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin | viewer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelVersion(Base):
    """One registered, servable model artifact.

    Exactly one row is expected to be in STATUS_PRODUCTION at a time; the
    promotion logic in routers/models.py maintains that invariant.
    """

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    framework: Mapped[str] = mapped_column(String(20))  # sklearn | keras
    artifact_path: Mapped[str] = mapped_column(String(300))
    scaler_path: Mapped[str] = mapped_column(String(300))
    preprocessing_version: Mapped[str] = mapped_column(String(20), default="v1")
    status: Mapped[str] = mapped_column(String(20), default=STATUS_CANDIDATE, index=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PromotionEvent(Base):
    """Audit trail of every promotion / rollback, so deployments are traceable."""

    __tablename__ = "promotion_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    action: Mapped[str] = mapped_column(String(20))  # promote | rollback | archive
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    performed_by: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    model_version: Mapped[ModelVersion] = relationship()


class UploadBatch(Base):
    """A single batch submission (CSV upload or JSON array)."""

    __tablename__ = "upload_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(260))
    source: Mapped[str] = mapped_column(String(20))  # csv | json
    uploaded_by: Mapped[str] = mapped_column(String(50), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    model_version: Mapped[ModelVersion] = relationship()


class InferenceLog(Base):
    """One row per attempted prediction - successes and failures alike.

    input_json echoes the validated payload and input_hash is a stable digest
    of it, which together with model_version and preprocessing_version is
    enough to reproduce any historical inference.
    """

    __tablename__ = "inference_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True, index=True)
    row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), index=True)
    requested_by: Mapped[str] = mapped_column(String(50), index=True)
    request_type: Mapped[str] = mapped_column(String(20))  # single | batch
    input_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    predicted_class: Mapped[int | None] = mapped_column(Integer, nullable=True)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    model_version: Mapped[ModelVersion] = relationship()


# Supports the dashboard's "recent logs for version X" query.
Index("ix_inference_logs_created_version", InferenceLog.created_at, InferenceLog.model_version_id)
