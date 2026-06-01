"""データベース操作ファサード"""
from __future__ import annotations
import json
from contextlib import contextmanager
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from .models import Base, DetectionEventRecord, KnownPerson, KnownVehicle, Snapshot
from pipeline.event_filter import DetectionEvent


class EventStore:
    def __init__(self, db_path: str = "data/events.db"):
        self._engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)
        logger.info(f"EventStore initialized: {db_path}")

    @contextmanager
    def _session(self):
        session: Session = self._Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------ #
    # イベント記録                                                          #
    # ------------------------------------------------------------------ #

    def save_event(
        self,
        event: DetectionEvent,
        snapshot_path: Optional[str] = None,
        clip_path: Optional[str] = None,
    ) -> DetectionEventRecord:
        detections_data = [
            {
                "class_name": d.class_name,
                "confidence": round(d.confidence, 4),
                "bbox": list(d.bbox),
            }
            for d in event.best_detections
        ]
        record = DetectionEventRecord(
            event_id=event.event_id,
            started_at=datetime.fromtimestamp(event.started_at),
            ended_at=datetime.fromtimestamp(event.ended_at),
            duration_sec=round(event.duration_sec, 2),
            detection_type=event.detection_type,
            frame_count=event.frame_count,
            snapshot_path=snapshot_path,
            clip_path=clip_path,
            detections_json=detections_data,
        )
        with self._session() as s:
            s.add(record)
        logger.debug(f"Event saved: {event.event_id} ({event.detection_type})")
        return record

    def update_event_recognition(
        self,
        event_id: str,
        face_label: Optional[str] = None,
        face_confidence: Optional[float] = None,
        plate_number: Optional[str] = None,
        plate_confidence: Optional[float] = None,
        vehicle_color: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        ai_description: Optional[str] = None,
    ):
        with self._session() as s:
            record = s.query(DetectionEventRecord).filter_by(event_id=event_id).first()
            if not record:
                logger.warning(f"Event not found: {event_id}")
                return
            if face_label is not None:
                record.face_label = face_label
            if face_confidence is not None:
                record.face_confidence = round(face_confidence, 4)
            if plate_number is not None:
                record.plate_number = plate_number
            if plate_confidence is not None:
                record.plate_confidence = round(plate_confidence, 4)
            if vehicle_color is not None:
                record.vehicle_color = vehicle_color
            if vehicle_type is not None:
                record.vehicle_type = vehicle_type
            if ai_description is not None:
                record.ai_description = ai_description

    # ------------------------------------------------------------------ #
    # クエリ                                                                #
    # ------------------------------------------------------------------ #

    def get_recent_events(self, limit: int = 50) -> list[DetectionEventRecord]:
        with self._session() as s:
            rows = (
                s.query(DetectionEventRecord)
                .order_by(desc(DetectionEventRecord.started_at))
                .limit(limit)
                .all()
            )
            s.expunge_all()
            return rows

    def get_events_by_label(self, face_label: str, limit: int = 100) -> list[DetectionEventRecord]:
        with self._session() as s:
            rows = (
                s.query(DetectionEventRecord)
                .filter(DetectionEventRecord.face_label == face_label)
                .order_by(desc(DetectionEventRecord.started_at))
                .limit(limit)
                .all()
            )
            s.expunge_all()
            return rows

    def get_events_by_plate(self, plate: str, limit: int = 100) -> list[DetectionEventRecord]:
        with self._session() as s:
            rows = (
                s.query(DetectionEventRecord)
                .filter(DetectionEventRecord.plate_number == plate)
                .order_by(desc(DetectionEventRecord.started_at))
                .limit(limit)
                .all()
            )
            s.expunge_all()
            return rows

    # ------------------------------------------------------------------ #
    # 静止画記録                                                            #
    # ------------------------------------------------------------------ #

    def save_snapshot_record(
        self,
        file_path: str,
        event_id: Optional[str] = None,
        snapshot_type: str = "event",
        width: Optional[int] = None,
        height: Optional[int] = None,
        file_size_bytes: Optional[int] = None,
    ) -> Snapshot:
        record = Snapshot(
            event_id=event_id,
            file_path=file_path,
            taken_at=datetime.now(),
            snapshot_type=snapshot_type,
            width=width,
            height=height,
            file_size_bytes=file_size_bytes,
        )
        with self._session() as s:
            s.add(record)
        return record

    # ------------------------------------------------------------------ #
    # 統計                                                                  #
    # ------------------------------------------------------------------ #

    def summary(self) -> dict:
        with self._session() as s:
            total = s.query(DetectionEventRecord).count()
            persons = s.query(DetectionEventRecord).filter(
                DetectionEventRecord.detection_type.contains("person")
            ).count()
            vehicles = s.query(DetectionEventRecord).filter(
                DetectionEventRecord.detection_type.contains("vehicle")
            ).count()
            snapshots = s.query(Snapshot).count()
        return {
            "total_events": total,
            "person_events": persons,
            "vehicle_events": vehicles,
            "snapshots": snapshots,
        }
