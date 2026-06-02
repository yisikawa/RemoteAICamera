"""
RemoteAICamera - ONVIF イベント駆動型
Tapo C520W の ONVIF イベント (人物・車両検知) をトリガーに
15秒クリップを RTSP から抽出・分析してイベント記録する。
"""
import sys
import time
import signal
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


def setup_logging(level: str = "INFO", log_file: str = "data/app.log"):
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    # cam が bind されていないモジュール (detector 等) でも動くようにデフォルト値を設定
    logger.configure(extra={"cam": "-"})
    logger.remove()
    logger.add(sys.stderr, level=level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | <cyan>{extra[cam]}</cyan> | {message}")
    logger.add(log_file, level=level, rotation="10 MB", retention=5,
               format="{time:YYYY-MM-DD HH:mm:ss} | {level:8} | {extra[cam]} | {message}")


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
    """
    ONVIF イベント検知後、15秒クリップを収集・分析・保存する。
    (バックグラウンドスレッドで実行)
    """
    try:
        event_id = f"{cam_cfg.name}_{trigger_event.timestamp:.0f}"

        # ポストロール待機
        time.sleep(cfg.storage.clip_post_seconds)

        # フレーム収集 (15秒分)
        frames = capture.get_recent_frames(cfg.storage.clip_duration_sec)
        if not frames or len(frames) < 5:
            cam_log.warning(f"[{event_id}] Not enough frames: {len(frames) if frames else 0}")
            return

        # Frame オブジェクト → (ndarray, timestamp) タプルに変換
        frames_as_list = [(f.data, f.timestamp) for f in frames]

        # 分析 (every 5th frame に YOLO推論)
        result = clip_analyzer.analyze(frames_as_list, event_id=event_id, frame_interval=5)
        if not result:
            cam_log.warning(f"[{event_id}] Analysis failed")
            return

        # スナップショット保存
        snapshot_path = file_store.save_snapshot(
            result.best_frame, event_id=event_id, prefix=cam_cfg.name
        )

        # クリップ保存
        clip_path = file_store.save_clip(
            frames_as_list, event_id=event_id, fps=capture.fps or 15
        )

        # DB 記録
        event_store.save_event(
            event_id=event_id,
            started_at=result.started_at,
            ended_at=result.ended_at,
            detection_type=result.detection_type,
            frame_count=result.frame_count,
            snapshot_path=snapshot_path,
            clip_path=clip_path,
        )
        event_store.save_snapshot_record(
            file_path=snapshot_path,
            event_id=event_id,
            snapshot_type="event",
            width=result.best_frame.shape[1],
            height=result.best_frame.shape[0],
            file_size_bytes=Path(snapshot_path).stat().st_size if snapshot_path else 0,
        )

        cam_log.info(
            f"[EVENT] {event_id} | type={result.detection_type} | "
            f"confidence={result.best_confidence:.2f} | frames={result.frame_count} | "
            f"snapshot={Path(snapshot_path).name if snapshot_path else '?'} | "
            f"clip={Path(clip_path).name if clip_path else '?'}"
        )

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

    # ONVIF 接続 (イベント取得用)
    tapo = TapoClient(
        host=cam_cfg.host,
        api_username=cam_cfg.api_username,
        api_password=cam_cfg.api_password,
        onvif_port=cam_cfg.onvif_port,
    )
    if not tapo.connect():
        cam_log.warning("Tapo API unavailable — cannot poll ONVIF events")
        return

    # RTSP キャプチャ開始 (フレームバッファ保持)
    rtsp_url = f"rtsp://{cam_cfg.stream_username}:{cam_cfg.stream_password}@{cam_cfg.host}:554/stream{cam_cfg.rtsp_stream}"
    capture = RTSPCapture(
        rtsp_url=rtsp_url,
        buffer_seconds=max(20, int(cfg.storage.clip_duration_sec) + 5),
        reconnect_interval=cam_cfg.reconnect_interval,
    )
    capture.start()

    cam_log.info(f"Waiting for stream: {rtsp_url}")
    for _ in range(50):
        if capture.latest_frame():
            break
        time.sleep(0.2)
    else:
        cam_log.error("Cannot receive frames. Check IP / password.")
        capture.stop()
        return

    cam_log.info(f"Stream connected. FPS={capture.fps:.1f}")

    # ClipAnalyzer (YOLO推論用)
    clip_analyzer = ClipAnalyzer(detector)

    # ONVIF ポーリング ループ
    last_poll = 0.0
    cooldown_until = 0.0
    collecting = threading.Event()

    while not stop_event.is_set():
        now = time.time()

        # ONVIF イベント 2秒ポーリング
        if now - last_poll >= cam_cfg.motion_poll_interval:
            last_poll = now
            if not collecting.is_set() and now >= cooldown_until:
                try:
                    events = tapo.poll_events()
                    if events:
                        trigger = events[0]
                        collecting.set()
                        cooldown_until = now + cfg.storage.clip_duration_sec + 5
                        cam_log.debug(f"ONVIF event: {trigger.detection_type}")

                        # バックグラウンドスレッドで clip 処理開始
                        t = threading.Thread(
                            target=handle_clip,
                            args=(trigger, cam_cfg, capture, clip_analyzer,
                                  file_store, event_store, cfg, cam_log),
                            daemon=True,
                            name=f"{cam_cfg.name}-clip",
                        )
                        t.start()
                except Exception as e:
                    cam_log.warning(f"poll_events error: {e}")

        # collecting 状態の確認 (handle_clip 完了待ち)
        if collecting.is_set() and now >= cooldown_until:
            collecting.clear()

        time.sleep(0.1)

    capture.stop()
    cam_log.info("Worker stopped")


def run(config_path: str = "config.yaml", show_window: bool = False):
    cfg = load_config(config_path)
    setup_logging()
    logger.bind(cam="main").info(
        f"=== RemoteAICamera (ONVIF-driven) starting ({len(cfg.cameras)} camera(s)) ==="
    )

    # YOLOv8 は全カメラで共有 (VRAM節約)
    detector = YOLODetector(
        model_name=cfg.detection.yolo_model,
        confidence=cfg.detection.confidence,
        target_classes=cfg.detection.target_classes,
        device=cfg.detection.device,
        models_dir=cfg.storage.base_dir + "/models",
    )
    logger.bind(cam="main").info("Loading YOLOv8 model...")
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
        logger.bind(cam="main").info("Shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    # 各カメラを別スレッドで起動
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
        logger.bind(cam=cam_cfg.name).info(f"Worker thread started: {cam_cfg.host}")

    # メインスレッドは停止を待つだけ
    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()

    for t in threads:
        t.join(timeout=15)

    stats = event_store.summary()
    storage = file_store.check_storage()
    logger.bind(cam="main").info(f"Session summary: {stats}")
    logger.bind(cam="main").info(f"Storage: {storage}")
    logger.bind(cam="main").info("=== RemoteAICamera stopped ===")


def main():
    parser = argparse.ArgumentParser(description="RemoteAICamera Phase 1")
    parser.add_argument("--config", default="config.yaml", help="設定ファイルパス")
    parser.add_argument("--show", action="store_true", help="検出ウィンドウを表示")
    args = parser.parse_args()
    run(config_path=args.config, show_window=args.show)


if __name__ == "__main__":
    main()
