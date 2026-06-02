"""Vehicle-related endpoints"""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_event_store
from db.store import EventStore

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


class VehicleResponse(BaseModel):
    id: int
    label: str
    display_name: Optional[str]
    plate_number: Optional[str]
    vehicle_color: Optional[str]
    vehicle_type: Optional[str]
    visit_count: Optional[int]
    last_seen_at: Optional[str]

    class Config:
        from_attributes = True


@router.get("", response_model=list[VehicleResponse])
def list_vehicles(store: EventStore = Depends(get_event_store)):
    """List all registered vehicles"""
    vehicles = store.get_all_vehicles()
    return [
        VehicleResponse(
            id=v.id,
            label=v.label,
            display_name=v.display_name,
            plate_number=v.plate_number,
            vehicle_color=v.vehicle_color,
            vehicle_type=v.vehicle_type,
            visit_count=v.visit_count,
            last_seen_at=v.last_seen_at.isoformat() if v.last_seen_at else None,
        )
        for v in vehicles
    ]
