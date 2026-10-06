from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, operator_user
from app.core.errors import AppError
from app.models import TelemetryRecord, User
from app.repositories.telemetry import TelemetryRepository
from app.schemas import TelemetryRecordRead

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/latest")
async def latest_telemetry(request: Request, user: User = Depends(operator_user)) -> dict[str, Any]:
    return request.app.state.hub.latest


@router.get("/history", response_model=list[TelemetryRecordRead])
async def telemetry_history(
    limit: int = Query(default=250, ge=1, le=1000),
    since: datetime | None = None,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> list[Any]:
    return await TelemetryRepository(session).recent(limit=limit, since=since)


@router.get("/export.csv")
async def export_telemetry_csv(
    limit: int = Query(default=1000, ge=1, le=10000),
    ids: str | None = None,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> StreamingResponse:
    if ids:
        try:
            selected_ids = [int(value) for value in ids.split(",") if value]
        except ValueError as exc:
            raise AppError(422, "Telemetry export IDs must be integers", code="invalid_export_ids") from exc
        if len(selected_ids) > 10000:
            raise AppError(
                422, "At most 10,000 telemetry records may be exported at once", code="export_limit_exceeded"
            )
        result = await session.scalars(
            select(TelemetryRecord)
            .where(TelemetryRecord.id.in_(selected_ids))
            .order_by(TelemetryRecord.timestamp.asc())
        )
        records = list(result.all())
    else:
        records = await TelemetryRepository(session).recent(limit=min(limit, 10000))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "timestamp",
            "source",
            "connected",
            "armed",
            "in_air",
            "flight_mode",
            "latitude",
            "longitude",
            "relative_altitude_m",
            "ground_speed_m_s",
            "heading_deg",
            "battery_remaining_pct",
            "battery_voltage_v",
            "gps_satellites",
            "flight_risk_score",
            "drone_health_score",
        ]
    )
    for item in records:
        writer.writerow(
            [
                item.timestamp.isoformat(),
                item.source,
                item.connected,
                item.armed,
                item.in_air,
                item.flight_mode,
                item.latitude,
                item.longitude,
                item.relative_altitude_m,
                item.ground_speed_m_s,
                item.heading_deg,
                item.battery_remaining_pct,
                item.battery_voltage_v,
                item.gps_satellites,
                item.flight_risk_score,
                item.drone_health_score,
            ]
        )
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=telemetry-export.csv"},
    )
