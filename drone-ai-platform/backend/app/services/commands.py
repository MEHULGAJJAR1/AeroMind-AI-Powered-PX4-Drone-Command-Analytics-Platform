from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas import CommandRequest, CommandResponse
from app.services.px4 import MavsdkConnector
from app.services.telemetry_hub import TelemetryHub

logger = logging.getLogger(__name__)


class DroneCommandService:
    def __init__(self, hub: TelemetryHub, connector: MavsdkConnector | None, settings: Settings) -> None:
        self.hub = hub
        self.connector = connector
        self.settings = settings

    async def execute(self, request: CommandRequest, *, actor_id: str | None = None) -> CommandResponse:
        if self.settings.telemetry_mode != "px4":
            raise AppError(409, "Vehicle commands are disabled outside real PX4 mode", code="controls_disabled")
        state = self.hub.latest
        if not state.get("connected"):
            raise AppError(409, "PX4 is disconnected; no command was sent", code="vehicle_disconnected")
        if self.connector is None or self.connector.system is None:
            raise AppError(503, "MAVSDK command channel is not ready", code="mavsdk_unavailable")
        vehicle = self.connector.system
        armed, in_air = bool(state.get("armed")), bool(state.get("in_air"))
        command = request.command

        if command == "arm":
            if armed:
                raise AppError(409, "Vehicle is already armed", code="invalid_vehicle_state")
            if in_air:
                raise AppError(409, "Cannot arm while the vehicle is reported airborne", code="invalid_vehicle_state")
            if state.get("ekf_ok") is not True or state.get("global_position_ok") is not True:
                raise AppError(
                    409,
                    "Arming blocked: estimator and global-position health must be confirmed",
                    code="preflight_check_failed",
                )
            if state.get("gps_satellites") is not None and int(state["gps_satellites"]) < 6:
                raise AppError(
                    409, "Arming blocked: fewer than six GPS satellites are available", code="preflight_check_failed"
                )
            if state.get("home_position") is None:
                raise AppError(409, "Arming blocked: home position is not established", code="preflight_check_failed")
            battery = state.get("battery_remaining_pct")
            if battery is not None and float(battery) < 20:
                raise AppError(
                    409, "Arming blocked: battery is below the 20% safety threshold", code="preflight_check_failed"
                )
        elif command == "disarm":
            if not armed:
                raise AppError(409, "Vehicle is already disarmed", code="invalid_vehicle_state")
            if in_air:
                raise AppError(
                    409, "Disarm is blocked while airborne; use land or return-to-launch", code="unsafe_command"
                )
        elif command == "takeoff":
            if not armed or in_air:
                raise AppError(
                    409, "Takeoff requires an armed vehicle that is still on the ground", code="invalid_vehicle_state"
                )
            if state.get("ekf_ok") is not True or state.get("home_position") is None:
                raise AppError(
                    409,
                    "Takeoff blocked: estimator health and home position must remain valid",
                    code="preflight_check_failed",
                )
            if request.takeoff_altitude_m > self.settings.safe_max_altitude_m:
                raise AppError(
                    422,
                    f"Takeoff altitude exceeds configured limit ({self.settings.safe_max_altitude_m:g} m)",
                    code="altitude_out_of_range",
                )
        elif command in ("land", "hold"):
            if not armed or not in_air:
                raise AppError(
                    409, f"{command.title()} requires an armed airborne vehicle", code="invalid_vehicle_state"
                )
        elif command == "rtl" and not armed:
            raise AppError(409, "Return-to-launch requires an armed vehicle", code="invalid_vehicle_state")
        elif command == "set_mode":
            if request.mode is None:
                raise AppError(422, "Choose a supported flight mode", code="invalid_mode")
            if request.mode in ("HOLD", "LAND") and (not armed or not in_air):
                raise AppError(
                    409,
                    f"{request.mode.replace('_', ' ').title()} mode requires an armed airborne vehicle",
                    code="invalid_vehicle_state",
                )
            if request.mode == "RETURN_TO_LAUNCH" and not armed:
                raise AppError(409, "Return-to-launch requires an armed vehicle", code="invalid_vehicle_state")

        try:
            if command == "arm":
                await vehicle.action.arm()
            elif command == "disarm":
                await vehicle.action.disarm()
            elif command == "takeoff":
                await vehicle.action.set_takeoff_altitude(float(request.takeoff_altitude_m))
                await vehicle.action.takeoff()
            elif command == "land":
                await vehicle.action.land()
            elif command == "rtl":
                await vehicle.action.return_to_launch()
            elif command == "hold":
                await vehicle.action.hold()
            elif command == "set_mode":
                await self._set_supported_mode(vehicle, request.mode or "")
        except AppError:
            raise
        except Exception as exc:
            logger.warning(
                "px4_command_rejected", extra={"event": "px4_command_rejected", "category": command}, exc_info=True
            )
            raise AppError(502, f"PX4 did not accept the {command} command", code="command_rejected") from exc

        label = (
            request.mode.replace("_", " ").title()
            if command == "set_mode" and request.mode
            else command.replace("_", " ").title()
        )
        await self.hub.record_system_event(
            "FLIGHT_COMMAND",
            f"{label} command accepted by PX4/MAVSDK",
            details={"command": command, "mode": request.mode, "actor_id": actor_id},
        )
        return CommandResponse(
            command=command,
            accepted=True,
            message=f"{label} command accepted by MAVSDK",
            executed_at=datetime.now(UTC),
        )

    @staticmethod
    async def _set_supported_mode(vehicle: Any, mode: str) -> None:
        supported = {
            "HOLD": vehicle.action.hold,
            "LAND": vehicle.action.land,
            "RETURN_TO_LAUNCH": vehicle.action.return_to_launch,
        }
        if mode not in supported:
            raise AppError(422, "Supported modes are HOLD, LAND and RETURN_TO_LAUNCH", code="unsupported_mode")
        await supported[mode]()
