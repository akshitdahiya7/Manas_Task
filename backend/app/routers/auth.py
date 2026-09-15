"""Login and identity endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import User
from app.schemas import LoginRequest, TokenResponse, UserResponse
from app.security import create_access_token, get_current_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Exchange username and password for a bearer token."""
    user = db.query(User).filter(User.username == payload.username).first()

    # Same message either way, so we don't reveal which usernames exist.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.username, user.role),
        username=user.username,
        role=user.role,
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    """Who the current token belongs to."""
    return UserResponse(username=user.username, role=user.role)
