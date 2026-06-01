"""
RemoteAICamera - Phase 2 メインループ
複数の Tapo C520W からの RTSP ストリームを並列受信し、
YOLOv8 で人体・車両を検出、InsightFace で顔照合してイベントを記録する。
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
from camera.tapo_client import TapoClient
from pipeline.detector import YOLODetector
from pipeline.event_filter import EventFilter
from pipeline.face_recognizer import FaceRecognizer
from pipeline.face_matcher import FaceMatcher
from storage.file_store import FileStore, FrameRingBuffer
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


def camera_worker(
    cam_cfg: CameraConfig,
    detector: YOLODetector,         # モデルは全カメラで共有 (VRAM節約)
    face_recognizer: FaceRecognizer,
    face_matcher: FaceMatcher,
    file_store: FileStore,
    event_store: EventStore,
    cfg: AppConfig,
    stop_event: threading.Event,
    show_window: bool = False,
):
    cam_log = logger.bind(cam=cam_cfg.name)

    tapo = TapoClient(
        host=cam_cfg.host,
        username=cam_cfg.username,
        password=cam_cfg.password,
        cloud_password=cam_cfg.cloud_password,
        rtsp_password=cam_cfg.rtsp_password,
    )
    if not tapo.connect():
        cam_log.warning("Tapo API unavailable — RTSP only")

    rtsp_url = tapo.get_rtsp_url(cam_cfg.rtsp_stream)
    capture = RTSPCapture(
        rtsp_url=rtsp_url,
        buffer_seconds=max(10, int(cfg.storage.clip_pre_seconds) + 5),
        reconnect_interval=cam_cfg.reconnect_interval,
    )
    event_filter = EventFilter(min_frames=3, cooldown_sec=5.0)
    ring_buf = FrameRingBuffer(pre_seconds=cfg.storage.clip_pre_seconds + 1, fps_hint=15)

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

    import cv2
    frame_counter = 0
    post_frames: list = []
    collecting_post = False
    post_collect_end = 0.0
    active_event = None

    while not stop_event.is_set():
        frame_obj = capture.latest_frame()
        if frame_obj is None:
            time.sleep(0.05)
            continue

        img = frame_obj.data
        ts = frame_obj.timestamp
        frame_counter += 1
        ring_buf.push(img, ts)

        if frame_counter % (cfg.detection.frame_skip + 1) != 0:
            time.sleep(0.01)
            continue

        result = detector.detect(img, frame_id=frame_obj.frame_id)

        event = event_filter.process(result)
        if event:
            event.event_id = f"{cam_cfg.name}_{event.event_id}"

            # --- 顔認識 (person が含まれるイベントのみ) ---
            face_label = None
            face_sim = None
            if "person" in event.detection_type:
                face_matcher.reload_if_stale()
                face_result = face_recognizer.detect(img, frame_id=frame_obj.frame_id)
                for face in face_result.faces:
                    if face.embedding is not None:
                        match = face_matcher.match(face.embedding)
                        if match:
                            face_label = match.label
                            face_sim = match.similarity
                            break   # 最初にマッチした人物を採用

            label_str = f" → {face_label} ({face_sim:.2f})" if face_label else " → 未登録"
            cam_log.info(
                f"[EVENT] {event.event_id} | type={event.detection_type} | "
                f"frames={event.frame_count} | dur={event.duration_sec:.1f}s{label_str if 'person' in event.detection_type else ''}"
            )

            snapshot_path = file_store.save_snapshot(
                img, event_id=event.event_id, prefix=cam_cfg.name
            )
            pre_frames = ring_buf.get_pre_frames(since=event.started_at)
            collecting_post = True
            post_collect_end = time.time() + cfg.storage.clip_post_seconds
            post_frames = list(pre_frames)
            active_event = event

            event_store.save_event(event, snapshot_path=snapshot_path)
            if face_label:
                event_store.update_event_recognition(
                    event.event_id,
                    face_label=face_label,
                    face_confidence=face_sim,
                )
                event_store.update_person_seen(face_label)
            event_store.save_snapshot_record(
                file_path=snapshot_path,
                event_id=event.event_id,
                snapshot_type="event",
                width=img.shape[1],
                height=img.shape[0],
                file_size_bytes=Path(snapshot_path).stat().st_size,
            )

        if collecting_post:
            post_frames.append((img, ts))
            if time.time() >= post_collect_end:
                collecting_post = False
                clip_path = file_store.save_clip(
                    post_frames, event_id=active_event.event_id,
                    fps=capture.fps or 15,
                )
                if clip_path:
                    cam_log.info(f"Clip saved: {clip_path}")
                post_frames = []
                active_event = None

        if show_window:
            display = detector.draw(img, result)
            win_name = f"RemoteAICamera [{cam_cfg.name}]"
            cv2.imshow(win_name, cv2.resize(display, (960, 540)))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                stop_event.set()
                break

        time.sleep(0.01)

    capture.stop()
    cam_log.info("Worker stopped")


def run(config_path: str = "config.yaml", show_window: bool = False):
    cfg = load_config(config_path)
    setup_logging()
    logger.bind(cam="main").info(
        f"=== RemoteAICamera Phase 2 starting ({len(cfg.cameras)} camera(s)) ==="
    )

    # YOLOv8 / FaceRecognizer は全カメラで共有 (VRAM節約)
    detector = YOLODetector(
        model_name=cfg.detection.yolo_model,
        confidence=cfg.detection.confidence,
        target_classes=cfg.detection.target_classes,
        device=cfg.detection.device,
        models_dir=cfg.storage.base_dir + "/models",
    )
    logger.bind(cam="main").info("Loading YOLOv8 model...")
    detector.load()

    face_recognizer = FaceRecognizer(
        device=cfg.detection.device,
        models_dir=cfg.storage.base_dir + "/models",
    )
    logger.bind(cam="main").info("Loading FaceRecognizer...")
    face_recognizer.load()

    face_matcher = FaceMatcher(faces_dir=cfg.storage.faces_dir)
    face_matcher.load()

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
            args=(cam_cfg, detector, face_recognizer, face_matcher,
                  file_store, event_store, cfg, stop_event, show_window),
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

    import cv2
    if show_window:
        cv2.destroyAllWindows()

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
