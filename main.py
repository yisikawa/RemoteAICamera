"""
RemoteAICamera - ONVIF イベント駆動型
Tapo C520WS の ONVIF イベント (人物・車両検知) をトリガーに
15秒クリップを RTSP から抽出・分析してイベント記録する。

起動: python main.py
  → カメラワーカー + FastAPI サーバー (port 8000) を一括起動
"""
import sys
import time
import signal
import asyncio
import argparse
import threading
from pathlib import Path
from loguru import logger

from config import load_config, CameraConfig, AppConfig
from camera.rtsp_capture import RTSPCapture
from camera.tapo_client import TapoClient, MotionEvent
from pipeline.detector import YOLODetector
from pipeline.clip_analyzer import ClipAnalyzer
from storage.file_store import FileStore
from db.store import EventStore
from ai.sub_category_client import SubCategoryClient, classify_other


def setup_logging(level: str = "INFO", log_file: str = "data/app.log"):
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logger.configure(extra={"cam": "-"})
    logger.remove()
    logger.add(sys.stderr, level=level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | <cyan>{extra[cam]}</cyan> | {message}")
    logger.add(log_file, level=level, rotation="10 MB", retention=5,
               format="{time:YYYY-MM-DD HH:mm:ss} | {level:8} | {extra[cam]} | {message}")


def _start_api_server(host: str, port: int):
    """uvicorn を独立スレッドで起動する（ブロッキング）"""
    import uvicorn
    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )


def handle_clip(
    trigger_event: MotionEvent,
    cam_cfg: CameraConfig,
    capture: RTSPCapture,
    clip_analyzer: ClipAnalyzer,
    file_store: FileStore,
    event_store: EventStore,
    cfg: AppConfig,
    cam_log,
):
    """ONVIF イベント検知後、15秒クリップを収集・分析・保存する（バックグラウンドスレッド）"""
    try:
        event_id = f"{cam_cfg.name}_{trigger_event.timestamp:.0f}_{trigger_event.detection_type}"

        time.sleep(cfg.storage.clip_post_seconds)

        frames = capture.get_recent_frames(cfg.storage.clip_duration_sec)
        if not frames or len(frames) < 5:
            cam_log.warning(f"[{event_id}] Not enough frames: {len(frames) if frames else 0}")
            return

        frames_as_list = [(f.data, f.timestamp) for f in frames]

        result = clip_analyzer.analyze(frames_as_list, event_id=event_id, frame_interval=5)
        if not result:
            cam_log.warning(f"[{event_id}] Analysis failed")
            return

        # YOLOが未検出(other)の場合はONVIFトリガー種別をフォールバックとして使う
        _ONVIF_FALLBACK: dict[str, str] = {"vehicle": "car", "person": "person"}
        detection_type = result.detection_type
        if detection_type == "other" and trigger_event.detection_type in _ONVIF_FALLBACK:
            detection_type = _ONVIF_FALLBACK[trigger_event.detection_type]
            cam_log.debug(f"[{event_id}] YOLO=other → fallback to ONVIF:{trigger_event.detection_type} → {detection_type}")

        snapshot_path = file_store.save_snapshot(
            result.best_frame, event_id=event_id, prefix=cam_cfg.name
        )
        audio_wav = capture.get_wav_segment(frames_as_list[0][1], frames_as_list[-1][1])
        actual_fps = capture.fps if capture.fps > 1.0 else 15.0
        clip_path = file_store.save_clip(
            frames_as_list, event_id=event_id, fps=actual_fps, audio_wav=audio_wav
        )

        event_store.save_event(
            event_id=event_id,
            started_at=result.started_at,
            ended_at=result.ended_at,
            detection_type=detection_type,
            frame_count=result.frame_count,
            snapshot_path=snapshot_path,
            clip_path=clip_path,
            detections_json=[
                {
                    "class_id": d.class_id,
                    "class_name": d.class_name,
                    "category": d.category,
                    "confidence": round(d.confidence, 4),
                    "bbox": list(d.bbox),
                }
                for d in result.best_detections
            ],
        )
        event_store.save_snapshot_record(
            file_path=snapshot_path,
            event_id=event_id,
            snapshot_type="event",
            width=result.best_frame.shape[1],
            height=result.best_frame.shape[0],
            file_size_bytes=Path(snapshot_path).stat().st_size if snapshot_path else 0,
        )

        # LLM サブカテゴリ自動分類
        sub_cat = "不明"
        try:
            if detection_type == "other":
                sub_cat = classify_other([
                    {"class_name": d.class_name, "confidence": d.confidence}
                    for d in result.best_detections
                ])
            elif snapshot_path:
                sub_client = SubCategoryClient(
                    base_url=cfg.ollama.base_url,
                    model=cfg.ollama.vision_model,
                )
                sub_cat = sub_client.classify(snapshot_path, detection_type)
            event_store.update_sub_category(event_id, sub_cat)
        except Exception as e:
            cam_log.warning(f"[{event_id}] Auto-classification failed: {e}")

        cam_log.info(
            f"[EVENT] {event_id} | type={detection_type} | sub={sub_cat} | "
            f"confidence={result.best_confidence:.2f} | frames={result.frame_count} | "
            f"snapshot={Path(snapshot_path).name if snapshot_path else '?'} | "
            f"clip={Path(clip_path).name if clip_path else '?'}"
        )

        # WebSocket でリアルタイム通知
        try:
            from api.ws_manager import manager
            manager.broadcast_from_thread({
                "type": "new_event",
                "event_id": event_id,
                "camera": cam_cfg.name,
                "detection_type": detection_type,
                "sub_category": sub_cat,
                "confidence": round(result.best_confidence, 2),
                "snapshot_url": f"/media/snapshots/{Path(snapshot_path).relative_to('data/snapshots').as_posix()}" if snapshot_path else None,
            })
        except Exception:
            pass

    except Exception as e:
        cam_log.error(f"handle_clip error: {e}", exc_info=True)


def camera_worker(
    cam_cfg: CameraConfig,
    detector: YOLODetector,
    file_store: FileStore,
    event_store: EventStore,
    cfg: AppConfig,
    stop_event: threading.Event,
):
    cam_log = logger.bind(cam=cam_cfg.name)

    tapo = TapoClient(
        host=cam_cfg.host,
        stream_username=cam_cfg.stream_username,
        stream_password=cam_cfg.stream_password,
        onvif_port=cam_cfg.onvif_port,
    )
    if not tapo.connect():
        cam_log.warning("ONVIF unavailable — cannot poll events")
        return

    rtsp_url = (
        f"rtsp://{cam_cfg.stream_username}:{cam_cfg.stream_password}"
        f"@{cam_cfg.host}:554/stream{cam_cfg.rtsp_stream}"
    )
    capture = RTSPCapture(
        rtsp_url=rtsp_url,
        buffer_seconds=max(20, int(cfg.storage.clip_duration_sec) + 5),
        reconnect_interval=cam_cfg.reconnect_interval,
        audio_buffer_seconds=max(30, int(cfg.storage.clip_duration_sec) + 10),
    )
    capture.start()

    cam_log.info(f"Waiting for RTSP stream: {cam_cfg.host}")
    for _ in range(50):
        if capture.latest_frame():
            break
        time.sleep(0.2)
    else:
        cam_log.error("Cannot receive RTSP frames. Check IP / password.")
        capture.stop()
        return

    cam_log.info(f"Stream connected. FPS={capture.fps:.1f}")

    clip_analyzer = ClipAnalyzer(detector)

    cooldown_until: float = 0
    cooldown_sec = cfg.storage.clip_duration_sec

    while not stop_event.is_set():
        try:
            events = tapo.poll_events()
        except Exception as e:
            cam_log.warning(f"poll_events error: {e}")
            time.sleep(2)
            continue

        if not events:
            continue

        now = time.time()
        for event in events:
            if now < cooldown_until:
                continue

            cooldown_until = now + cooldown_sec
            cam_log.info(f"ONVIF event: {event.detection_type}")

            threading.Thread(
                target=handle_clip,
                args=(event, cam_cfg, capture, clip_analyzer,
                      file_store, event_store, cfg, cam_log),
                daemon=True,
                name=f"{cam_cfg.name}-clip",
            ).start()
            break

    capture.stop()
    cam_log.info("Worker stopped")


def run(config_path: str = "config.yaml"):
    cfg = load_config(config_path)
    setup_logging()

    main_log = logger.bind(cam="main")
    main_log.info(f"=== RemoteAICamera starting ({len(cfg.cameras)} camera(s)) ===")

    # API サーバーをバックグラウンドスレッドで起動
    api_thread = threading.Thread(
        target=_start_api_server,
        args=(cfg.api_server.host, cfg.api_server.port),
        daemon=True,
        name="api-server",
    )
    api_thread.start()
    main_log.info(f"API server starting: http://{cfg.api_server.host}:{cfg.api_server.port}")

    detector = YOLODetector(
        model_name=cfg.detection.yolo_model,
        confidence=cfg.detection.confidence,
        target_classes=cfg.detection.target_classes,
        device=cfg.detection.device,
        models_dir=cfg.storage.base_dir + "/models",
    )
    main_log.info("Loading YOLO model...")
    detector.load()

    file_store = FileStore(
        snapshots_dir=cfg.storage.snapshots_dir,
        clips_dir=cfg.storage.clips_dir,
        snapshot_quality=cfg.storage.snapshot_quality,
        clip_pre_seconds=cfg.storage.clip_pre_seconds,
        clip_post_seconds=cfg.storage.clip_post_seconds,
        max_storage_gb=cfg.storage.max_storage_gb,
    )
    event_store = EventStore(db_path=cfg.storage.db_path)

    stop_event = threading.Event()

    def _stop(sig, frame):
        main_log.info("Shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    threads = []
    for cam_cfg in cfg.cameras:
        t = threading.Thread(
            target=camera_worker,
            args=(cam_cfg, detector, file_store, event_store, cfg, stop_event),
            name=f"cam-{cam_cfg.name}",
            daemon=True,
        )
        t.start()
        threads.append(t)
        logger.bind(cam=cam_cfg.name).info(f"Worker started: {cam_cfg.host}")

    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()

    for t in threads:
        t.join(timeout=15)

    stats = event_store.summary()
    storage = file_store.check_storage()
    main_log.info(f"Session summary: {stats}")
    main_log.info(f"Storage: {storage}")
    main_log.info("=== RemoteAICamera stopped ===")


def main():
    parser = argparse.ArgumentParser(description="RemoteAICamera")
    parser.add_argument("--config", default="config.yaml", help="設定ファイルパス")
    args = parser.parse_args()
    run(config_path=args.config)


if __name__ == "__main__":
    main()
