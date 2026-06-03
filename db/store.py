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
        event: Optional[DetectionEvent] = None,
        snapshot_path: Optional[str] = None,
        clip_path: Optional[str] = None,
        # DirectCall用パラメータ (event=Noneの場合)
        event_id: Optional[str] = None,
        started_at: Optional[float] = None,
        ended_at: Optional[float] = None,
        detection_type: Optional[str] = None,
        frame_count: int = 0,
    ) -> DetectionEventRecord:
        """
        イベント記録。
        event: DetectionEvent を渡すか、event_id/started_at/... を直接指定。
        """
        if event:
            # DetectionEvent オブジェクトから
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
            event_id_log = event.event_id
        else:
            # 直接値から (ONVIF駆動型用)
            record = DetectionEventRecord(
                event_id=event_id,
                started_at=datetime.fromtimestamp(started_at) if started_at else datetime.now(),
                ended_at=datetime.fromtimestamp(ended_at) if ended_at else datetime.now(),
                duration_sec=round((ended_at or started_at or 0) - (started_at or 0), 2),
                detection_type=detection_type or "motion",
                frame_count=frame_count,
                snapshot_path=snapshot_path,
                clip_path=clip_path,
                detections_json=[],
            )
            event_id_log = event_id or "unknown"

        with self._session() as s:
            existing = s.query(DetectionEventRecord).filter_by(event_id=record.event_id).first()
            if existing:
                logger.warning(f"Duplicate event_id skipped: {record.event_id}")
                s.expunge(existing)
                return existing
            s.add(record)
        logger.debug(f"Event saved: {event_id_log} ({detection_type or 'motion'})")
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

    def get_all_vehicles(self) -> list:
        """is_active な全登録車両を返す"""
        with self._session() as s:
            rows = s.query(KnownVehicle).filter_by(is_active=True).all()
            s.expunge_all()
            return rows

    def update_vehicle_seen(self, label: str):
        """既知車両の最終通過時刻と通過回数を更新"""
        with self._session() as s:
            v = s.query(KnownVehicle).filter_by(label=label).first()
            if v:
                v.last_seen_at = datetime.now()
                v.visit_count = (v.visit_count or 0) + 1

    def update_person_seen(self, face_label: str):
        """既知人物の最終通過時刻と通過回数を更新"""
        with self._session() as s:
            person = s.query(KnownPerson).filter_by(label=face_label).first()
            if person:
                person.last_seen_at = datetime.now()
                person.visit_count = (person.visit_count or 0) + 1

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

    # ------------------------------------------------------------------ #
    # API用クエリ (Phase 4 ダッシュボード)                                  #
    # ------------------------------------------------------------------ #

    def get_event_by_id(self, event_id: str) -> Optional[DetectionEventRecord]:
        """単体イベント取得"""
        with self._session() as s:
            row = s.query(DetectionEventRecord).filter_by(event_id=event_id).first()
            if row:
                s.expunge(row)
            return row

    def get_events_filtered(
        self,
        detection_type: Optional[str] = None,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DetectionEventRecord], int]:
        """フィルタ付きイベント一覧 + 総件数"""
        with self._session() as s:
            q = s.query(DetectionEventRecord)

            if detection_type:
                q = q.filter(DetectionEventRecord.detection_type.like(f"%{detection_type}%"))

            if from_dt:
                q = q.filter(DetectionEventRecord.started_at >= from_dt)

            if to_dt:
                q = q.filter(DetectionEventRecord.started_at <= to_dt)

            total = q.count()
            rows = (
                q.order_by(desc(DetectionEventRecord.started_at))
                .offset(offset)
                .limit(limit)
                .all()
            )
            s.expunge_all()
            return rows, total

    def get_all_persons(self, active_only: bool = True) -> list[KnownPerson]:
        """人物マスタ一覧"""
        with self._session() as s:
            q = s.query(KnownPerson)
            if active_only:
                q = q.filter_by(is_active=True)
            rows = q.all()
            s.expunge_all()
            return rows

    def get_snapshots_by_event(self, event_id: str) -> list[Snapshot]:
        """イベント紐づけスナップショット一覧"""
        with self._session() as s:
            rows = (
                s.query(Snapshot)
                .filter_by(event_id=event_id)
                .order_by(Snapshot.taken_at)
                .all()
            )
            s.expunge_all()
            return rows
