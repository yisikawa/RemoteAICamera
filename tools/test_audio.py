"""
騒音レベル計測の動作確認ツール

使い方:
  .venv\Scripts\python.exe tools/test_audio.py
  .venv\Scripts\python.exe tools/test_audio.py --cam 1
  .venv\Scripts\python.exe tools/test_audio.py --alert 65   # 65dB で警告
"""
import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from camera.audio_monitor import AudioMonitor


def db_bar(db: float, min_db: float = -60, max_db: float = 0) -> str:
    """dB 値をバーグラフ文字列に変換"""
    width = 40
    ratio = max(0.0, min(1.0, (db - min_db) / (max_db - min_db)))
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"


def on_alert(level, cam_name: str, threshold: float):
    print(f"\n🔔 [{cam_name}] 騒音アラート: {level.db:.1f} dB (閾値={threshold}dB)")


def main():
    parser = argparse.ArgumentParser(description="騒音レベル計測テスト")
    parser.add_argument("--cam",   type=int, default=0,    help="カメラ番号 (default=0)")
    parser.add_argument("--alert", type=float, default=70, help="警告閾値 dB (default=70)")
    parser.add_argument("--both",  action="store_true",    help="両カメラ同時計測")
    args = parser.parse_args()

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
