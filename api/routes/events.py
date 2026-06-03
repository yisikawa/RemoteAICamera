"""Event-related endpoints"""
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response
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


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: str, store: EventStore = Depends(get_event_store)):
    """イベントとファイルを削除する"""
    deleted = store.delete_event(event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    return Response(status_code=204)


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
