from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, operator_user
from app.core.errors import AppError
from app.models import Flight, User
from app.schemas import FlightRead

router = APIRouter(prefix="/api/flights", tags=["flights"])


@router.get("", response_model=list[FlightRead])
async def list_flights(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> list[Flight]:
    query = select(Flight).order_by(Flight.started_at.desc()).limit(limit)
    return list((await session.scalars(query)).all())


@router.get("/export.csv")
async def export_flights_csv(
    limit: int = Query(default=500, ge=1, le=5000),
    ids: str | None = None,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> StreamingResponse:
    statement = select(Flight).order_by(Flight.started_at.desc())
    if ids:
        selected_ids = [value for value in ids.split(",") if value]
        if len(selected_ids) > 5000:
            raise AppError(422, "At most 5,000 flights may be exported at once", code="export_limit_exceeded")
        statement = statement.where(Flight.id.in_(selected_ids))
    else:
        statement = statement.limit(limit)
    flights = await session.scalars(statement)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "name",
            "status",
            "started_at",
            "ended_at",
            "duration_seconds",
            "max_altitude_m",
            "distance_m",
            "telemetry_count",
            "max_risk_score",
            "battery_start_pct",
            "battery_end_pct",
        ]
    )
    for flight in flights:
        writer.writerow(
            [
                flight.id,
                flight.name,
                flight.status,
                flight.started_at.isoformat(),
                flight.ended_at.isoformat() if flight.ended_at else "",
                flight.duration_seconds,
                flight.max_altitude_m,
                flight.distance_m,
                flight.telemetry_count,
                flight.max_risk_score,
                flight.battery_start_pct,
                flight.battery_end_pct,
            ]
        )
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=flight-logs.csv"},
    )
