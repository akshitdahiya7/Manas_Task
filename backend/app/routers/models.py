"""Model registry endpoints: listing versions, promotion and rollback.

Promotion never overwrites an artifact. It only moves which registered row
carries the `production` status, so the previous model stays on disk and a
rollback is just another status change.
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import (
    STATUS_ARCHIVED,
    STATUS_PRODUCTION,
    ModelVersion,
    PromotionEvent,
    User,
)
from app.errors import BadRequestError, NotFoundError
from app.schemas import (
    ModelVersionResponse,
    PromotionEventResponse,
    PromotionRequest,
)
from app.security import get_current_user, require_admin
from app.services import get_active_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelVersionResponse])
def list_versions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Every registered version, newest first."""
    return db.query(ModelVersion).order_by(ModelVersion.created_at.desc()).all()


@router.get("/active", response_model=ModelVersionResponse)
def active_version(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The version currently serving traffic."""
    return get_active_model(db)


@router.get("/promotions", response_model=list[PromotionEventResponse])
def promotion_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Audit trail of promotions and rollbacks, newest first."""
    events = (
        db.query(PromotionEvent)
        .order_by(PromotionEvent.created_at.desc(), PromotionEvent.id.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        PromotionEventResponse(
            id=event.id,
            version=event.model_version.version,
            action=event.action,
            from_status=event.from_status,
            to_status=event.to_status,
            performed_by=event.performed_by,
            reason=event.reason,
            created_at=event.created_at,
        )
        for event in events
    ]


def _switch_production(
    db: Session,
    target: ModelVersion,
    performed_by: str,
    action: str,
    reason: str | None,
) -> ModelVersion:
    """Make `target` the production model in a single transaction.

    Demoting the incumbent and promoting the target happen together, so the
    "exactly one production model" invariant always holds.
    """
    previous_status = target.status
    incumbent = (
        db.query(ModelVersion)
        .filter(ModelVersion.status == STATUS_PRODUCTION, ModelVersion.id != target.id)
        .first()
    )

    if incumbent is not None:
        incumbent.status = STATUS_ARCHIVED
        db.add(
            PromotionEvent(
                model_version_id=incumbent.id,
                action="archive",
                from_status=STATUS_PRODUCTION,
                to_status=STATUS_ARCHIVED,
                performed_by=performed_by,
                reason=f"Replaced by {target.version}.",
            )
        )

    target.status = STATUS_PRODUCTION
    db.add(
        PromotionEvent(
            model_version_id=target.id,
            action=action,
            from_status=previous_status,
            to_status=STATUS_PRODUCTION,
            performed_by=performed_by,
            reason=reason,
        )
    )

    db.commit()
    db.refresh(target)
    logger.info("%s: %s is now in production (by %s)", action, target.version, performed_by)
    return target


@router.post("/{version}/promote", response_model=ModelVersionResponse)
def promote(
    version: str,
    payload: PromotionRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Promote a version to production. Admin only."""
    target = db.query(ModelVersion).filter(ModelVersion.version == version).first()
    if target is None:
        raise NotFoundError(f"Unknown model version '{version}'")
    if target.status == STATUS_PRODUCTION:
        raise BadRequestError(f"Version '{version}' is already in production")

    reason = payload.reason if payload else None
    return _switch_production(db, target, user.username, "promote", reason)


@router.post("/rollback", response_model=ModelVersionResponse)
def rollback(
    payload: PromotionRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Return to the previously deployed version. Admin only.

    The target is the model that was archived most recently, i.e. the one the
    current production model displaced.
    """
    last_archive = (
        db.query(PromotionEvent)
        .filter(PromotionEvent.to_status == STATUS_ARCHIVED)
        .order_by(PromotionEvent.created_at.desc(), PromotionEvent.id.desc())
        .first()
    )
    if last_archive is None:
        raise BadRequestError("There is no previous version to roll back to")

    target = db.query(ModelVersion).filter(ModelVersion.id == last_archive.model_version_id).first()
    if target is None:
        raise NotFoundError("The previous version is no longer registered")
    if target.status == STATUS_PRODUCTION:
        raise BadRequestError(f"Version '{target.version}' is already in production")

    reason = payload.reason if payload else None
    return _switch_production(db, target, user.username, "rollback", reason)
