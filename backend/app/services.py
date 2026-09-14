"""Small helpers shared by the routers."""
from sqlalchemy.orm import Session

from app.db_models import STATUS_PRODUCTION, ModelVersion
from app.errors import NotFoundError


def get_active_model(db: Session) -> ModelVersion:
    """The version currently serving traffic."""
    model_version = (
        db.query(ModelVersion).filter(ModelVersion.status == STATUS_PRODUCTION).first()
    )
    if model_version is None:
        raise NotFoundError("No model version is currently in production")
    return model_version


def resolve_model(db: Session, version: str | None) -> ModelVersion:
    """Pick the requested version, falling back to whichever is in production."""
    if version is None:
        return get_active_model(db)

    model_version = db.query(ModelVersion).filter(ModelVersion.version == version).first()
    if model_version is None:
        raise NotFoundError(f"Unknown model version '{version}'")
    return model_version
