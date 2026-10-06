import pytest

from app.services.ws_tickets import WebSocketTicketStore


@pytest.mark.asyncio
async def test_websocket_ticket_is_single_use_and_bound_to_user():
    store = WebSocketTicketStore(ttl_seconds=45)
    ticket = await store.issue("operator-123")
    assert await store.consume(ticket) == "operator-123"
    assert await store.consume(ticket) is None
    assert await store.consume("invalid-ticket") is None
