"""
eastCamera の started_at / ended_at / duration_sec を
event_id に埋め込まれた正確なタイムスタンプで上書き修正する。

PTSベースのタイムスタンプ計算に起因するずれ（今回は +26460秒）を解消する。

修正式:
  T           = event_id 中の Unix タイムスタンプ（ONVIF受信時刻）
  started_at  = T - clip_pre_seconds   (= T - 3)
  ended_at    = T + clip_post_seconds  (= T + 12)
  duration    = clip_post_seconds + clip_pre_seconds  (= 15.0)

dry-run (デフォルト): 修正前後を表示するだけ
--apply: 実際に DB を更新する
"""
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.store import EventStore
from db.models import DetectionEventRecord
from config import load_config

CLIP_PRE_SEC  = 3.0
CLIP_POST_SEC = 12.0


def extract_event_ts(event_id: str) -> float | None:
    """event_id から Unix タイムスタンプを取得する。"""
    m = re.search(r'_(\d{10})_', event_id)
    return float(m.group(1)) if m else None


def main():
    parser = argparse.ArgumentParser(description="eastCamera タイムスタンプ修正ツール")
    parser.add_argument("--apply", action="store_true", help="実際に DB を更新する（省略時は dry-run）")
    args = parser.parse_args()

    cfg = load_config()
    store = EventStore(cfg.storage.db_path)

    with store._session() as s:
        records = (
            s.query(DetectionEventRecord)
            .filter(DetectionEventRecord.event_id.like("eastCamera_%"))
            .order_by(DetectionEventRecord.started_at)
            .all()
        )

        print(f"対象レコード: {len(records)} 件\n")
        print(f"{'event_id':<52} {'修正前 started_at':<22} {'修正後 started_at':<22} {'ずれ(秒)':>8}")
        print("-" * 110)

        updated = 0
        skipped = 0
        for r in records:
            T = extract_event_ts(r.event_id)
            if T is None:
                print(f"{r.event_id:<52} (event_id から時刻を取得できません)")
                continue

            new_started = datetime.fromtimestamp(T - CLIP_PRE_SEC)
            new_ended   = datetime.fromtimestamp(T + CLIP_POST_SEC)
            new_dur     = CLIP_POST_SEC + CLIP_PRE_SEC

            old_ts = r.started_at.timestamp() if r.started_at else 0
            diff   = old_ts - (T - CLIP_PRE_SEC)

            # すでに正確なレコード（60秒以内）はスキップ
            if abs(diff) <= 60:
                skipped += 1
                continue

            old_str = r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else "None"
            new_str = new_started.strftime("%Y-%m-%d %H:%M:%S")

            print(f"{r.event_id:<52} {old_str:<22} {new_str:<22} {diff:>+8.1f}")

            if args.apply:
                r.started_at   = new_started
                r.ended_at     = new_ended
                r.duration_sec = new_dur
                updated += 1

        if args.apply:
            print(f"\n{updated} 件を更新しました。（正確なレコード {skipped} 件はスキップ）")
        else:
            print(f"\n正確なレコード {skipped} 件はスキップ対象")
            print(f"--- dry-run: DB は変更していません。--apply を付けて実行すると更新されます ---")


if __name__ == "__main__":
    main()
