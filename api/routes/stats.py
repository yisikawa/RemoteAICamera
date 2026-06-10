"""Statistics endpoints"""
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.deps import get_event_store
from db.store import EventStore

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
def get_summary(store: EventStore = Depends(get_event_store)):
    """Get session statistics summary"""
    return store.summary()


@router.get("/daily")
def get_daily_stats(days: int = 14, store: EventStore = Depends(get_event_store)):
    """日別×カテゴリの件数集計（直近 days 日分）"""
    return store.get_daily_stats(days=days)


@router.get("/daily-camera")
def get_daily_camera_stats(days: int = 14, store: EventStore = Depends(get_event_store)):
    """日別×カメラ×カテゴリの件数集計（直近 days 日分）"""
    return store.get_daily_stats_by_camera(days=days)


@router.get("/daily-sub-camera")
def get_daily_sub_camera_stats(
    detection_type: str,
    days: int = 14,
    store: EventStore = Depends(get_event_store),
):
    """日別×カメラ×サブカテゴリの件数集計（detection_type 指定必須）"""
    return store.get_daily_sub_stats_by_camera(detection_type=detection_type, days=days)


@router.get("/daily-sub")
def get_daily_sub_stats(
    detection_type: str,
    days: int = 14,
    store: EventStore = Depends(get_event_store),
):
    """日別×サブカテゴリの件数集計（detection_type 指定必須）"""
    return store.get_daily_sub_stats(detection_type=detection_type, days=days)


@router.get("/sub-categories")
def get_sub_category_stats(store: EventStore = Depends(get_event_store)):
    """カテゴリ×サブカテゴリの件数集計を返す"""
    return store.get_sub_category_stats()


@router.get("/classify/stream")
async def classify_stream(
    store: EventStore = Depends(get_event_store),
    detection_type: str | None = None,
):
    """SSE: 未分類イベントをサブカテゴリ分類し1件ずつ結果を返す（detection_type 指定で絞り込み可）"""
    from ai.sub_category_client import SubCategoryClient, classify_other, SUB_CATEGORIES
    from config import load_config

    targets = store.get_unclassified_events(detection_type=detection_type)
    total = len(targets)

    ollama_cfg = load_config().ollama
    client = SubCategoryClient(base_url=ollama_cfg.base_url, model=ollama_cfg.vision_model)

    async def generate():
        if total == 0:
            yield f"data: {json.dumps({'done': 0, 'total': 0, 'finished': True})}\n\n"
            return

        for i, event in enumerate(targets):
            if not event.snapshot_path or not Path(event.snapshot_path).exists():
                sub = "不明"
            elif event.detection_type == "other":
                sub = classify_other(event.detections_json)
            else:
                sub = await asyncio.to_thread(
                    client.classify, event.snapshot_path, event.detection_type
                )

            await asyncio.to_thread(store.update_sub_category, event.event_id, sub)

            payload = {
                "done": i + 1,
                "total": total,
                "event_id": event.event_id,
                "detection_type": event.detection_type,
                "sub_category": sub,
                "finished": i + 1 == total,
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
