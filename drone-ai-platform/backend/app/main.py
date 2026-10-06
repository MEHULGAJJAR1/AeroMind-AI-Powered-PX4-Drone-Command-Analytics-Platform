from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api import alerts, analytics, auth, drone, flights, missions, system, telemetry, websocket
from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.database import Base, create_database
from app.models import Drone, User
from app.services.commands import DroneCommandService
from app.services.px4 import MavsdkConnector
from app.services.telemetry_hub import TelemetryHub
from app.services.ws_tickets import WebSocketTicketStore

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging()
    engine, session_factory = create_database(settings.database_url)
    hub = TelemetryHub(
        mode=settings.telemetry_mode,
        session_factory=session_factory,
        persist_interval_s=settings.telemetry_persist_interval_s,
        max_altitude_m=settings.safe_max_altitude_m,
        max_speed_m_s=settings.safe_max_speed_m_s,
    )
    connector = MavsdkConnector(hub, settings) if settings.telemetry_mode == "px4" else None
    command_service = DroneCommandService(hub, connector, settings)
    stop_event = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.auto_create_schema:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            default_drone = await session.scalar(select(Drone).order_by(Drone.created_at).limit(1))
            if default_drone is None:
                default_drone = Drone(name="PX4 / SITL vehicle", model="PX4 Autopilot")
                session.add(default_drone)
                await session.commit()
                await session.refresh(default_drone)
            hub.drone_id = default_drone.id
        if settings.bootstrap_admin_email:
            async with session_factory() as session:
                existing = await session.scalar(
                    select(User).where(User.email == settings.bootstrap_admin_email.casefold())
                )
                if existing is None:
                    session.add(
                        User(
                            email=settings.bootstrap_admin_email.casefold(),
                            hashed_password=hash_password(settings.bootstrap_admin_password),
                            role="admin",
                        )
                    )
                    await session.commit()
                    logger.info("bootstrap_admin_created", extra={"event": "bootstrap_admin_created"})
        worker: asyncio.Task | None = None
        if settings.telemetry_mode == "mock":
            worker = asyncio.create_task(hub.run_mock(settings.mock_tick_seconds, stop_event), name="mock-telemetry")
        elif settings.telemetry_mode == "px4" and connector is not None:
            worker = asyncio.create_task(connector.run(), name="px4-mavsdk-supervisor")
        logger.info("application_started", extra={"event": "application_started", "category": settings.telemetry_mode})
        try:
            yield
        finally:
            stop_event.set()
            if connector is not None:
                await connector.stop()
            if worker is not None:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
            await hub.close()
            await engine.dispose()
            logger.info("application_stopped", extra={"event": "application_stopped"})

    app = FastAPI(
        title=settings.app_name,
        description="PX4/MAVSDK drone operations, telemetry, mission planning, and explainable analytics API.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.hub = hub
    app.state.connector = connector
    app.state.command_service = command_service
    app.state.ws_tickets = WebSocketTicketStore()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": jsonable_encoder(exc.errors()),
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("database_request_failed", extra={"event": "database_request_failed"})
        return JSONResponse(
            status_code=503, content={"error": {"code": "database_unavailable", "message": "Database operation failed"}}
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_request_error", extra={"event": "unhandled_request_error"})
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "An unexpected server error occurred"}},
        )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "drone-ai-platform"}

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "docs": "/docs", "health": "/health"}

    for router in (
        auth.router,
        drone.router,
        telemetry.router,
        missions.router,
        flights.router,
        analytics.router,
        alerts.router,
        system.router,
        websocket.router,
    ):
        app.include_router(router)
    return app


app = create_app()
