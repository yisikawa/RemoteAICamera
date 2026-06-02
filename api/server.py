"""FastAPI server for RemoteAICamera dashboard"""
import asyncio
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from api.ws_manager import manager
from api.routes import stats, events, media, persons, vehicles

app = FastAPI(title="RemoteAICamera API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stats.router)
app.include_router(events.router)
app.include_router(media.router)
app.include_router(persons.router)
app.include_router(vehicles.router)

project_root = Path(__file__).parent.parent
data_dir = project_root / "data"

try:
    snapshots_dir = data_dir / "snapshots"
    if snapshots_dir.exists():
        app.mount("/media/snapshots", StaticFiles(directory=snapshots_dir), name="snapshots")
except Exception as e:
    logger.warning(f"Could not mount snapshots directory: {e}")

try:
    clips_dir = data_dir / "clips"
    if clips_dir.exists():
        app.mount("/media/clips", StaticFiles(directory=clips_dir), name="clips")
except Exception as e:
    logger.warning(f"Could not mount clips directory: {e}")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket connection for real-time event notifications"""
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        logger.debug(f"WebSocket error: {e}")
        manager.disconnect(ws)


@app.on_event("startup")
async def startup():
    """Startup event"""
    logger.info("RemoteAICamera API server started")


@app.on_event("shutdown")
async def shutdown():
    """Shutdown event"""
    logger.info("RemoteAICamera API server stopped")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
