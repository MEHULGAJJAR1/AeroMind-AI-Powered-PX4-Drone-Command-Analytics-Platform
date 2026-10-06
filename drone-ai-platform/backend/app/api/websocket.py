from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["telemetry stream"])


@router.websocket("/ws/telemetry")
async def telemetry_socket(websocket: WebSocket) -> None:
    ticket = websocket.query_params.get("ticket", "")
    user_id = await websocket.app.state.ws_tickets.consume(ticket) if ticket else None
    if user_id is None:
        await websocket.close(code=4401, reason="A fresh WebSocket ticket is required")
        return
    await websocket.accept()
    hub = websocket.app.state.hub
    queue = hub.subscribe()
    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=15.0)
                await websocket.send_json(message)
            except TimeoutError:
                await websocket.send_json({"type": "heartbeat", "timestamp": datetime.now(UTC).isoformat()})
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass
    finally:
        hub.unsubscribe(queue)
