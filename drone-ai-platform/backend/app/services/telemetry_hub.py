from __future__ import annotations

import asyncio
import copy
import logging
import math
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Alert, Flight, SystemEvent, TelemetryRecord, utc_now
from app.services.analytics import TelemetryAnalytics

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    value = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1.0 - value)))


def _empty_snapshot(mode: str) -> dict[str, Any]:
    return {
        "timestamp": _utc_iso(),
        "connected": False,
        "connection_state": "offline" if mode != "mock" else "starting",
        "source": "mock" if mode == "mock" else ("px4" if mode == "px4" else "offline"),
        "armed": False,
        "in_air": False,
        "flight_mode": "UNKNOWN",
        "latitude": None,
        "longitude": None,
        "absolute_altitude_m": None,
        "relative_altitude_m": None,
        "ground_speed_m_s": None,
        "airspeed_m_s": None,
        "heading_deg": None,
        "battery_remaining_pct": None,
        "battery_voltage_v": None,
        "battery_current_a": None,
        "gps_satellites": None,
        "gps_fix_type": None,
        "ekf_ok": None,
        "global_position_ok": None,
        "local_position_ok": None,
        "home_position_ok": None,
        "gyro_ok": None,
        "accelerometer_ok": None,
        "magnetometer_ok": None,
        "home_position": None,
        "distance_from_home_m": None,
        "flight_time_seconds": 0,
        "link_quality_pct": None,
        "cpu_load_pct": None,
        "system_status": "Waiting for telemetry",
        "last_error": None,
        "flight_risk_score": 0,
        "drone_health_score": 100,
        "anomaly_count": 0,
        "active_alerts": [],
        "warnings": [],
        "recommendations": ["Connect a PX4 vehicle or use simulated telemetry to begin."],
    }


class TelemetryHub:
    def __init__(
        self,
        *,
        mode: str,
        session_factory: async_sessionmaker | None = None,
        persist_interval_s: float = 2.0,
        max_altitude_m: float = 120.0,
        max_speed_m_s: float = 25.0,
    ) -> None:
        self.mode = mode
        self._session_factory = session_factory
        self._persist_interval_s = persist_interval_s
        self._latest = _empty_snapshot(mode)
        self._history: deque[dict[str, Any]] = deque(maxlen=240)
        self._subscribers: set[asyncio.Queue] = set()
        self._update_lock = asyncio.Lock()
        self._persist_lock = asyncio.Lock()
        self._analytics = TelemetryAnalytics(max_altitude_m=max_altitude_m, max_speed_m_s=max_speed_m_s)
        self._last_persist_at = 0.0
        self._last_persisted_connection_state: str | None = None
        self.drone_id: str | None = None
        self._flight_started_at: float | None = None
        self._background_tasks: set[asyncio.Task] = set()
        self._open_flight_id: str | None = None
        self._flight_distance_m = 0.0
        self._last_flight_position: tuple[float, float] | None = None
        self._alert_last_emitted: dict[str, float] = {}
        self._mock_started = time.monotonic()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def latest(self) -> dict[str, Any]:
        return copy.deepcopy(self._latest)

    @property
    def history(self) -> list[dict[str, Any]]:
        return copy.deepcopy(list(self._history))

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=4)
        self._subscribers.add(queue)
        queue.put_nowait({"type": "telemetry", "data": self.latest})
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publish(self, **changes: Any) -> dict[str, Any]:
        async with self._update_lock:
            self._latest.update(changes)
            self._latest["timestamp"] = _utc_iso()
            self._update_derived_fields()
            sample = copy.deepcopy(self._latest)
            self._history.append(sample)
            analysis = await asyncio.to_thread(self._analytics.evaluate, sample, list(self._history))
            self._latest.update(analysis)
            snapshot = copy.deepcopy(self._latest)
            now = time.monotonic()
            should_persist = (
                self._session_factory is not None and now - self._last_persist_at >= self._persist_interval_s
            )
            if should_persist:
                self._last_persist_at = now
                task = asyncio.create_task(self._persist_snapshot(snapshot))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

        message = {"type": "telemetry", "data": snapshot}
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass
        return snapshot

    def _update_derived_fields(self) -> None:
        current = time.monotonic()
        in_air = bool(self._latest.get("in_air"))
        if in_air:
            if self._flight_started_at is None:
                self._flight_started_at = current
            self._latest["flight_time_seconds"] = max(0, int(current - self._flight_started_at))
        else:
            self._flight_started_at = None
            self._latest["flight_time_seconds"] = 0

        home = self._latest.get("home_position")
        lat, lon = self._latest.get("latitude"), self._latest.get("longitude")
        if isinstance(home, dict) and lat is not None and lon is not None:
            home_lat, home_lon = home.get("latitude"), home.get("longitude")
            if home_lat is not None and home_lon is not None:
                self._latest["distance_from_home_m"] = round(
                    _distance_m(float(home_lat), float(home_lon), float(lat), float(lon)), 1
                )
        self._latest["connection_state"] = (
            "connected" if self._latest.get("connected") else self._latest.get("connection_state", "offline")
        )

    async def run_mock(self, tick_seconds: float = 1.0, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        self._mock_started = time.monotonic()
        while not stop_event.is_set():
            elapsed = time.monotonic() - self._mock_started
            phase = elapsed * 0.035
            home_lat, home_lon = 47.397742, 8.545594
            radius = 0.00014
            lat = home_lat + radius * math.sin(phase)
            lon = home_lon + radius * math.cos(phase)
            battery = max(35.0, 94.0 - elapsed * 0.018)
            await self.publish(
                connected=True,
                connection_state="connected",
                source="mock",
                armed=True,
                in_air=True,
                flight_mode="HOLD",
                latitude=lat,
                longitude=lon,
                absolute_altitude_m=535.0 + 32.0 + 2.5 * math.sin(phase * 0.8),
                relative_altitude_m=32.0 + 2.5 * math.sin(phase * 0.8),
                ground_speed_m_s=4.2 + 0.7 * math.sin(phase),
                airspeed_m_s=None,
                heading_deg=(phase * 180 / math.pi + 90.0) % 360,
                battery_remaining_pct=battery,
                battery_voltage_v=16.2 + (battery - 90.0) * 0.035,
                battery_current_a=5.4 + 0.6 * math.sin(phase),
                gps_satellites=16,
                gps_fix_type="3D",
                ekf_ok=True,
                global_position_ok=True,
                local_position_ok=True,
                home_position_ok=True,
                gyro_ok=True,
                accelerometer_ok=True,
                magnetometer_ok=True,
                home_position={"latitude": home_lat, "longitude": home_lon, "altitude_m": 535.0},
                link_quality_pct=98.0,
                cpu_load_pct=None,
                system_status="Simulated SITL telemetry",
                last_error=None,
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=tick_seconds)
            except TimeoutError:
                pass

    async def _persist_snapshot(self, snapshot: dict[str, Any]) -> None:
        if self._session_factory is None:
            return
        async with self._persist_lock:
            try:
                timestamp = datetime.fromisoformat(snapshot["timestamp"])
                async with self._session_factory() as session:
                    session.add(
                        TelemetryRecord(
                            drone_id=self.drone_id,
                            timestamp=timestamp,
                            connected=bool(snapshot.get("connected")),
                            source=str(snapshot.get("source", "offline")),
                            latitude=snapshot.get("latitude"),
                            longitude=snapshot.get("longitude"),
                            relative_altitude_m=snapshot.get("relative_altitude_m"),
                            ground_speed_m_s=snapshot.get("ground_speed_m_s"),
                            heading_deg=snapshot.get("heading_deg"),
                            battery_remaining_pct=snapshot.get("battery_remaining_pct"),
                            battery_voltage_v=snapshot.get("battery_voltage_v"),
                            gps_satellites=snapshot.get("gps_satellites"),
                            armed=bool(snapshot.get("armed")),
                            in_air=bool(snapshot.get("in_air")),
                            flight_mode=str(snapshot.get("flight_mode", "UNKNOWN")),
                            flight_risk_score=int(snapshot.get("flight_risk_score", 0)),
                            drone_health_score=int(snapshot.get("drone_health_score", 100)),
                            payload=snapshot,
                        )
                    )
                    await self._record_flight(session, snapshot, timestamp)
                    await self._record_alerts(session, snapshot)
                    connection_state = str(snapshot.get("connection_state", "offline"))
                    if connection_state != self._last_persisted_connection_state:
                        is_connected = bool(snapshot.get("connected"))
                        session.add(
                            SystemEvent(
                                level="INFO" if is_connected else "WARNING",
                                category="TELEMETRY_LINK",
                                message=f"Telemetry link {connection_state}",
                                created_at=utc_now(),
                                details={"source": snapshot.get("source"), "connected": is_connected},
                            )
                        )
                        self._last_persisted_connection_state = connection_state
                    await session.commit()
            except Exception:
                logger.exception("telemetry_persistence_failed")

    async def _record_flight(self, session: Any, snapshot: dict[str, Any], timestamp: datetime) -> None:
        if snapshot.get("in_air"):
            position = (snapshot.get("latitude"), snapshot.get("longitude"))
            if self._last_flight_position and all(value is not None for value in position):
                self._flight_distance_m += _distance_m(
                    self._last_flight_position[0], self._last_flight_position[1], float(position[0]), float(position[1])
                )
            if all(value is not None for value in position):
                self._last_flight_position = (float(position[0]), float(position[1]))
            if self._open_flight_id is None:
                flight = Flight(
                    drone_id=self.drone_id,
                    name="Simulated flight" if snapshot.get("source") == "mock" else "PX4 flight",
                    status="in_progress",
                    started_at=timestamp,
                    battery_start_pct=snapshot.get("battery_remaining_pct"),
                )
                session.add(flight)
                await session.flush()
                self._open_flight_id = flight.id
                self._flight_distance_m = 0.0
            flight = await session.get(Flight, self._open_flight_id)
            if flight:
                flight.duration_seconds = float(snapshot.get("flight_time_seconds") or 0)
                flight.max_altitude_m = max(flight.max_altitude_m, float(snapshot.get("relative_altitude_m") or 0))
                flight.distance_m = self._flight_distance_m
                flight.telemetry_count += 1
                flight.max_risk_score = max(flight.max_risk_score, int(snapshot.get("flight_risk_score") or 0))
                flight.battery_end_pct = snapshot.get("battery_remaining_pct")
        elif self._open_flight_id:
            flight = await session.get(Flight, self._open_flight_id)
            if flight:
                flight.status = "completed"
                flight.ended_at = timestamp
                flight.battery_end_pct = snapshot.get("battery_remaining_pct")
                flight.distance_m = self._flight_distance_m
            self._open_flight_id = None
            self._last_flight_position = None
            self._flight_distance_m = 0.0

    async def _record_alerts(self, session: Any, snapshot: dict[str, Any]) -> None:
        now = time.monotonic()
        for item in snapshot.get("active_alerts", []):
            key = f"{item.get('category')}:{item.get('title')}"
            if now - self._alert_last_emitted.get(key, -60.0) < 60.0:
                continue
            self._alert_last_emitted[key] = now
            session.add(
                Alert(
                    severity=item["severity"],
                    category=item["category"],
                    title=item["title"],
                    message=item["message"],
                    occurred_at=utc_now(),
                    details={"source": snapshot.get("source"), "timestamp": snapshot.get("timestamp")},
                )
            )

    async def record_system_event(
        self, category: str, message: str, *, level: str = "INFO", details: dict[str, Any] | None = None
    ) -> None:
        if self._session_factory is None:
            return
        try:
            async with self._session_factory() as session:
                session.add(
                    SystemEvent(
                        level=level, category=category, message=message, created_at=utc_now(), details=details or {}
                    )
                )
                await session.commit()
        except Exception:
            logger.exception("system_event_persistence_failed")

    async def close(self) -> None:
        for task in tuple(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
