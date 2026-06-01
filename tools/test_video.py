"""
録画済み動画ファイルで顔認識・ナンバープレート認識をテストする

Tapo の SD カード動画 (MP4) をダウンロードして指定するだけで動作します。

使い方:
  # 動画ファイルを指定
  .venv\Scripts\python.exe tools/test_video.py --video data/test_videos/clip.mp4

  # data/test_videos/ 内の全動画を一括処理 (引数省略で自動使用)
  .venv\Scripts\python.exe tools/test_video.py

  # 処理結果の動画も保存する
  .venv\Scripts\python.exe tools/test_video.py --video clip.mp4 --save

  # 再生速度を遅くして確認 (デフォルト等倍)
  .venv\Scripts\python.exe tools/test_video.py --video clip.mp4 --speed 0.3
"""
import sys
import argparse
import time
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np

from config import load_config
from pipeline.detector import YOLODetector
from pipeline.face_recognizer import FaceRecognizer
from pipeline.face_matcher import FaceMatcher
from pipeline.plate_recognizer import PlateRecognizer
from pipeline.vehicle_analyzer import VehicleAnalyzer

VEHICLE_CLASSES = {1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


@dataclass
class VideoSummary:
    video_path: str
    total_frames: int = 0
    processed_frames: int = 0
    person_events: int = 0
    vehicle_events: int = 0
    face_matches: dict = field(default_factory=dict)    # label -> count
    plate_matches: dict = field(default_factory=dict)   # plate -> count
    vehicle_colors: dict = field(default_factory=dict)  # "色 車種" -> count
    elapsed_sec: float = 0.0


def process_video(
    video_path: str,
    detector: YOLODetector,
    face_recognizer: FaceRecognizer,
    face_matcher: FaceMatcher,
    plate_recognizer: PlateRecognizer,
    vehicle_analyzer: VehicleAnalyzer,
    save_output: bool = False,
    speed: float = 1.0,
) -> VideoSummary:

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"ERROR: 動画を開けません: {video_path}")
        return VideoSummary(video_path)

    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    wait_ms = max(1, int(1000 / fps / speed))

    print(f"\n{'='*60}")
    print(f"動画: {Path(video_path).name}")
    print(f"解像度: {w}x{h}  FPS: {fps:.1f}  フレーム数: {total}")
    print(f"再生速度: x{speed}  (q で次の動画へ / s でスナップ保存)")
    print(f"{'='*60}")

    # 出力動画ライター
    writer = None
    out_path = ""
    if save_output:
        out_path = str(Path("data/snapshots") / f"analyzed_{Path(video_path).stem}.mp4")
        Path("data/snapshots").mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h)
        )

    summary = VideoSummary(video_path=video_path)
    t_start = time.time()
    frame_count = 0
    skip = 3   # N フレームおきに推論
    last_det = None
    last_face = None
    last_plate = None
    prev_had_person = False
    prev_had_vehicle = False

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        summary.total_frames += 1

        if frame_count % skip != 0:
            display = _overlay(frame, last_det, last_face, last_plate, face_matcher)
            cv2.imshow(f"Video Test: {Path(video_path).name}", cv2.resize(display, (960, 540)))
            if writer:
                writer.write(display)
            key = cv2.waitKey(wait_ms) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s"):
                snap = f"data/snapshots/snap_{Path(video_path).stem}_{frame_count:05d}.jpg"
                cv2.imwrite(snap, frame)
                print(f"  スナップ保存: {snap}")
            continue

        summary.processed_frames += 1

        # YOLO 検出
        last_det = detector.detect(frame, frame_id=frame_count)
        has_person = last_det.persons != []
        has_vehicle = last_det.vehicles != []

        # イベントカウント (検出開始時のみカウント)
        if has_person and not prev_had_person:
            summary.person_events += 1
        if has_vehicle and not prev_had_vehicle:
            summary.vehicle_events += 1
        prev_had_person = has_person
        prev_had_vehicle = has_vehicle

        # 顔認識
        if has_person:
            last_face = face_recognizer.detect(frame, frame_id=frame_count)
            for face in last_face.faces:
                if face.embedding is not None:
                    match = face_matcher.match(face.embedding)
                    if match:
                        summary.face_matches[match.label] = (
                            summary.face_matches.get(match.label, 0) + 1
                        )
                        print(f"  [{frame_count:5d}] 顔一致: {match.label} "
                              f"(類似度={match.similarity:.2f})")

        # 車両色・車種分析
        last_vehicle_analyses = []
        if has_vehicle:
            for d in last_det.vehicles:
                vtype = VEHICLE_CLASSES.get(d.class_id, "car")
                ana = vehicle_analyzer.analyze(frame, d.bbox, vtype)
                last_vehicle_analyses.append(ana)
                key = f"{ana.color_name} {ana.vehicle_type_jp}"
                summary.vehicle_colors[key] = summary.vehicle_colors.get(key, 0) + 1

            # 車両色サマリーを数フレームおきに表示 (毎フレームは冗長なので5回に1回)
            if frame_count % 15 == 0 and last_vehicle_analyses:
                color_summary = ", ".join(
                    f"{a.color_name}{a.vehicle_type_jp}" for a in last_vehicle_analyses
                )
                print(f"  [{frame_count:5d}] 車両: {color_summary}")

        # ナンバープレート認識
        if has_vehicle:
            vehicle_bboxes = [
                (*d.bbox, VEHICLE_CLASSES.get(d.class_id, "car"))
                for d in last_det.vehicles
            ]
            last_plate = plate_recognizer.detect_from_vehicle_crops(
                frame, vehicle_bboxes, frame_id=frame_count
            )
            for p in last_plate.plates:
                if p.normalized:
                    summary.plate_matches[p.normalized] = (
                        summary.plate_matches.get(p.normalized, 0) + 1
                    )
                    print(f"  [{frame_count:5d}] プレート: {p.normalized} "
                          f"(信頼度={p.confidence:.2f}  {p.vehicle_class})")
                elif p.raw_text.strip():
                    print(f"  [{frame_count:5d}] OCR生: '{p.raw_text[:40]}' "
                          f"(conf={p.confidence:.2f})")

        display = _overlay(frame, last_det, last_face, last_plate, face_matcher,
                           last_vehicle_analyses)

        # フレーム番号・進捗表示
        progress = f"{frame_count}/{total} ({100*frame_count//total if total else 0}%)"
        cv2.putText(display, progress, (8, display.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        cv2.imshow(f"Video Test: {Path(video_path).name}", cv2.resize(display, (960, 540)))
        if writer:
            writer.write(display)

        key = cv2.waitKey(wait_ms) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            snap = f"data/snapshots/snap_{Path(video_path).stem}_{frame_count:05d}.jpg"
            cv2.imwrite(snap, frame)
            print(f"  スナップ保存: {snap}")

    cap.release()
    if writer:
        writer.release()
        print(f"出力動画保存: {out_path}")

    summary.elapsed_sec = time.time() - t_start
    _print_summary(summary)
    return summary


def _overlay(frame, det, face_result, plate_result, face_matcher,
             vehicle_analyses=None):
    """検出結果をフレームに重ねて返す"""
    import cv2
    out = frame.copy()
    # 車両色ラベル (vehicle_analyses と det の順序を合わせて描画)
    if vehicle_analyses and det:
        vehicles = [d for d in det.detections if not d.is_person]
        for d, ana in zip(vehicles, vehicle_analyses):
            x1, y1, x2, y2 = d.bbox
            cv2.rectangle(out, (x1, y1), (x2, y2), (0, 165, 255), 2)
            cv2.putText(out, f"{ana.color_name} {ana.vehicle_type_jp}",
                        (x1, y2 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
    if det:
        # 人物ボックス描画
        for d in det.detections:
            if not d.is_person:
                continue
            x1, y1, x2, y2 = d.bbox
            cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(out, f"person {d.confidence:.2f}",
                        (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    if face_result:
        for face in face_result.faces:
            x1, y1, x2, y2 = face.bbox
            match = face_matcher.match(face.embedding) if face.embedding is not None else None
            label = match.label if match else "未登録"
            color = (0, 200, 0) if match else (80, 80, 255)
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            cv2.putText(out, label, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    if plate_result and plate_result.best:
        p = plate_result.best
        x1, y1, x2, y2 = p.bbox
        cv2.putText(out, p.normalized, (x1, y2 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
    return out


def _print_summary(s: VideoSummary):
    print(f"\n--- 解析結果: {Path(s.video_path).name} ---")
    print(f"  フレーム: {s.processed_frames}/{s.total_frames}  処理時間: {s.elapsed_sec:.1f}s")
    print(f"  人物イベント: {s.person_events} 回  車両イベント: {s.vehicle_events} 回")
    if s.face_matches:
        print("  顔一致:")
        for label, cnt in sorted(s.face_matches.items(), key=lambda x: -x[1]):
            print(f"    {label}: {cnt} フレームで検出")
    if s.vehicle_colors:
        print("  検出車両 (色・車種):")
        for key, cnt in sorted(s.vehicle_colors.items(), key=lambda x: -x[1]):
            print(f"    {key}: {cnt} フレームで検出")
    if s.plate_matches:
        print("  ナンバープレート:")
        for plate, cnt in sorted(s.plate_matches.items(), key=lambda x: -x[1]):
            print(f"    {plate}: {cnt} フレームで検出")
    if not s.face_matches and not s.vehicle_colors and not s.plate_matches:
        print("  検出なし")


def main():
    parser = argparse.ArgumentParser(description="録画動画で顔・ナンバープレート認識テスト")
    parser.add_argument("--video", default="", help="動画ファイルパス (.mp4 等)")
    parser.add_argument("--folder", default="", help="動画フォルダパス (一括処理)")
    parser.add_argument("--save", action="store_true", help="解析済み動画を保存")
    parser.add_argument("--speed", type=float, default=1.0, help="再生速度倍率 (0.3 で1/3速)")
    args = parser.parse_args()

    # 引数省略時は data/test_videos/ をデフォルトフォルダとして使用
    if not args.video and not args.folder:
        default_folder = Path("data/test_videos")
        if default_folder.exists() and any(default_folder.iterdir()):
            args.folder = str(default_folder)
            print(f"デフォルトフォルダを使用: {default_folder.resolve()}")
        else:
            parser.error(
                "--video か --folder を指定してください\n"
                "  または data/test_videos/ に動画ファイルを置いて引数なしで実行"
            )

    cfg = load_config()

    print("モデルロード中...")
    detector = YOLODetector(
        model_name=cfg.detection.yolo_model,
        confidence=cfg.detection.confidence,
        target_classes=list({0, 2, 3, 5, 7}),
        device=cfg.detection.device,
        models_dir=cfg.storage.base_dir + "/models",
    )
    detector.load()

    face_recognizer = FaceRecognizer(
        device=cfg.detection.device,
        models_dir=cfg.storage.base_dir + "/models",
    )
    face_recognizer.load()

    face_matcher = FaceMatcher(faces_dir=cfg.storage.faces_dir)
    face_matcher.load()

    plate_recognizer = PlateRecognizer(device=cfg.detection.device)
    plate_recognizer.load()

    vehicle_analyzer = VehicleAnalyzer()
    print("ロード完了\n")

    # 処理対象ファイルの収集
    videos = []
    if args.video:
        videos = [args.video]
    elif args.folder:
        folder = Path(args.folder)
        videos = sorted(
            {f for f in folder.iterdir()
             if f.is_file() and f.suffix.lower() in (".mp4", ".avi", ".mkv", ".mov")},
            key=lambda f: f.name.lower()
        )
        print(f"フォルダ内動画: {len(videos)} ファイル")

    for v in videos:
        process_video(
            str(v), detector, face_recognizer, face_matcher,
            plate_recognizer, vehicle_analyzer,
            save_output=args.save, speed=args.speed,
        )

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
