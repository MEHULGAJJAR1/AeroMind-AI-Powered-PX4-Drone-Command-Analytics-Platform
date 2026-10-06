import pytest

from app.core.errors import AppError
from app.services.mission_validation import validate_waypoints


def point(lat=47.4, lon=8.5, altitude=30, hold=0):
    return {"latitude": lat, "longitude": lon, "altitude_m": altitude, "hold_time_s": hold}


def test_mission_draft_accepts_empty_route_but_upload_requires_two_points():
    validate_waypoints([], for_upload=False)
    with pytest.raises(AppError, match="at least two"):
        validate_waypoints([point()], for_upload=True)


def test_valid_mission_and_hold_times():
    validate_waypoints([point(), point(lat=47.41, hold=15)], for_upload=True)


@pytest.mark.parametrize(
    "candidate", [point(lat=91), point(lon=-181), point(altitude=0), point(altitude=121), point(hold=-1)]
)
def test_invalid_waypoints_are_rejected(candidate):
    with pytest.raises(AppError):
        validate_waypoints([candidate], max_altitude_m=120)


def test_mission_waypoint_limit_is_enforced():
    with pytest.raises(AppError, match="at most"):
        validate_waypoints([point() for _ in range(3)], max_waypoints=2)
