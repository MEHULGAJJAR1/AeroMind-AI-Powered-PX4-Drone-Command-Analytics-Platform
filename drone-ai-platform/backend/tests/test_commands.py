from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas import CommandRequest
from app.services.commands import DroneCommandService


class FakeAction:
    def __init__(self):
        self.called = []

    async def arm(self):
        self.called.append("arm")

    async def disarm(self):
        self.called.append("disarm")

    async def hold(self):
        self.called.append("hold")

    async def land(self):
        self.called.append("land")

    async def return_to_launch(self):
        self.called.append("rtl")

    async def set_takeoff_altitude(self, value):
        self.called.append(("altitude", value))

    async def takeoff(self):
        self.called.append("takeoff")


class FakeHub:
    def __init__(self, state):
        self.latest = state

    async def record_system_event(self, *args, **kwargs):
        pass


@pytest.mark.asyncio
async def test_mock_mode_never_sends_vehicle_commands():
    action = FakeAction()
    connector = SimpleNamespace(system=SimpleNamespace(action=action))
    service = DroneCommandService(
        FakeHub({"connected": True, "source": "mock"}), connector, Settings(telemetry_mode="mock")
    )
    with pytest.raises(AppError, match="disabled"):
        await service.execute(CommandRequest(command="arm"))
    assert action.called == []


@pytest.mark.asyncio
async def test_disconnected_px4_command_is_rejected_before_mavsdk():
    action = FakeAction()
    connector = SimpleNamespace(system=SimpleNamespace(action=action))
    service = DroneCommandService(FakeHub({"connected": False}), connector, Settings(telemetry_mode="px4"))
    with pytest.raises(AppError, match="disconnected"):
        await service.execute(CommandRequest(command="rtl"))
    assert action.called == []


@pytest.mark.asyncio
async def test_disarm_is_blocked_in_air_and_arm_requires_health_and_home():
    action = FakeAction()
    connector = SimpleNamespace(system=SimpleNamespace(action=action))
    in_air = {"connected": True, "armed": True, "in_air": True, "source": "px4"}
    service = DroneCommandService(FakeHub(in_air), connector, Settings(telemetry_mode="px4"))
    with pytest.raises(AppError, match="airborne"):
        await service.execute(CommandRequest(command="disarm"))
    not_ready = {
        "connected": True,
        "armed": False,
        "in_air": False,
        "ekf_ok": False,
        "global_position_ok": True,
        "home_position": {},
    }
    service.hub = FakeHub(not_ready)
    with pytest.raises(AppError, match="health"):
        await service.execute(CommandRequest(command="arm"))
    assert action.called == []


@pytest.mark.asyncio
async def test_arm_command_is_sent_only_after_preflight_state_checks():
    action = FakeAction()
    connector = SimpleNamespace(system=SimpleNamespace(action=action))
    state = {
        "connected": True,
        "armed": False,
        "in_air": False,
        "ekf_ok": True,
        "global_position_ok": True,
        "gps_satellites": 12,
        "home_position": {"latitude": 1, "longitude": 2},
    }
    service = DroneCommandService(FakeHub(state), connector, Settings(telemetry_mode="px4"))
    result = await service.execute(CommandRequest(command="arm"))
    assert result.accepted
    assert action.called == ["arm"]
