"""WebSocket connection manager"""
import asyncio
import threading
from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_lock = threading.Lock()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """uvicorn の asyncio ループを保存（startup 時に呼ぶ）"""
        with self._loop_lock:
            self._loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket connected. Active: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        logger.info(f"WebSocket disconnected. Active: {len(self.active)}")

    async def broadcast(self, payload: dict):
        """全接続クライアントへ JSON を送信（async コンテキストから呼ぶ）"""
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

    def broadcast_from_thread(self, payload: dict):
        """同期スレッドから安全に broadcast を呼ぶ"""
        with self._loop_lock:
            loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(payload), loop)


manager = ConnectionManager()
