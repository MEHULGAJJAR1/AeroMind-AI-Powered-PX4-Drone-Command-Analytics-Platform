from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable
from typing import Any

from app.core.config import Settings
from app.services.telemetry_hub import TelemetryHub

logger = logging.getLogger(__name__)


class MavsdkConnector:
    """Owns a reconnecting MAVSDK connection and publishes telemetry without blocking HTTP."""

    def __init__(self, hub: TelemetryHub, settings: Settings) -> None:
        self.hub = hub
        self.settings = settings
        self.system: Any | None = None
        self._stop = asyncio.Event()
        self._reconnect_requested = asyncio.Event()

    def request_reconnect(self) -> None:
        self._reconnect_requested.set()

    async def run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                from mavsdk import System

                self.system = System(
                    mavsdk_server_address=self.settings.mavsdk_server_address,
                    port=self.settings.mavsdk_server_port,
                )
                await self.hub.publish(
                    source="px4",
                    connected=False,
                    connection_state="connecting",
                    last_error=None,
                    system_status="Connecting to PX4/MAVLink",
                )
                await self.system.connect(system_address=self.settings.px4_system_address)
                await asyncio.wait_for(
                    self._wait_until_connected(self.system), timeout=self.settings.px4_connect_timeout_s
                )
                await self.hub.publish(
                    source="px4",
                    connected=True,
                    connection_state="connected",
                    last_error=None,
                    system_status="PX4 connected via MAVSDK",
                )
                backoff = 1.0
                await self._stream_until_disconnected(self.system)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "px4_connection_cycle_failed",
                    extra={"event": "px4_connection_cycle_failed", "category": type(exc).__name__},
                )
                await self.hub.publish(
                    source="px4",
                    connected=False,
                    connection_state="reconnecting",
                    last_error=f"{type(exc).__name__}: {str(exc)[:180]}",
                    system_status="PX4 unavailable; reconnecting",
                )
            finally:
                was_active = self.system is not None
                self.system = None
                if was_active and not self._stop.is_set():
                    await self.hub.publish(
                        source="px4",
                        connected=False,
                        connection_state="reconnecting",
                        system_status="PX4 link lost; reconnecting",
                    )
            if self._stop.is_set():
                break
            wait_time = min(backoff, self.settings.reconnect_backoff_max_s)
            try:
                await asyncio.wait_for(self._reconnect_requested.wait(), timeout=wait_time)
            except TimeoutError:
                pass
            self._reconnect_requested.clear()
            backoff = min(backoff * 2.0, self.settings.reconnect_backoff_max_s)

    async def _wait_until_connected(self, system: Any) -> None:
        async for state in system.core.connection_state():
            if state.is_connected:
                return
        raise ConnectionError("MAVSDK connection-state stream closed before connecting")

    async def _stream_until_disconnected(self, system: Any) -> None:
        telemetry = system.telemetry
        streams: list[tuple[Any, Callable[[Any], dict[str, Any]]]] = [
            (telemetry.position(), _position),
            (telemetry.attitude_euler(), _attitude),
            (telemetry.velocity_ned(), _velocity),
            (telemetry.battery(), _battery),
            (telemetry.gps_info(), _gps),
            (telemetry.health(), _health),
            (telemetry.flight_mode(), _flight_mode),
            (telemetry.armed(), lambda value: {"armed": bool(value)}),
            (telemetry.in_air(), lambda value: {"in_air": bool(value)}),
            (telemetry.home(), _home),
        ]
        tasks = [asyncio.create_task(self._consume(stream, mapper)) for stream, mapper in streams]
        tasks.append(asyncio.create_task(self._watch_disconnect(system)))
        optional_tasks = [
            asyncio.create_task(self._consume_optional(telemetry.fixedwing_metrics(), _fixedwing_metrics))
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in (*pending, *optional_tasks):
            task.cancel()
        await asyncio.gather(*pending, *optional_tasks, return_exceptions=True)
        for task in done:
            exception = task.exception() if not task.cancelled() else None
            if exception:
                logger.warning(
                    "px4_telemetry_stream_ended", extra={"event": "px4_telemetry_stream_ended"}, exc_info=exception
                )

    async def _consume(self, stream: Any, mapper: Callable[[Any], dict[str, Any]]) -> None:
        async for value in stream:
            changes = mapper(value)
            if changes:
                await self.hub.publish(source="px4", connected=True, connection_state="connected", **changes)

    async def _consume_optional(self, stream: Any, mapper: Callable[[Any], dict[str, Any]]) -> None:
        try:
            await self._consume(stream, mapper)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug(
                "optional_px4_stream_unavailable",
                extra={"event": "optional_px4_stream_unavailable", "category": type(exc).__name__},
            )

    async def _watch_disconnect(self, system: Any) -> None:
        async for state in system.core.connection_state():
            if not state.is_connected:
                return

    async def upload_mission(self, waypoints: list[dict[str, Any]]) -> None:
        if self.system is None:
            raise ConnectionError("No active MAVSDK vehicle connection")
        from mavsdk.mission_raw import MissionItem

        items = [
            MissionItem(
                seq=index,
                frame=6,  # MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
                command=16,  # MAV_CMD_NAV_WAYPOINT; param1 carries the requested loiter time
                current=1 if index == 0 else 0,
                autocontinue=1,
                param1=float(point["hold_time_s"]),
                param2=1.0,
                param3=0.0,
                param4=float("nan"),
                x=int(round(float(point["latitude"]) * 10_000_000)),
                y=int(round(float(point["longitude"]) * 10_000_000)),
                z=float(point["altitude_m"]),
                mission_type=0,
            )
            for index, point in enumerate(waypoints)
        ]
        await self.system.mission_raw.upload_mission(items)

    async def stop(self) -> None:
        self._stop.set()
        self._reconnect_requested.set()


def _position(value: Any) -> dict[str, Any]:
    return {
        "latitude": float(value.latitude_deg),
        "longitude": float(value.longitude_deg),
        "absolute_altitude_m": float(value.absolute_altitude_m),
        "relative_altitude_m": float(value.relative_altitude_m),
    }


def _attitude(value: Any) -> dict[str, Any]:
    return {"heading_deg": float(value.yaw_deg) % 360.0}


def _velocity(value: Any) -> dict[str, Any]:
    north, east = float(value.north_m_s), float(value.east_m_s)
    return {"ground_speed_m_s": math.hypot(north, east)}


def _battery(value: Any) -> dict[str, Any]:
    remaining = _optional_float(getattr(value, "remaining_percent", None))
    return {
        "battery_remaining_pct": remaining,
        "battery_voltage_v": _optional_float(getattr(value, "voltage_v", None)),
        "battery_current_a": _optional_float(getattr(value, "current_battery_a", None)),
    }


def _gps(value: Any) -> dict[str, Any]:
    fix = getattr(value, "fix_type", None)
    return {
        "gps_satellites": int(value.num_satellites),
        "gps_fix_type": str(fix).split(".")[-1].replace("_", " ") if fix is not None else None,
    }


def _health(value: Any) -> dict[str, Any]:
    gyro = bool(value.is_gyrometer_calibration_ok)
    accel = bool(value.is_accelerometer_calibration_ok)
    mag = bool(value.is_magnetometer_calibration_ok)
    local = bool(value.is_local_position_ok)
    global_position = bool(value.is_global_position_ok)
    home = bool(value.is_home_position_ok)
    return {
        "gyro_ok": gyro,
        "accelerometer_ok": accel,
        "magnetometer_ok": mag,
        "local_position_ok": local,
        "global_position_ok": global_position,
        "home_position_ok": home,
        "ekf_ok": local and global_position,
    }


def _flight_mode(value: Any) -> dict[str, Any]:
    return {"flight_mode": str(value).split(".")[-1].replace("_", " ").upper()}


def _home(value: Any) -> dict[str, Any]:
    # MAVSDK 2.x streams Home as a Position directly (not as Home.position).
    position = getattr(value, "position", value)
    if not hasattr(position, "latitude_deg"):
        return {"home_position": None}
    return {
        "home_position": {
            "latitude": float(position.latitude_deg),
            "longitude": float(position.longitude_deg),
            "altitude_m": float(position.absolute_altitude_m),
        }
    }


def _fixedwing_metrics(value: Any) -> dict[str, Any]:
    airspeed = _optional_float(getattr(value, "airspeed_m_s", None))
    return {"airspeed_m_s": airspeed}


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value) if value is not None else None
        return parsed if parsed is not None and math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None
