from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_auth_missions_websocket_and_telemetry_persistence(tmp_path):
    settings = Settings(
        app_env="test",
        secret_key="integration-test-secret-is-long-and-random-looking",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        auto_create_schema=True,
        telemetry_mode="mock",
        mock_tick_seconds=0.1,
        telemetry_persist_interval_s=0.5,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register", json={"email": "operator@example.test", "password": "a-strong-test-password"}
        )
        assert response.status_code == 201
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert (
            client.post(
                "/api/auth/login", json={"email": "operator@example.test", "password": "incorrect-password"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/auth/login", json={"email": "operator@example.test", "password": "a-strong-test-password"}
            ).status_code
            == 200
        )

        assert client.get("/api/auth/me", headers=headers).status_code == 200
        assert client.get("/api/telemetry/latest", headers=headers).json()["source"] == "mock"

        mission = client.post(
            "/api/missions",
            headers=headers,
            json={
                "name": "Inspection route",
                "waypoints": [
                    {"latitude": 47.3977, "longitude": 8.5455, "altitude_m": 25, "hold_time_s": 0},
                    {"latitude": 47.3980, "longitude": 8.5460, "altitude_m": 30, "hold_time_s": 5},
                ],
            },
        )
        assert mission.status_code == 201, mission.text
        mission_data = mission.json()
        assert len(mission_data["waypoints"]) == 2
        assert mission_data["waypoints"][0]["sequence"] == 1
        reordered = client.put(
            f"/api/missions/{mission_data['id']}",
            headers=headers,
            json={"name": "Inspection route revised", "waypoints": list(reversed(mission_data["waypoints"]))},
        )
        assert reordered.status_code == 200, reordered.text
        assert reordered.json()["waypoints"][0]["latitude"] == 47.398

        upload = client.post(f"/api/missions/{mission_data['id']}/upload", headers=headers)
        assert upload.status_code == 409
        assert "PX4" in upload.json()["error"]["message"]

        ws_ticket = client.post("/api/auth/ws-ticket", headers=headers).json()["ticket"]
        with client.websocket_connect(f"/ws/telemetry?ticket={ws_ticket}") as socket:
            frame = socket.receive_json()
            assert frame["type"] == "telemetry"
            assert frame["data"]["source"] == "mock"
            assert frame["data"]["connected"] is True

        time.sleep(0.7)
        history = client.get("/api/telemetry/history?limit=5", headers=headers)
        assert history.status_code == 200
        assert len(history.json()) > 0
        selected_id = history.json()[-1]["id"]
        telemetry_csv = client.get(f"/api/telemetry/export.csv?ids={selected_id}", headers=headers)
        assert telemetry_csv.status_code == 200
        assert "relative_altitude_m" in telemetry_csv.text
        assert client.get("/api/system/status", headers=headers).json()["database"] == "online"
        events = client.get("/api/system/events", headers=headers)
        assert events.status_code == 200 and len(events.json()) > 0
        flights = client.get("/api/flights", headers=headers)
        assert flights.status_code == 200 and len(flights.json()) > 0


def test_protected_api_rejects_missing_token(tmp_path):
    app = create_app(
        Settings(
            app_env="test",
            secret_key="integration-test-secret-is-long-and-random-looking",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}",
            telemetry_mode="disabled",
        )
    )
    with TestClient(app) as client:
        assert client.get("/api/telemetry/latest").status_code == 401
