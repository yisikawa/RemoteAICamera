"""Statistics endpoints"""
from fastapi import APIRouter, Depends

from api.deps import get_event_store
from db.store import EventStore

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
def get_summary(store: EventStore = Depends(get_event_store)):
    """Get session statistics summary"""
    return store.summary()
