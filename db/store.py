"""データベース操作ファサード"""
from __future__ import annotations
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from sqlalchemy import or_
from .models import Base, DetectionEventRecord, EventSimilarity, KnownPerson, KnownVehicle, Snapshot
from pipeline.detector import DetectionEvent


class EventStore:
    def __init__(self, db_path: str = "data/events.db"):
        self._engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)
        self._migrate()
        logger.info(f"EventStore initialized: {db_path}")

    def _migrate(self):
        """既存DBへのカラム追加マイグレーション（冪等）"""
        with self._engine.connect() as conn:
            try:
                conn.execute(__import__("sqlalchemy").text(
                    "ALTER TABLE detection_events ADD COLUMN sub_category VARCHAR(64)"
                ))
                conn.commit()
                logger.info("Migration: sub_category column added")
            except Exception:
                pass  # 既にカラムが存在する場合はスキップ

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
        detections_json: Optional[list] = None,
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
                detection_type=detection_type or "other",
                frame_count=frame_count,
                snapshot_path=snapshot_path,
                clip_path=clip_path,
                detections_json=detections_json or [],
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

    def delete_event(self, event_id: str) -> bool:
        """イベントレコード・紐づくSnapshotレコード・ファイルを削除する"""
        with self._session() as s:
            record = s.query(DetectionEventRecord).filter_by(event_id=event_id).first()
            if not record:
                return False

            # ファイル削除
            for path_str in (record.snapshot_path, record.clip_path):
                if path_str:
                    p = Path(path_str)
                    if p.exists():
                        p.unlink()

            # Snapshot レコード削除
            s.query(Snapshot).filter_by(event_id=event_id).delete()

            # EventSimilarity レコード削除（検索元・一致先の両方向）
            s.query(EventSimilarity).filter(
                or_(EventSimilarity.event_id_a == event_id,
                    EventSimilarity.event_id_b == event_id)
            ).delete(synchronize_session=False)

            s.delete(record)
        logger.info(f"Event deleted: {event_id}")
        return True

    def delete_events_older_than(self, days: int) -> int:
        """指定日数より古いイベントとその関連ファイルを一括削除する"""
        from datetime import timedelta
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = today - timedelta(days=days - 1)
        with self._session() as s:
            records = s.query(DetectionEventRecord).filter(
                DetectionEventRecord.started_at < cutoff
            ).all()
            count = 0
            for record in records:
                for path_str in (record.snapshot_path, record.clip_path):
                    if path_str:
                        p = Path(path_str)
                        if p.exists():
                            p.unlink()
                s.query(Snapshot).filter_by(event_id=record.event_id).delete()
                s.query(EventSimilarity).filter(
                    or_(EventSimilarity.event_id_a == record.event_id,
                        EventSimilarity.event_id_b == record.event_id)
                ).delete(synchronize_session=False)
                s.delete(record)
                count += 1
        logger.info(f"Bulk deleted {count} events older than {days} days (cutoff: {cutoff})")
        return count

    def update_event_detection_type(self, event_id: str, detection_type: str):
        with self._session() as s:
            record = s.query(DetectionEventRecord).filter_by(event_id=event_id).first()
            if record:
                record.detection_type = detection_type
        logger.info(f"Event type updated: {event_id} → {detection_type}")

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
        categories = ["person", "car", "motorcycle", "bicycle", "pet", "other"]
        with self._session() as s:
            total = s.query(DetectionEventRecord).count()
            snapshots = s.query(Snapshot).count()
            counts = {
                cat: s.query(DetectionEventRecord).filter(
                    DetectionEventRecord.detection_type == cat
                ).count()
                for cat in categories
            }
        return {
            "total_events": total,
            "snapshots": snapshots,
            **counts,
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
            q = q.order_by(desc(DetectionEventRecord.started_at))
            if limit > 0:
                q = q.offset(offset).limit(limit)
            rows = q.all()
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

    # ------------------------------------------------------------------ #
    # 画像類似判定記録                                                      #
    # ------------------------------------------------------------------ #

    def save_similarity(self, event_id_a: str, event_id_b: str, reason: str):
        """SAME 判定結果を保存。同ペアの重複は上書きしない。"""
        with self._session() as s:
            existing = s.query(EventSimilarity).filter_by(
                event_id_a=event_id_a, event_id_b=event_id_b
            ).first()
            if not existing:
                s.add(EventSimilarity(
                    event_id_a=event_id_a,
                    event_id_b=event_id_b,
                    reason=reason,
                ))
        logger.debug(f"Similarity saved: {event_id_a} ~ {event_id_b}")

    def get_similarities(self, event_id: str) -> list[EventSimilarity]:
        """event_id が検索元・検索先どちらでも SAME 記録を返す"""
        with self._session() as s:
            rows = (
                s.query(EventSimilarity)
                .filter(or_(
                    EventSimilarity.event_id_a == event_id,
                    EventSimilarity.event_id_b == event_id,
                ))
                .order_by(desc(EventSimilarity.compared_at))
                .all()
            )
            s.expunge_all()
            return rows

    # ------------------------------------------------------------------ #
    #  サブカテゴリ分類                                                    #
    # ------------------------------------------------------------------ #

    def get_unclassified_events(self, detection_type: str | None = None) -> list[DetectionEventRecord]:
        """sub_category が未設定のイベントを返す（スナップショットあり限定・カテゴリ絞り込み可）"""
        with self._session() as s:
            q = (
                s.query(DetectionEventRecord)
                .filter(
                    DetectionEventRecord.sub_category.is_(None),
                    DetectionEventRecord.snapshot_path.isnot(None),
                )
            )
            if detection_type:
                q = q.filter(DetectionEventRecord.detection_type == detection_type)
            rows = q.order_by(desc(DetectionEventRecord.started_at)).all()
            s.expunge_all()
            return rows

    def update_sub_category(self, event_id: str, sub_category: str):
        """イベントのサブカテゴリを更新する"""
        with self._session() as s:
            s.query(DetectionEventRecord).filter_by(event_id=event_id).update(
                {"sub_category": sub_category}
            )

    def get_daily_sub_stats(self, detection_type: str, days: int = 14) -> dict:
        """日別×サブカテゴリの件数集計（直近 days 日分）"""
        from datetime import timedelta
        from sqlalchemy import func as _func
        cutoff = datetime.now() - timedelta(days=days)
        with self._session() as s:
            rows = (
                s.query(
                    _func.date(DetectionEventRecord.started_at).label("date"),
                    DetectionEventRecord.sub_category,
                    _func.count().label("count"),
                )
                .filter(
                    DetectionEventRecord.started_at >= cutoff,
                    DetectionEventRecord.detection_type == detection_type,
                    DetectionEventRecord.sub_category.isnot(None),
                )
                .group_by(
                    _func.date(DetectionEventRecord.started_at),
                    DetectionEventRecord.sub_category,
                )
                .order_by(_func.date(DetectionEventRecord.started_at))
                .all()
            )
        dates = sorted(set(str(r.date) for r in rows))
        sub_cats = list(dict.fromkeys(r.sub_category for r in rows if r.sub_category))
        pivot: dict[str, dict[str, int]] = {s: {d: 0 for d in dates} for s in sub_cats}
        for r in rows:
            if r.sub_category:
                pivot[r.sub_category][str(r.date)] = r.count
        return {
            "dates": dates,
            "sub_categories": {s: [pivot[s][d] for d in dates] for s in sub_cats},
        }

    def get_daily_stats(self, days: int = 14) -> list[dict]:
        """日別×カテゴリの件数集計を返す（直近 days 日分）"""
        from datetime import timedelta
        from sqlalchemy import func as _func, cast
        from sqlalchemy import Date
        cutoff = datetime.now() - timedelta(days=days)
        categories = ["person", "car", "motorcycle", "bicycle", "pet", "other"]
        with self._session() as s:
            rows = (
                s.query(
                    _func.date(DetectionEventRecord.started_at).label("date"),
                    DetectionEventRecord.detection_type,
                    _func.count().label("count"),
                )
                .filter(DetectionEventRecord.started_at >= cutoff)
                .group_by(
                    _func.date(DetectionEventRecord.started_at),
                    DetectionEventRecord.detection_type,
                )
                .order_by(_func.date(DetectionEventRecord.started_at))
                .all()
            )
        # 日付×カテゴリのマップに変換
        day_map: dict[str, dict] = {}
        for r in rows:
            d = str(r.date)
            if d not in day_map:
                day_map[d] = {cat: 0 for cat in categories}
                day_map[d]["date"] = d
            if r.detection_type in categories:
                day_map[d][r.detection_type] = r.count
        return sorted(day_map.values(), key=lambda x: x["date"])

    def get_sub_category_stats(self) -> list[dict]:
        """カテゴリ×サブカテゴリの件数集計を返す"""
        from sqlalchemy import func as _func
        with self._session() as s:
            rows = (
                s.query(
                    DetectionEventRecord.detection_type,
                    DetectionEventRecord.sub_category,
                    _func.count().label("count"),
                )
                .filter(DetectionEventRecord.sub_category.isnot(None))
                .group_by(
                    DetectionEventRecord.detection_type,
                    DetectionEventRecord.sub_category,
                )
                .all()
            )
            return [
                {"detection_type": r.detection_type, "sub_category": r.sub_category, "count": r.count}
                for r in rows
            ]
