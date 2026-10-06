from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, operator_user
from app.core.errors import AppError
from app.models import Alert, User, utc_now
from app.schemas import AlertRead

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    acknowledged: bool | None = None,
    severity: str | None = Query(default=None, pattern="^(INFO|WARNING|CRITICAL)$"),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> list[Alert]:
    query = select(Alert).order_by(Alert.occurred_at.desc()).limit(limit)
    if acknowledged is True:
        query = query.where(Alert.acknowledged_at.is_not(None))
    elif acknowledged is False:
        query = query.where(Alert.acknowledged_at.is_(None))
    if severity:
        query = query.where(Alert.severity == severity)
    return list((await session.scalars(query)).all())


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: str,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(operator_user),
) -> Alert:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise AppError(404, "Alert not found", code="alert_not_found")
    if alert.acknowledged_at is None:
        alert.acknowledged_at = utc_now()
        alert.acknowledged_by = user.id
        await session.commit()
        await session.refresh(alert)
    return alert
