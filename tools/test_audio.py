"""
騒音レベル計測の動作確認ツール

使い方:
  # ライブカメラ
  .venv\Scripts\python.exe tools/test_audio.py
  .venv\Scripts\python.exe tools/test_audio.py --cam 1 --alert 65

  # テスト動画ファイル
  .venv\Scripts\python.exe tools/test_audio.py --video data/test_videos/clip.mp4

  # data/test_videos/ 内を一括処理
  .venv\Scripts\python.exe tools/test_audio.py --folder data/test_videos
"""
import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from config import load_config
from camera.audio_monitor import AudioMonitor, NoiseLevel


def db_bar(db: float, min_db: float = -80, max_db: float = 0) -> str:
    """dB 値をバーグラフ文字列に変換"""
    width = 40
    ratio = max(0.0, min(1.0, (db - min_db) / (max_db - min_db)))
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"


def on_alert(level, cam_name: str, threshold: float):
    print(f"\n*** [{cam_name}] 騒音アラート: {level.db:.1f} dB (閾値={threshold}dB)")


# ------------------------------------------------------------------ #
# ファイルモード                                                         #
# ------------------------------------------------------------------ #

def analyze_file(video_path: str, alert_db: float = 70.0, window_sec: float = 0.5):
    """動画ファイルの音声トラックを解析して騒音レベルを表示する"""
    import av

    name = Path(video_path).name
    print(f"\n{'='*60}")
    print(f"音声解析: {name}")

    try:
        container = av.open(video_path)
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    audio_stream = next((s for s in container.streams if s.type == "audio"), None)
    if audio_stream is None:
        print("  音声トラックなし")
        container.close()
        return

    sample_rate = audio_stream.codec_context.sample_rate
    codec_name  = audio_stream.codec_context.name
    duration    = float(container.duration or 0) / 1_000_000
    print(f"  コーデック: {codec_name}  サンプリング: {sample_rate}Hz  "
          f"長さ: {duration:.1f}s  警告閾値: {alert_db}dB")
    print(f"  {'時刻':>7}  {'dB':>7}  バーグラフ")
    print(f"  {'-'*55}")

    samples_per_window = int(sample_rate * window_sec)
    buf   = np.array([], dtype=np.float32)
    t_sec = 0.0
    ref   = None   # 最初のウィンドウで自動判定
    levels: list[NoiseLevel] = []
    alert_count = 0

    for packet in container.demux(audio_stream):
        try:
            for frame in packet.decode():
                pcm = frame.to_ndarray().astype(np.float32).flatten()
                buf = np.concatenate([buf, pcm])
                while len(buf) >= samples_per_window:
                    window = buf[:samples_per_window]
                    buf    = buf[samples_per_window:]
                    # 初回ウィンドウで float/int を自動判定
                    if ref is None:
                        ref = 1.0 if np.max(np.abs(window)) <= 1.0 else 32768.0
                        print(f"  音声形式: {'float32 (-1〜1)' if ref == 1.0 else 'int16 (-32768〜32767)'}  基準: {ref}")
                    rms    = np.sqrt(np.mean(window ** 2))
                    db     = 20 * np.log10(rms / ref + 1e-9)
                    peak   = 20 * np.log10(np.max(np.abs(window)) / ref + 1e-9)
                    level  = NoiseLevel(timestamp=t_sec, db=round(db, 1),
                                        peak_db=round(peak, 1))
                    levels.append(level)

                    bar      = db_bar(db)
                    alert_mk = " ***" if db >= alert_db else ""
                    if alert_mk:
                        alert_count += 1
                    print(f"  {t_sec:>6.1f}s  {db:>6.1f}dB  {bar}{alert_mk}")
                    t_sec += window_sec
        except Exception:
            pass

    container.close()

    # サマリー
    if levels:
        dbs = [l.db for l in levels]
        print(f"\n  --- サマリー: {name} ---")
        print(f"  サンプル数: {len(dbs)}  平均: {np.mean(dbs):.1f}dB  "
              f"最大: {max(dbs):.1f}dB  最小: {min(dbs):.1f}dB")
        print(f"  警告超過 ({alert_db}dB以上): {alert_count} 回 "
              f"({100*alert_count//len(dbs)}%)")
    else:
        print("  音声データなし")


def main():
    parser = argparse.ArgumentParser(description="騒音レベル計測テスト")
    parser.add_argument("--cam",    type=int, default=0,    help="カメラ番号 (default=0)")
    parser.add_argument("--alert",  type=float, default=70, help="警告閾値 dBFS (default=70)")
    parser.add_argument("--both",   action="store_true",    help="両カメラ同時計測")
    parser.add_argument("--video",  default="",             help="テスト動画ファイルパス")
    parser.add_argument("--folder", default="",             help="テスト動画フォルダ (一括)")
    args = parser.parse_args()

    # ファイルモード
    if args.video:
        analyze_file(args.video, alert_db=args.alert)
        return
    if args.folder:
        folder = Path(args.folder)
        files = sorted(
            {f for f in folder.iterdir()
             if f.is_file() and f.suffix.lower() in (".mp4", ".avi", ".mkv", ".mov")},
            key=lambda f: f.name.lower()
        )
        print(f"フォルダ内動画: {len(files)} ファイル")
        for f in files:
            analyze_file(str(f), alert_db=args.alert)
        return
    if not args.video and not args.folder and not args.both:
        # 引数なし → data/test_videos があればファイルモード
        default = Path("data/test_videos")
        if default.exists() and any(default.iterdir()):
            files = sorted(
                {f for f in default.iterdir()
                 if f.is_file() and f.suffix.lower() in (".mp4", ".avi", ".mkv", ".mov")},
                key=lambda f: f.name.lower()
            )
            print(f"デフォルトフォルダを使用: {default.resolve()}  ({len(files)} ファイル)")
            for f in files:
                analyze_file(str(f), alert_db=args.alert)
            return

    cfg = load_config()
    monitors = []

    targets = cfg.cameras if args.both else [cfg.cameras[args.cam]]

    for cam_cfg in targets:
        rtsp_pw = cam_cfg.stream_password if cam_cfg.stream_password else cam_cfg.password
        url = f"rtsp://{cam_cfg.username}:{rtsp_pw}@{cam_cfg.host}:554/stream{cam_cfg.rtsp_stream}"
        m = AudioMonitor(
            rtsp_url=url,
            camera_name=cam_cfg.name,
            alert_db=args.alert,
        )
        m.start(on_alert=lambda lv, n=cam_cfg.name, t=args.alert: on_alert(lv, n, t))
        monitors.append((cam_cfg.name, m))

    print(f"騒音計測開始 (Ctrl+C で終了)  警告閾値: {args.alert} dB")
    print(f"{'カメラ':<15} {'現在dB':>8}  バーグラフ (-60dB 〜 0dBFS)")
    print("-" * 70)

    try:
        while True:
            time.sleep(0.5)
            lines = []
            for name, m in monitors:
                db = m.current_db
                avg = m.average_db(last_sec=5)
                bar = db_bar(db)
                alert_mark = " ⚠" if db >= args.alert else ""
                lines.append(
                    f"{name:<15} {db:>6.1f}dB  {bar}  avg5s={avg:.1f}dB{alert_mark}"
                )
            # カーソルを上に戻して上書き
            print("\033[{}A".format(len(lines)), end="")
            for line in lines:
                print(f"\033[K{line}")
    except KeyboardInterrupt:
        pass
    finally:
        for _, m in monitors:
            m.stop()
        print("\n計測終了")
        for name, m in monitors:
            recent = m.latest(20)
            if recent:
                dbs = [n.db for n in recent]
                print(f"  {name}: 直近 {len(recent)} サンプル  "
                      f"平均={sum(dbs)/len(dbs):.1f}dB  "
                      f"最大={max(dbs):.1f}dB  最小={min(dbs):.1f}dB")


if __name__ == "__main__":
    main()
