"""Person-related endpoints"""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_event_store
from db.store import EventStore

router = APIRouter(prefix="/api/persons", tags=["persons"])


class PersonResponse(BaseModel):
    id: int
    label: str
    display_name: Optional[str]
    visit_count: Optional[int]
    last_seen_at: Optional[str]

    class Config:
        from_attributes = True


@router.get("", response_model=list[PersonResponse])
def list_persons(store: EventStore = Depends(get_event_store)):
    """List all registered persons"""
    persons = store.get_all_persons(active_only=True)
    return [
        PersonResponse(
            id=p.id,
            label=p.label,
            display_name=p.display_name,
            visit_count=p.visit_count,
            last_seen_at=p.last_seen_at.isoformat() if p.last_seen_at else None,
        )
        for p in persons
    ]
