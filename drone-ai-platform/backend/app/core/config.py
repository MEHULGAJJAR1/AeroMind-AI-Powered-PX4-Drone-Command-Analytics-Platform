from __future__ import annotations

import secrets
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AeroMind Drone Operations"
    app_env: Literal["development", "test", "production"] = "development"
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=5, le=1440)
    database_url: str = "sqlite+aiosqlite:///./data/aeromind.db"
    auto_create_schema: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    allow_registration: bool = True
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    telemetry_mode: Literal["mock", "px4", "disabled"] = "mock"
    px4_system_address: str = "udp://:14540"
    mavsdk_server_address: str = "127.0.0.1"
    mavsdk_server_port: int = Field(default=50051, ge=1, le=65535)
    px4_connect_timeout_s: float = Field(default=15.0, ge=1.0, le=120.0)
    reconnect_backoff_max_s: float = Field(default=30.0, ge=1.0, le=300.0)
    mock_tick_seconds: float = Field(default=1.0, ge=0.1, le=10.0)
    telemetry_persist_interval_s: float = Field(default=2.0, ge=0.5, le=60.0)
    max_mission_waypoints: int = Field(default=100, ge=2, le=500)
    safe_max_altitude_m: float = Field(default=120.0, gt=0, le=500)
    safe_max_speed_m_s: float = Field(default=25.0, gt=0, le=100)

    @model_validator(mode="after")
    def configure_security(self) -> Settings:
        if not self.secret_key:
            if self.app_env == "production":
                raise ValueError("SECRET_KEY must be configured in production")
            self.secret_key = secrets.token_urlsafe(48)
        if self.app_env == "production" and len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production")
        if bool(self.bootstrap_admin_email) != bool(self.bootstrap_admin_password):
            raise ValueError("Set both BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD")
        if self.bootstrap_admin_password and len(self.bootstrap_admin_password) < 12:
            raise ValueError("Bootstrap admin password must be at least 12 characters")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
