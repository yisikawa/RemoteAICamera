"""WebSocket connection manager"""
from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        """Accept and add connection"""
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket connected. Active connections: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        """Remove connection"""
        self.active.remove(ws)
        logger.info(f"WebSocket disconnected. Active connections: {len(self.active)}")

    async def broadcast(self, payload: dict):
        """Broadcast message to all connected clients"""
        if not self.active:
            return

        disconnected = []
        for ws in self.active:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.debug(f"WebSocket send error: {e}")
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()
