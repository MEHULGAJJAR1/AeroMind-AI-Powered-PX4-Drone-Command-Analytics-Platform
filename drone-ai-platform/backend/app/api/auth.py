from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import AuthResponse, LoginRequest, RegisterRequest, UserPublic

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def _auth_response(user: User, request: Request) -> AuthResponse:
    settings = request.app.state.settings
    token, expires_at = create_access_token(user.id, user.role, settings)
    return AuthResponse(access_token=token, expires_at=expires_at, user=UserPublic.model_validate(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AuthResponse:
    if not request.app.state.settings.allow_registration:
        raise HTTPException(status_code=403, detail="New account registration is disabled")
    existing = await session.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(email=payload.email, hashed_password=hash_password(payload.password), role="operator")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _auth_response(user, request)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AuthResponse:
    user = await session.scalar(select(User).where(User.email == payload.email))
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email or password is incorrect")
    return _auth_response(user, request)


@router.post("/ws-ticket")
async def websocket_ticket(request: Request, user: User = Depends(get_current_user)) -> dict[str, object]:
    ticket = await request.app.state.ws_tickets.issue(user.id)
    return {"ticket": ticket, "expires_in": request.app.state.ws_tickets.ttl_seconds}


@router.get("/me", response_model=UserPublic)
async def current_user(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(user)
