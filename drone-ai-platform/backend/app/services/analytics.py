from __future__ import annotations

import logging
import math
from collections import deque
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)
_FEATURES = ("relative_altitude_m", "ground_speed_m_s", "battery_remaining_pct", "gps_satellites")


class TelemetryAnalytics:
    """Rule-based safety checks plus a rolling IsolationForest for explainable outliers."""

    def __init__(self, *, max_altitude_m: float = 120.0, max_speed_m_s: float = 25.0) -> None:
        self.max_altitude_m = max_altitude_m
        self.max_speed_m_s = max_speed_m_s
        self._samples: deque[dict[str, Any]] = deque(maxlen=240)
        self._model: IsolationForest | None = None
        self._updates_since_fit = 0
        self._last_sample_timestamp: str | None = None

    def evaluate(self, sample: dict[str, Any], history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        timestamp = sample.get("timestamp")
        if timestamp != self._last_sample_timestamp:
            self._samples.append({key: sample.get(key) for key in _FEATURES})
            self._last_sample_timestamp = timestamp
        samples = history if history is not None else list(self._samples)
        alerts: list[dict[str, str]] = []

        def add(severity: str, category: str, title: str, message: str) -> None:
            alerts.append({"severity": severity, "category": category, "title": title, "message": message})

        altitude = _number(sample.get("relative_altitude_m"))
        speed = _number(sample.get("ground_speed_m_s"))
        battery = _number(sample.get("battery_remaining_pct"))
        satellites = _number(sample.get("gps_satellites"))
        if altitude is not None and altitude > self.max_altitude_m:
            add(
                "CRITICAL",
                "ALTITUDE",
                "Altitude limit exceeded",
                f"Relative altitude is {altitude:.1f} m; configured limit is {self.max_altitude_m:.0f} m.",
            )
        elif altitude is not None and altitude > self.max_altitude_m * 0.85:
            add(
                "WARNING",
                "ALTITUDE",
                "Approaching altitude limit",
                f"Relative altitude is {altitude:.1f} m, near the configured {self.max_altitude_m:.0f} m limit.",
            )
        if speed is not None and speed > self.max_speed_m_s:
            add(
                "CRITICAL",
                "SPEED",
                "Speed limit exceeded",
                f"Ground speed is {speed:.1f} m/s; configured limit is {self.max_speed_m_s:.0f} m/s.",
            )
        elif speed is not None and speed > self.max_speed_m_s * 0.85:
            add(
                "WARNING",
                "SPEED",
                "High ground speed",
                f"Ground speed is {speed:.1f} m/s, approaching the configured limit.",
            )
        if battery is not None and battery < 10:
            add(
                "CRITICAL",
                "BATTERY",
                "Critical battery",
                f"Battery remaining is {battery:.0f}%; land or return to launch immediately.",
            )
        elif battery is not None and battery < 20:
            add("WARNING", "BATTERY", "Low battery", f"Battery remaining is {battery:.0f}%; plan a safe landing.")
        if sample.get("connected") and satellites is not None and satellites < 6:
            add(
                "WARNING",
                "GPS",
                "Weak GPS reception",
                f"Only {int(satellites)} satellites are reported; position reliability may be reduced.",
            )
        gps_anomaly = _gps_position_anomaly(sample, samples, self.max_speed_m_s)
        if gps_anomaly:
            add(gps_anomaly[0], "GPS_ANOMALY", gps_anomaly[1], gps_anomaly[2])
        if sample.get("connected") and sample.get("ekf_ok") is False:
            add("CRITICAL", "ESTIMATOR", "Estimator health degraded", "PX4 reports an unhealthy EKF/estimator state.")
        for sensor_name, label in (
            ("gyro_ok", "Gyroscope"),
            ("accelerometer_ok", "Accelerometer"),
            ("magnetometer_ok", "Magnetometer"),
        ):
            if sample.get(sensor_name) is False:
                add(
                    "WARNING",
                    "SENSOR",
                    f"{label} health check failed",
                    f"PX4 reports that the {label.lower()} is not calibrated or healthy.",
                )

        ml_alert = self._check_outlier(sample, samples)
        if ml_alert:
            alerts.append(ml_alert)

        severity_points = {"CRITICAL": 32, "WARNING": 13, "INFO": 2}
        risk_score = min(100, 5 + sum(severity_points.get(item["severity"], 0) for item in alerts))
        health_score = 100
        if sample.get("ekf_ok") is False:
            health_score -= 28
        if sample.get("global_position_ok") is False:
            health_score -= 18
        if any(sample.get(name) is False for name in ("gyro_ok", "accelerometer_ok", "magnetometer_ok")):
            health_score -= 18
        if satellites is not None and satellites < 6:
            health_score -= 15
        if battery is not None and battery < 20:
            health_score -= 12
        health_score = max(0, min(100, health_score))
        recommendations = list(dict.fromkeys(_recommendation(item["category"]) for item in alerts))
        if not recommendations:
            recommendations = ["Continue monitoring telemetry; no actionable anomaly is present."]
        return {
            "flight_risk_score": risk_score,
            "drone_health_score": health_score,
            "anomaly_count": len(alerts),
            "active_alerts": alerts,
            "warnings": [item["message"] for item in alerts if item["severity"] in ("WARNING", "CRITICAL")],
            "recommendations": recommendations,
        }

    def _check_outlier(self, current: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, str] | None:
        rows = [row for row in history if all(_number(row.get(feature)) is not None for feature in _FEATURES)]
        if len(rows) < 24 or not all(_number(current.get(feature)) is not None for feature in _FEATURES):
            return None
        try:
            frame = pd.DataFrame([{name: float(row[name]) for name in _FEATURES} for row in rows])
            values = frame.to_numpy(dtype=float)
            if not np.isfinite(values).all():
                return None
            self._updates_since_fit += 1
            if self._model is None or self._updates_since_fit >= 10:
                # Fit on the stable prefix; leave the newest sample out of the baseline.
                training = values[:-1]
                if len(training) < 20:
                    return None
                self._model = IsolationForest(n_estimators=80, contamination="auto", random_state=17)
                self._model.fit(training)
                self._updates_since_fit = 0
            current_row = np.asarray([[float(current[name]) for name in _FEATURES]], dtype=float)
            is_outlier = int(self._model.predict(current_row)[0]) == -1
            baseline = values[:-1]
            median = np.median(baseline, axis=0)
            mad = np.median(np.abs(baseline - median), axis=0)
            scale = np.maximum(1.4826 * mad, np.asarray([1.5, 0.8, 2.0, 1.0]))
            z_scores = np.abs((current_row[0] - median) / scale)
            worst = int(np.argmax(z_scores))
            if is_outlier and z_scores[worst] >= 3.5:
                label = _FEATURES[worst].replace("_", " ")
                return {
                    "severity": "WARNING",
                    "category": "ML_ANOMALY",
                    "title": "Unusual telemetry pattern",
                    "message": (
                        f"IsolationForest flagged an outlier; {label} differs materially from the recent baseline."
                    ),
                }
        except Exception:
            logger.exception("telemetry_anomaly_model_failed")
        return None


def _gps_position_anomaly(
    current: dict[str, Any], history: list[dict[str, Any]], max_speed_m_s: float
) -> tuple[str, str, str] | None:
    latitude = _number(current.get("latitude"))
    longitude = _number(current.get("longitude"))
    if latitude is None or longitude is None:
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return ("CRITICAL", "Invalid GPS coordinates", "Latitude or longitude is outside the valid geographic range.")
    if not current.get("connected") or len(history) < 2:
        return None
    previous = next(
        (
            row
            for row in reversed(history[:-1])
            if _number(row.get("latitude")) is not None and _number(row.get("longitude")) is not None
        ),
        None,
    )
    if previous is None:
        return None
    try:
        current_time = datetime.fromisoformat(str(current["timestamp"]).replace("Z", "+00:00"))
        previous_time = datetime.fromisoformat(str(previous["timestamp"]).replace("Z", "+00:00"))
        elapsed = (current_time - previous_time).total_seconds()
        if elapsed < 0.2 or elapsed > 10:
            return None
        previous_lat = float(previous["latitude"])
        previous_lon = float(previous["longitude"])
        radius = 6_371_000.0
        phi1, phi2 = math.radians(previous_lat), math.radians(latitude)
        delta_phi = math.radians(latitude - previous_lat)
        delta_lon = math.radians(longitude - previous_lon)
        value = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
        displacement = radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))
        apparent_speed = displacement / elapsed
        threshold = max(max_speed_m_s * 1.5, 40.0)
        if apparent_speed > threshold:
            severity = "CRITICAL" if apparent_speed > threshold * 2 else "WARNING"
            return (
                severity,
                "Position jump detected",
                (
                    f"GPS moved {displacement:.0f} m in {elapsed:.1f} s "
                    f"({apparent_speed:.1f} m/s), above the plausibility threshold."
                ),
            )
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _recommendation(category: str) -> str:
    return {
        "ALTITUDE": "Check geofence and altitude limits; reduce altitude if safe to do so.",
        "SPEED": "Reduce commanded speed and verify the vehicle is stable.",
        "BATTERY": "Initiate a safe return-to-launch or landing based on the operating area.",
        "GPS": "Avoid autonomous navigation until GNSS quality improves; verify estimator status.",
        "GPS_ANOMALY": (
            "Cross-check GNSS against inertial/position estimates and avoid autonomous maneuvers "
            "until the jump is resolved."
        ),
        "ESTIMATOR": "Pause autonomous maneuvers and follow the PX4 failsafe procedure.",
        "SENSOR": "Inspect sensor calibration and vehicle health before the next flight.",
        "ML_ANOMALY": "Review the recent telemetry window and inspect the flagged sensor channel.",
    }.get(category, "Review the alert and follow the approved operating procedure.")
