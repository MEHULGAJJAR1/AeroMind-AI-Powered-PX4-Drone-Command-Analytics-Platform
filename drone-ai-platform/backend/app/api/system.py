from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, operator_user
from app.models import SystemEvent, User
from app.schemas import SystemEventRead, SystemStatus

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/events", response_model=list[SystemEventRead])
async def recent_system_events(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> list[SystemEvent]:
    result = await session.scalars(select(SystemEvent).order_by(SystemEvent.created_at.desc()).limit(limit))
    return list(result.all())


@router.get("/status", response_model=SystemStatus)
async def system_status(
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> SystemStatus:
    try:
        await session.execute(text("SELECT 1"))
        database = "online"
    except Exception:
        database = "degraded"
    state = request.app.state.hub.latest
    mode = request.app.state.settings.telemetry_mode
    if state.get("connected"):
        px4, mavsdk = "connected" if mode == "px4" else "simulated", "connected" if mode == "px4" else "not used"
    elif mode == "disabled":
        px4, mavsdk = "disabled", "disabled"
    else:
        px4, mavsdk = "offline", "reconnecting" if mode == "px4" else "not used"
    return SystemStatus(
        api="online",
        database=database,
        telemetry_mode=mode,
        px4=px4,
        mavsdk=mavsdk,
        websocket_clients=request.app.state.hub.subscriber_count,
        last_telemetry_at=state.get("timestamp"),
    )
