"""
ClipAnalyzer のテスト (test_videos の MP4 で動作確認)

使い方:
  .venv\Scripts\python.exe tools/test_clip_analyzer.py
  .venv\Scripts\python.exe tools/test_clip_analyzer.py --video data/test_videos/clip.mp4
  .venv\Scripts\python.exe tools/test_clip_analyzer.py --show  # 検出結果を表示
"""
import sys
import argparse
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from pipeline.detector import YOLODetector
from pipeline.clip_analyzer import ClipAnalyzer


def test_clip_analyzer(video_path: str, show_window: bool = False):
    """ビデオファイルから連続フレームを取得し、ClipAnalyzer でテスト"""
    cfg = load_config()

    print("Loading YOLOv8...")
    detector = YOLODetector(
        model_name=cfg.detection.yolo_model,
        confidence=cfg.detection.confidence,
        target_classes=cfg.detection.target_classes,
        device=cfg.detection.device,
        models_dir=cfg.storage.base_dir + "/models",
    )
    detector.load()

    print(f"Opening video: {video_path}")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video: {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps

    print(f"  FPS: {fps:.1f}, Total frames: {total_frames}, Duration: {duration_sec:.1f}s")

    # 15秒分のフレーム（または動画全体）を収集
    clip_duration = min(15.0, duration_sec)
    target_frames = int(clip_duration * fps)

    print(f"Collecting {target_frames} frames ({clip_duration:.1f}s)...")

    clip_analyzer = ClipAnalyzer(detector)
    frames = []
    frame_count = 0
    start_time = 0.0

    while cap.isOpened() and frame_count < target_frames:
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = frame_count / fps
        frames.append((frame, timestamp))
        frame_count += 1

        if show_window and frame_count % 10 == 0:
            print(f"  {frame_count}/{target_frames} frames collected")

    cap.release()

    if not frames:
        print("ERROR: No frames collected")
        return

    print(f"\nAnalyzing {len(frames)} frames...")
    result = clip_analyzer.analyze(
        frames,
        event_id="test_clip",
        frame_interval=5,
    )

    if not result:
        print("ERROR: Analysis failed")
        return

    print("\n" + "=" * 70)
    print(f"[RESULT] {result.event_id}")
    print(f"  Type: {result.detection_type}")
    print(f"  Best Confidence: {result.best_confidence:.2f}")
    print(f"  Best Frame Time: {result.best_frame_time:.2f}s")
    print(f"  Total Frames: {result.frame_count}")
    print(f"  Duration: {result.ended_at - result.started_at:.2f}s")
    print("=" * 70)

    if show_window:
        cv2.imshow("Best Frame", cv2.resize(result.best_frame, (960, 540)))
        print("Press any key to close window...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    # 保存
    best_frame_path = Path("data/test_clip_best_frame.jpg")
    best_frame_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(best_frame_path), result.best_frame)
    print(f"\nBest frame saved: {best_frame_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="ClipAnalyzer テスト")
    parser.add_argument(
        "--video",
        default="",
        help="テスト動画ファイルパス (未指定: data/test_videos/ の最初のMP4)",
    )
    parser.add_argument("--show", action="store_true", help="結果を画面表示")
    args = parser.parse_args()

    # 動画ファイル選択
    if args.video:
        video_path = args.video
    else:
        test_videos_dir = Path("data/test_videos")
        if not test_videos_dir.exists():
            print(f"ERROR: {test_videos_dir} not found")
            return
        mp4_files = sorted(test_videos_dir.glob("*.mp4")) + sorted(
            test_videos_dir.glob("*.MP4")
        )
        if not mp4_files:
            print(f"ERROR: No MP4 files in {test_videos_dir}")
            return
        video_path = str(mp4_files[0])

    print(f"Test video: {video_path}\n")
    test_clip_analyzer(video_path, show_window=args.show)


if __name__ == "__main__":
    main()
