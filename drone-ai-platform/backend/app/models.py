from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(24), default="operator", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    missions: Mapped[list[Mission]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Drone(Base):
    __tablename__ = "drones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), default="PX4 vehicle", nullable=False)
    system_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    connection_uri: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"
    __table_args__ = (Index("ix_telemetry_timestamp", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drone_id: Mapped[str | None] = mapped_column(ForeignKey("drones.id", ondelete="SET NULL"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="offline", nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    ground_speed_m_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_remaining_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_satellites: Mapped[int | None] = mapped_column(Integer, nullable=True)
    armed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    in_air: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flight_mode: Mapped[str] = mapped_column(String(64), default="UNKNOWN", nullable=False)
    flight_risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    drone_health_score: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class Mission(Base):
    __tablename__ = "missions"
    __table_args__ = (Index("ix_missions_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner: Mapped[User] = relationship(back_populates="missions")
    waypoints: Mapped[list[Waypoint]] = relationship(
        back_populates="mission", cascade="all, delete-orphan", order_by="Waypoint.sequence"
    )


class Waypoint(Base):
    __tablename__ = "waypoints"
    __table_args__ = (Index("ix_waypoints_mission_sequence", "mission_id", "sequence", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    altitude_m: Mapped[float] = mapped_column(Float, nullable=False)
    hold_time_s: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    mission: Mapped[Mission] = relationship(back_populates="waypoints")


class Flight(Base):
    __tablename__ = "flights"
    __table_args__ = (Index("ix_flights_started_at", "started_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    drone_id: Mapped[str | None] = mapped_column(ForeignKey("drones.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(160), default="PX4 flight", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="in_progress", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    max_altitude_m: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    distance_m: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    telemetry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    battery_start_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_end_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_occurred_at", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class SystemEvent(Base):
    __tablename__ = "system_events"
    __table_args__ = (Index("ix_system_events_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
