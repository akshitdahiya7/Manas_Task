"""Basic service monitoring, aggregated from the inference log.

Deliberately lightweight - a real deployment would export these to Prometheus
rather than compute them per request.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.db_models import InferenceLog, ModelVersion, User, utcnow
from app.security import get_current_user

router = APIRouter(prefix="/api/metrics", tags=["monitoring"])


def _percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(int(round(fraction * len(ordered) + 0.5)) - 1, len(ordered) - 1)
    return round(ordered[max(index, 0)], 2)


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Volume, error rate, latency and prediction distribution."""
    total = db.query(func.count(InferenceLog.id)).scalar() or 0
    errors = (
        db.query(func.count(InferenceLog.id)).filter(InferenceLog.status == "error").scalar() or 0
    )

    since = utcnow() - timedelta(hours=24)
    last_24h = (
        db.query(func.count(InferenceLog.id)).filter(InferenceLog.created_at >= since).scalar() or 0
    )

    latencies = [
        row[0]
        for row in db.query(InferenceLog.latency_ms)
        .filter(InferenceLog.latency_ms.isnot(None))
        .order_by(InferenceLog.created_at.desc())
        .limit(1000)
        .all()
    ]

    by_class = dict(
        db.query(InferenceLog.predicted_class, func.count(InferenceLog.id))
        .filter(InferenceLog.predicted_class.isnot(None))
        .group_by(InferenceLog.predicted_class)
        .all()
    )

    by_version = [
        {"version": version, "count": count}
        for version, count in db.query(ModelVersion.version, func.count(InferenceLog.id))
        .join(InferenceLog, InferenceLog.model_version_id == ModelVersion.id)
        .group_by(ModelVersion.version)
        .all()
    ]

    return {
        "total_inferences": total,
        "inferences_last_24h": last_24h,
        "error_count": errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "latency_ms": {
            "avg": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "samples": len(latencies),
        },
        "prediction_distribution": {
            "negative": by_class.get(0, 0),
            "positive": by_class.get(1, 0),
        },
        "by_version": by_version,
        "drift": _drift(db),
    }


def _drift(db: Session) -> dict:
    """Prediction-drift proxy.

    Compares the recent positive rate against the balanced 50/50 training
    baseline. This watches the model's output, not its input features, so it
    flags a shift worth investigating rather than proving one.
    """
    recent = [
        row[0]
        for row in db.query(InferenceLog.predicted_class)
        .filter(InferenceLog.predicted_class.isnot(None))
        .order_by(InferenceLog.created_at.desc(), InferenceLog.id.desc())
        .limit(settings.drift_window)
        .all()
    ]

    if not recent:
        return {
            "window": 0,
            "positive_rate": None,
            "baseline": settings.drift_baseline_positive_rate,
            "delta": None,
            "status": "no_data",
        }

    positive_rate = sum(recent) / len(recent)
    delta = positive_rate - settings.drift_baseline_positive_rate

    return {
        "window": len(recent),
        "positive_rate": round(positive_rate, 4),
        "baseline": settings.drift_baseline_positive_rate,
        "delta": round(delta, 4),
        "threshold": settings.drift_threshold,
        "status": "alert" if abs(delta) > settings.drift_threshold else "ok",
    }
