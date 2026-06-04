"""Event-related endpoints"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import get_event_store
from db.store import EventStore

router = APIRouter(prefix="/api/events", tags=["events"])


class DetectionEventResponse(BaseModel):
    event_id: str
    started_at: str
    ended_at: str
    duration_sec: Optional[float]
    detection_type: str
    face_label: Optional[str]
    face_confidence: Optional[float]
    plate_number: Optional[str]
    plate_confidence: Optional[float]
    vehicle_color: Optional[str]
    vehicle_type: Optional[str]
    ai_description: Optional[str]
    snapshot_url: Optional[str]
    clip_url: Optional[str]
    frame_count: Optional[int]

    class Config:
        from_attributes = True


class EventsListResponse(BaseModel):
    items: list[DetectionEventResponse]
    total: int


class SnapshotResponse(BaseModel):
    file_path: str
    url: str
    taken_at: str
    snapshot_type: str
    width: Optional[int]
    height: Optional[int]
    file_size_bytes: Optional[int]

    class Config:
        from_attributes = True


def _path_to_url(file_path: Optional[str]) -> Optional[str]:
    """Convert file path to API URL"""
    if not file_path:
        return None
    try:
        p = Path(file_path)
        rel = p.relative_to("data")
        return f"/media/{rel.as_posix()}"
    except ValueError:
        return file_path


def _event_to_response(record) -> DetectionEventResponse:
    """Convert DB record to API response"""
    return DetectionEventResponse(
        event_id=record.event_id,
        started_at=record.started_at.isoformat() if record.started_at else None,
        ended_at=record.ended_at.isoformat() if record.ended_at else None,
        duration_sec=record.duration_sec,
        detection_type=record.detection_type,
        face_label=record.face_label,
        face_confidence=record.face_confidence,
        plate_number=record.plate_number,
        plate_confidence=record.plate_confidence,
        vehicle_color=record.vehicle_color,
        vehicle_type=record.vehicle_type,
        ai_description=record.ai_description,
        snapshot_url=_path_to_url(record.snapshot_path),
        clip_url=_path_to_url(record.clip_path),
        frame_count=record.frame_count,
    )


@router.get("", response_model=EventsListResponse)
def list_events(
    detection_type: Optional[str] = None,
    from_dt: Optional[str] = None,
    to_dt: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    store: EventStore = Depends(get_event_store),
):
    """List events with optional filters"""
    from_datetime = None
    to_datetime = None

    if from_dt:
        try:
            from_datetime = datetime.fromisoformat(from_dt)
        except ValueError:
            pass

    if to_dt:
        try:
            to_datetime = datetime.fromisoformat(to_dt)
        except ValueError:
            pass

    rows, total = store.get_events_filtered(
        detection_type=detection_type,
        from_dt=from_datetime,
        to_dt=to_datetime,
        limit=limit,
        offset=offset,
    )

    return EventsListResponse(
        items=[_event_to_response(r) for r in rows],
        total=total,
    )


@router.get("/{event_id}", response_model=DetectionEventResponse)
def get_event(event_id: str, store: EventStore = Depends(get_event_store)):
    """Get single event by ID"""
    record = store.get_event_by_id(event_id)
    if not record:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_to_response(record)


class EventUpdateRequest(BaseModel):
    detection_type: str


@router.patch("/{event_id}", response_model=DetectionEventResponse)
def update_event(event_id: str, body: EventUpdateRequest, store: EventStore = Depends(get_event_store)):
    """種別を手動修正する"""
    record = store.get_event_by_id(event_id)
    if not record:
        raise HTTPException(status_code=404, detail="Event not found")
    old_type = record.detection_type
    store.update_event_detection_type(event_id, body.detection_type)
    updated = store.get_event_by_id(event_id)
    from api.ws_manager import manager
    manager.broadcast_from_thread({
        "type": "type_updated",
        "event_id": event_id,
        "detection_type": body.detection_type,
        "old_detection_type": old_type,
    })
    return _event_to_response(updated)


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: str, store: EventStore = Depends(get_event_store)):
    """イベントとファイルを削除する"""
    record = store.get_event_by_id(event_id)
    if not record:
        raise HTTPException(status_code=404, detail="Event not found")
    detection_type = record.detection_type
    deleted = store.delete_event(event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    from api.ws_manager import manager
    manager.broadcast_from_thread({"type": "deleted", "event_id": event_id, "detection_type": detection_type})
    return Response(status_code=204)


@router.get("/{event_id}/similar/stream")
async def stream_similar_events(event_id: str, store: EventStore = Depends(get_event_store)):
    """SSE: 同カテゴリの直近N件と画像類似判定し、1件ずつストリームで返す"""
    from ai.identity_client import IdentityClient, SIMILAR_CANDIDATES_LIMIT

    target = store.get_event_by_id(event_id)
    if not target:
        raise HTTPException(status_code=404, detail="Event not found")
    if not target.snapshot_path or not Path(target.snapshot_path).exists():
        raise HTTPException(status_code=400, detail="No snapshot available for this event")

    rows, _ = store.get_events_filtered(
        detection_type=target.detection_type,
        limit=SIMILAR_CANDIDATES_LIMIT + 1,
    )
    already_compared = {row.event_id_b for row in store.get_similarities(event_id)}
    candidates = [
        r for r in rows
        if r.event_id != event_id
        and r.event_id not in already_compared
        and r.snapshot_path
        and Path(r.snapshot_path).exists()
    ][:SIMILAR_CANDIDATES_LIMIT]

    total = len(candidates)
    client = IdentityClient()

    async def generate():
        if total == 0:
            yield f"data: {json.dumps({'done': 0, 'total': 0, 'finished': True})}\n\n"
            return
        for i, candidate in enumerate(candidates):
            verdict, reason = await asyncio.to_thread(
                client.compare,
                target.snapshot_path,
                candidate.snapshot_path,
                target.detection_type,
                target.detections_json,
                candidate.detections_json,
            )
            if verdict == "SAME":
                await asyncio.to_thread(store.save_similarity, event_id, candidate.event_id, reason)
            payload = {
                "done": i + 1,
                "total": total,
                "event_id": candidate.event_id,
                "started_at": candidate.started_at.isoformat() if candidate.started_at else "",
                "detection_type": candidate.detection_type,
                "snapshot_url": _path_to_url(candidate.snapshot_path),
                "verdict": verdict,
                "reason": reason,
                "finished": False,
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': total, 'total': total, 'finished': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{event_id}/similarities")
def get_event_similarities(event_id: str, store: EventStore = Depends(get_event_store)):
    """DB に保存済みの類似判定結果を返す"""
    rows = store.get_similarities(event_id)
    results = []
    for row in rows:
        candidate = store.get_event_by_id(row.event_id_b)
        if candidate:
            results.append({
                "event_id": candidate.event_id,
                "started_at": candidate.started_at.isoformat() if candidate.started_at else "",
                "detection_type": candidate.detection_type,
                "snapshot_url": _path_to_url(candidate.snapshot_path),
                "verdict": "SAME",
                "reason": row.reason,
                "compared_at": row.compared_at.isoformat() if row.compared_at else "",
            })
    return results


@router.get("/{event_id}/snapshots", response_model=list[SnapshotResponse])
def get_event_snapshots(event_id: str, store: EventStore = Depends(get_event_store)):
    """Get snapshots for an event"""
    snapshots = store.get_snapshots_by_event(event_id)
    return [
        SnapshotResponse(
            file_path=s.file_path,
            url=_path_to_url(s.file_path),
            taken_at=s.taken_at.isoformat() if s.taken_at else None,
            snapshot_type=s.snapshot_type,
            width=s.width,
            height=s.height,
            file_size_bytes=s.file_size_bytes,
        )
        for s in snapshots
    ]
