from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db, operator_user
from app.core.errors import AppError
from app.models import Mission, User, Waypoint
from app.schemas import MissionCreate, MissionRead, MissionUpdate
from app.services.mission_validation import validate_waypoints

router = APIRouter(prefix="/api/missions", tags=["missions"])


async def _get_mission(session: AsyncSession, mission_id: str, user: User) -> Mission:
    query = select(Mission).options(selectinload(Mission.waypoints)).where(Mission.id == mission_id)
    if user.role != "admin":
        query = query.where(Mission.owner_id == user.id)
    mission = await session.scalar(query)
    if mission is None:
        raise AppError(404, "Mission not found", code="mission_not_found")
    return mission


def _replace_waypoints(mission: Mission, payload: list[Any]) -> None:
    mission.waypoints = [
        Waypoint(
            sequence=index,
            latitude=point.latitude,
            longitude=point.longitude,
            altitude_m=point.altitude_m,
            hold_time_s=point.hold_time_s,
        )
        for index, point in enumerate(payload, start=1)
    ]


@router.get("", response_model=list[MissionRead])
async def list_missions(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> list[Mission]:
    query = select(Mission).options(selectinload(Mission.waypoints)).order_by(Mission.updated_at.desc())
    if user.role != "admin":
        query = query.where(Mission.owner_id == user.id)
    result = await session.scalars(query)
    return list(result.all())


@router.post("", response_model=MissionRead, status_code=status.HTTP_201_CREATED)
async def create_mission(
    payload: MissionCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> Mission:
    settings = request.app.state.settings
    validate_waypoints(
        payload.waypoints, max_waypoints=settings.max_mission_waypoints, max_altitude_m=settings.safe_max_altitude_m
    )
    mission = Mission(owner_id=user.id, name=payload.name.strip())
    _replace_waypoints(mission, payload.waypoints)
    session.add(mission)
    await session.commit()
    return await _get_mission(session, mission.id, user)


@router.get("/{mission_id}", response_model=MissionRead)
async def get_mission(
    mission_id: str,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> Mission:
    return await _get_mission(session, mission_id, user)


@router.put("/{mission_id}", response_model=MissionRead)
async def update_mission(
    mission_id: str,
    payload: MissionUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> Mission:
    settings = request.app.state.settings
    validate_waypoints(
        payload.waypoints, max_waypoints=settings.max_mission_waypoints, max_altitude_m=settings.safe_max_altitude_m
    )
    mission = await _get_mission(session, mission_id, user)
    mission.name = payload.name.strip()
    mission.status = "draft"
    mission.uploaded_at = None
    await session.execute(delete(Waypoint).where(Waypoint.mission_id == mission.id))
    await session.flush()
    _replace_waypoints(mission, payload.waypoints)
    await session.commit()
    return await _get_mission(session, mission.id, user)


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mission(
    mission_id: str,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> Response:
    mission = await _get_mission(session, mission_id, user)
    await session.delete(mission)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{mission_id}/upload")
async def upload_mission(
    mission_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> dict[str, Any]:
    mission = await _get_mission(session, mission_id, user)
    settings = request.app.state.settings
    points = [
        {
            "latitude": point.latitude,
            "longitude": point.longitude,
            "altitude_m": point.altitude_m,
            "hold_time_s": point.hold_time_s,
        }
        for point in mission.waypoints
    ]
    validate_waypoints(
        points,
        max_waypoints=settings.max_mission_waypoints,
        max_altitude_m=settings.safe_max_altitude_m,
        for_upload=True,
    )
    hub = request.app.state.hub
    current = hub.latest
    if not current.get("connected"):
        raise AppError(409, "PX4 is disconnected; mission upload was not attempted", code="vehicle_disconnected")
    if current.get("in_air") or current.get("armed"):
        raise AppError(
            409, "Mission upload is permitted only while PX4 is disarmed and on the ground", code="unsafe_vehicle_state"
        )
    if (
        current.get("ekf_ok") is not True
        or current.get("global_position_ok") is not True
        or current.get("home_position") is None
    ):
        raise AppError(
            409,
            "Mission upload requires healthy estimator, global position and home position",
            code="preflight_check_failed",
        )
    connector = request.app.state.connector
    if settings.telemetry_mode != "px4" or connector is None:
        raise AppError(409, "Mission upload requires a live PX4/MAVSDK connection", code="px4_required")
    try:
        await connector.upload_mission(points)
    except Exception as exc:
        raise AppError(502, "MAVSDK could not upload this mission to PX4", code="mission_upload_failed") from exc
    mission.status = "uploaded"
    mission.uploaded_at = datetime.now(UTC)
    await session.commit()
    return {
        "accepted": True,
        "mission_id": mission.id,
        "waypoint_count": len(points),
        "message": "Mission uploaded to PX4. Review it on the vehicle before starting.",
    }
