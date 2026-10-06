from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: Literal["operator", "admin"]
    created_at: datetime


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address")
        return normalized


class LoginRequest(RegisterRequest):
    pass


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserPublic


class WaypointInput(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    altitude_m: float = Field(gt=0, le=500, allow_inf_nan=False)
    hold_time_s: float = Field(default=0, ge=0, le=3600, allow_inf_nan=False)


class WaypointRead(WaypointInput):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sequence: int


class MissionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    waypoints: list[WaypointInput] = Field(default_factory=list, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Mission name cannot be blank")
        return normalized


class MissionUpdate(MissionCreate):
    pass


class MissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime
    uploaded_at: datetime | None
    waypoints: list[WaypointRead]


class CommandRequest(BaseModel):
    command: Literal["arm", "disarm", "takeoff", "land", "rtl", "hold", "set_mode"]
    takeoff_altitude_m: float = Field(default=5, ge=2, le=120)
    mode: Literal["HOLD", "LAND", "RETURN_TO_LAUNCH"] | None = None


class CommandResponse(BaseModel):
    command: str
    accepted: bool
    message: str
    executed_at: datetime


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    severity: str
    category: str
    title: str
    message: str
    occurred_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    details: dict[str, Any]


class FlightRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float
    max_altitude_m: float
    distance_m: float
    telemetry_count: int
    max_risk_score: int
    battery_start_pct: float | None
    battery_end_pct: float | None
    summary: str | None


class TelemetryRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    connected: bool
    source: str
    latitude: float | None
    longitude: float | None
    relative_altitude_m: float | None
    ground_speed_m_s: float | None
    heading_deg: float | None
    battery_remaining_pct: float | None
    battery_voltage_v: float | None
    gps_satellites: int | None
    armed: bool
    in_air: bool
    flight_mode: str
    flight_risk_score: int
    drone_health_score: int
    payload: dict[str, Any]


class SystemEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    category: str
    message: str
    created_at: datetime
    details: dict[str, Any]


class SystemStatus(BaseModel):
    api: str
    database: str
    telemetry_mode: str
    px4: str
    mavsdk: str
    websocket_clients: int
    last_telemetry_at: str | None
    frontend: str = "client-reported"
