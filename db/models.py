"""SQLAlchemy ORM モデル定義"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, DateTime,
    ForeignKey, JSON, Boolean, Text, Index, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class DetectionEventRecord(Base):
    """検出イベントログ (1通過 = 1レコード)"""
    __tablename__ = "detection_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, index=True)
    ended_at = Column(DateTime, nullable=False)
    duration_sec = Column(Float)
    detection_type = Column(String(32))        # person / vehicle / person+vehicle
    frame_count = Column(Integer)

    # 認識結果 (Phase 2 以降で埋まる)
    face_label = Column(String(128))           # 顔認識ラベル (登録名)
    face_confidence = Column(Float)
    plate_number = Column(String(32))          # ナンバープレート
    plate_confidence = Column(Float)
    vehicle_color = Column(String(32))
    vehicle_type = Column(String(32))
    ai_description = Column(Text)             # LM Studio による状況説明

    # ファイルパス
    snapshot_path = Column(String(512))
    clip_path = Column(String(512))

    detections_json = Column(JSON)            # 検出ボックス生データ
    sub_category = Column(String(64))         # サブカテゴリ（LLM分類結果）

    __table_args__ = (
        Index("ix_events_started_type", "started_at", "detection_type"),
    )


class EventSimilarity(Base):
    """画像類似判定結果（SAME のみ記録）"""
    __tablename__ = "event_similarities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id_a = Column(String(64), nullable=False, index=True)  # 検索元
    event_id_b = Column(String(64), nullable=False, index=True)  # 一致先
    reason = Column(Text)
    compared_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("event_id_a", "event_id_b", name="uq_similarity_pair"),
    )


class KnownPerson(Base):
    """登録済み人物マスター"""
    __tablename__ = "known_persons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(128), unique=True, nullable=False)
    display_name = Column(String(256))
    encoding_path = Column(String(512))       # face encoding numpy ファイルパス
    thumbnail_path = Column(String(512))
    note = Column(Text)
    registered_at = Column(DateTime, default=datetime.now)
    last_seen_at = Column(DateTime)
    visit_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class KnownVehicle(Base):
    """登録済み車両マスター (色・車種ベース、ナンバーは任意)"""
    __tablename__ = "known_vehicles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(128), unique=True, nullable=False)  # 識別ラベル
    display_name = Column(String(256))
    owner_label = Column(String(128))         # KnownPerson.label との対応
    vehicle_color = Column(String(32))        # 色名 (黒/白/シルバー/青 等)
    vehicle_color_hsv = Column(String(64))    # HSV値 "h,s,v" (色照合用)
    vehicle_type = Column(String(32))         # car/motorcycle/bus/truck
    plate_number = Column(String(32))         # ナンバー (任意・参考情報)
    thumbnail_path = Column(String(512))
    note = Column(Text)
    registered_at = Column(DateTime, default=datetime.now)
    last_seen_at = Column(DateTime)
    visit_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class Snapshot(Base):
    """静止画ファイル管理"""
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), index=True)
    file_path = Column(String(512), nullable=False)
    taken_at = Column(DateTime, nullable=False, default=datetime.now)
    snapshot_type = Column(String(32))        # "event" / "periodic" / "manual"
    width = Column(Integer)
    height = Column(Integer)
    file_size_bytes = Column(Integer)
