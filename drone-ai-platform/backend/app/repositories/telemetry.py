from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelemetryRecord


class TelemetryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def recent(self, *, limit: int = 250, since: datetime | None = None) -> list[TelemetryRecord]:
        statement = select(TelemetryRecord).order_by(TelemetryRecord.timestamp.desc()).limit(limit)
        if since is not None:
            statement = statement.where(TelemetryRecord.timestamp >= since)
        result = await self.session.scalars(statement)
        return list(reversed(result.all()))
