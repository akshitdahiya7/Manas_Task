"""Idempotent bootstrap of the registry and demo users.

Runs on every startup. Existing rows are left alone so restarting the stack
never resets which model is in production or undoes a promotion.
"""
import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.db_models import (
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    ModelVersion,
    PromotionEvent,
    User,
)
from app.security import hash_password

logger = logging.getLogger(__name__)

# Metrics are the held-out test scores published on the model card; they are
# what the "is the challenger better?" comparison starts from.
SEED_MODELS = [
    {
        "version": "v1-rf",
        "display_name": "Tuned Random Forest",
        "framework": "sklearn",
        "filename": "diabetes_random_forest_tuned.joblib",
        "status": STATUS_PRODUCTION,
        "metrics": {"accuracy": 0.7488, "precision": 0.7281, "recall": 0.7942, "f1": 0.7597},
        "notes": "Baseline production model (scikit-learn RandomForestClassifier, 200 trees).",
    },
    {
        "version": "v2-mlp",
        "display_name": "Tuned MLP",
        "framework": "keras",
        "filename": "diabetes_mlp_tuned.keras",
        "status": STATUS_CANDIDATE,
        "metrics": {"accuracy": 0.7512, "precision": 0.7264, "recall": 0.8059, "f1": 0.7641},
        "notes": "Candidate awaiting approval. Higher recall, which matters most here.",
    },
]


def seed_users(db: Session) -> None:
    accounts = [
        (settings.admin_username, settings.admin_password, "admin"),
        (settings.viewer_username, settings.viewer_password, "viewer"),
    ]
    for username, password, role in accounts:
        if db.query(User).filter(User.username == username).first():
            continue
        db.add(User(username=username, password_hash=hash_password(password), role=role))
        logger.info("Seeded %s user '%s'", role, username)
    db.commit()


def seed_models(db: Session) -> None:
    scaler_path = str(settings.models_dir / "scaler.joblib")

    for spec in SEED_MODELS:
        if db.query(ModelVersion).filter(ModelVersion.version == spec["version"]).first():
            continue

        version = ModelVersion(
            version=spec["version"],
            display_name=spec["display_name"],
            framework=spec["framework"],
            artifact_path=str(settings.models_dir / spec["filename"]),
            scaler_path=scaler_path,
            status=spec["status"],
            metrics=spec["metrics"],
            notes=spec["notes"],
        )
        db.add(version)
        db.flush()  # assign an id for the promotion event below

        if spec["status"] == STATUS_PRODUCTION:
            db.add(
                PromotionEvent(
                    model_version_id=version.id,
                    action="promote",
                    from_status="none",
                    to_status=STATUS_PRODUCTION,
                    performed_by="system",
                    reason="Initial deployment during bootstrap.",
                )
            )
        logger.info("Registered model version %s (%s)", spec["version"], spec["status"])

    db.commit()


def run(db: Session) -> None:
    seed_users(db)
    seed_models(db)
