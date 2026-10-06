from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import operator_user
from app.core.errors import AppError
from app.models import User
from app.schemas import CommandRequest, CommandResponse

router = APIRouter(prefix="/api/drone", tags=["drone"])


@router.get("/status")
async def drone_status(request: Request, user: User = Depends(operator_user)) -> dict[str, Any]:
    hub = request.app.state.hub
    state = hub.latest
    return {
        **state,
        "configured_mode": request.app.state.settings.telemetry_mode,
        "mavsdk_available": request.app.state.connector is not None,
        "control_enabled": request.app.state.settings.telemetry_mode == "px4" and bool(state.get("connected")),
    }


@router.post("/connect", status_code=202)
async def request_connection(request: Request, user: User = Depends(operator_user)) -> dict[str, Any]:
    connector = request.app.state.connector
    mode = request.app.state.settings.telemetry_mode
    if mode == "mock":
        return {"accepted": True, "mode": "mock", "message": "Simulated telemetry is already running."}
    if mode == "disabled" or connector is None:
        raise AppError(409, "PX4 connection is not enabled; set TELEMETRY_MODE=px4", code="px4_disabled")
    connector.request_reconnect()
    return {
        "accepted": True,
        "mode": "px4",
        "message": "Connection retry requested; the MAVSDK supervisor reconnects automatically.",
    }


@router.post("/command", response_model=CommandResponse)
async def send_command(
    payload: CommandRequest,
    request: Request,
    user: User = Depends(operator_user),
) -> CommandResponse:
    return await request.app.state.command_service.execute(payload, actor_id=user.id)
