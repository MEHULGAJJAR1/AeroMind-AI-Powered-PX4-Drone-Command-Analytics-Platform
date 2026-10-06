from types import SimpleNamespace

from app.services.px4 import _attitude, _battery, _health, _home, _position, _velocity


def test_px4_stream_mappers_normalize_mavsdk_values():
    position = SimpleNamespace(
        latitude_deg=47.3, longitude_deg=8.5, absolute_altitude_m=500.0, relative_altitude_m=30.0
    )
    assert _position(position) == {
        "latitude": 47.3,
        "longitude": 8.5,
        "absolute_altitude_m": 500.0,
        "relative_altitude_m": 30.0,
    }
    assert _attitude(SimpleNamespace(yaw_deg=-30)) == {"heading_deg": 330.0}
    assert _velocity(SimpleNamespace(north_m_s=3, east_m_s=4))["ground_speed_m_s"] == 5
    assert (
        _battery(SimpleNamespace(remaining_percent=75.0, voltage_v=15.2, current_battery_a=2.1))[
            "battery_remaining_pct"
        ]
        == 75.0
    )
    assert (
        _battery(SimpleNamespace(remaining_percent=1.0, voltage_v=15.2, current_battery_a=2.1))["battery_remaining_pct"]
        == 1.0
    )
    assert (
        _home(SimpleNamespace(latitude_deg=47.3, longitude_deg=8.5, absolute_altitude_m=500.0))["home_position"][
            "latitude"
        ]
        == 47.3
    )
    health = _health(
        SimpleNamespace(
            is_gyrometer_calibration_ok=True,
            is_accelerometer_calibration_ok=True,
            is_magnetometer_calibration_ok=True,
            is_local_position_ok=True,
            is_global_position_ok=True,
            is_home_position_ok=True,
        )
    )
    assert health["ekf_ok"] is True
    assert health["home_position_ok"] is True
