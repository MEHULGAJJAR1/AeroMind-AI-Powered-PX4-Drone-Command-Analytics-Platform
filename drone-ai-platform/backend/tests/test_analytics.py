from app.services.analytics import TelemetryAnalytics


def make_sample(**overrides):
    sample = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "connected": True,
        "relative_altitude_m": 30.0,
        "ground_speed_m_s": 4.0,
        "battery_remaining_pct": 88.0,
        "gps_satellites": 15,
        "ekf_ok": True,
        "global_position_ok": True,
        "gyro_ok": True,
        "accelerometer_ok": True,
        "magnetometer_ok": True,
    }
    return sample | overrides


def test_nominal_telemetry_has_low_risk_and_no_anomaly():
    result = TelemetryAnalytics().evaluate(make_sample())
    assert result["flight_risk_score"] == 5
    assert result["drone_health_score"] == 100
    assert result["active_alerts"] == []
    assert result["anomaly_count"] == 0


def test_hard_limits_and_sensor_failures_are_explainable():
    result = TelemetryAnalytics(max_altitude_m=100, max_speed_m_s=20).evaluate(
        make_sample(relative_altitude_m=115, ground_speed_m_s=23, battery_remaining_pct=8, gyro_ok=False)
    )
    categories = {alert["category"] for alert in result["active_alerts"]}
    assert {"ALTITUDE", "SPEED", "BATTERY", "SENSOR"} <= categories
    assert result["flight_risk_score"] == 100
    assert result["drone_health_score"] <= 70
    assert any("land" in item.lower() or "return" in item.lower() for item in result["recommendations"])


def test_gps_position_jump_is_detected_from_historical_displacement():
    engine = TelemetryAnalytics()
    previous = make_sample(timestamp="2026-01-01T00:00:00+00:00", latitude=47.3977, longitude=8.5455)
    current = make_sample(timestamp="2026-01-01T00:00:01+00:00", latitude=47.3990, longitude=8.5455)
    result = engine.evaluate(current, [previous, current])
    assert any(alert["category"] == "GPS_ANOMALY" for alert in result["active_alerts"])


def test_isolation_forest_flags_a_contextual_telemetry_outlier():
    engine = TelemetryAnalytics()
    baseline = [make_sample(timestamp=f"2026-01-01T00:00:{index:02d}+00:00") for index in range(40)]
    current = make_sample(timestamp="2026-01-01T00:00:41+00:00", relative_altitude_m=72.0)
    result = engine.evaluate(current, [*baseline, current])
    assert any(alert["category"] == "ML_ANOMALY" for alert in result["active_alerts"])
