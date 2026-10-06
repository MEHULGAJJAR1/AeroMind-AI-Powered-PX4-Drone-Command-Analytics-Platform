from __future__ import annotations

from typing import Any

from app.core.errors import AppError


def validate_waypoints(
    waypoints: list[Any], *, max_waypoints: int = 100, max_altitude_m: float = 120.0, for_upload: bool = False
) -> None:
    if len(waypoints) > max_waypoints:
        raise AppError(422, f"A mission may contain at most {max_waypoints} waypoints", code="mission_too_large")
    if for_upload and len(waypoints) < 2:
        raise AppError(422, "Upload requires at least two waypoints", code="mission_too_short")
    for index, point in enumerate(waypoints, start=1):
        latitude = float(_value(point, "latitude"))
        longitude = float(_value(point, "longitude"))
        altitude = float(_value(point, "altitude_m"))
        hold = float(_value(point, "hold_time_s", 0))
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise AppError(422, f"Waypoint {index} has invalid coordinates", code="invalid_coordinates")
        if not 0 < altitude <= max_altitude_m:
            raise AppError(
                422,
                f"Waypoint {index} altitude must be above 0 m and no higher than {max_altitude_m:g} m",
                code="altitude_out_of_range",
            )
        if not 0 <= hold <= 3600:
            raise AppError(
                422, f"Waypoint {index} hold time must be between 0 and 3600 seconds", code="invalid_hold_time"
            )


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)
