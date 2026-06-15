"""WebSocket connection manager for real-time chat streaming."""

from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    """Manages WebSocket connections grouped by conversation_id."""

    def __init__(self) -> None:
        # conversation_id → list of WebSocket connections
        self._conversation_connections: dict[str, list[WebSocket]] = defaultdict(list)
        # ws → conversation_id reverse lookup
        self._ws_conversation: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, conversation_id: str) -> None:
        """Accept a WebSocket connection and register it."""
        await websocket.accept()
        self._conversation_connections[conversation_id].append(websocket)
        self._ws_conversation[websocket] = conversation_id
        logger.info(f"WebSocket connected to conversation {conversation_id}")

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        conv_id = self._ws_conversation.pop(websocket, None)
        if conv_id and websocket in self._conversation_connections[conv_id]:
            self._conversation_connections[conv_id].remove(websocket)
            if not self._conversation_connections[conv_id]:
                del self._conversation_connections[conv_id]
        logger.debug(f"WebSocket disconnected from conversation {conv_id}")

    async def send_to_conversation(self, conversation_id: str, message: dict[str, Any]) -> None:
        """Send a JSON message to all connections subscribed to a conversation."""
        # Snapshot the list: a concurrent disconnect (e.g. from another
        # send_to_conversation or the route's finally block) can mutate the
        # underlying list while we await send_json below, which would skip
        # subscribers or raise "list changed size during iteration".
        connections = list(self._conversation_connections.get(conversation_id, []))
        stale = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)

        for ws in stale:
            self.disconnect(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        stale = []
        for ws in list(self._ws_conversation.keys()):
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)

        for ws in stale:
            self.disconnect(ws)

    @property
    def connection_count(self) -> int:
        return len(self._ws_conversation)


# Singleton
ws_manager = ConnectionManager()
