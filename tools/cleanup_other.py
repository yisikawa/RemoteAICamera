"""
"other" イベントのうち target_classes に含まれないクラスの誤検知を削除する

target_classes: [0, 1, 2, 3, 5, 7, 14, 15, 16]
  = person, bicycle, car, motorcycle, bus, truck, bird, cat, dog

dry-run (デフォルト): 削除対象の件数・内訳を表示するだけ
--delete: 実際に削除する
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.store import EventStore
from config import load_config

TARGET_CLASSES = {0, 1, 2, 3, 5, 7, 14, 15, 16}


def is_false_positive(detections_json) -> bool:
    """target_classes のクラスが一つも含まれなければ誤検知"""
    if not detections_json:
        return True
    dets = json.loads(detections_json) if isinstance(detections_json, str) else detections_json
    return not any(d.get('class_id') in TARGET_CLASSES for d in dets)


def main():
    parser = argparse.ArgumentParser(
        description='Cleanup false "other" events (no target-class detection)'
    )
    parser.add_argument('--delete', action='store_true', help='実際に削除する（省略時はdry-run）')
    parser.add_argument('--date', help='対象日を YYYY-MM-DD で指定（省略時は全期間）')
    parser.add_argument('--config', default='config.yaml', help='設定ファイルパス')
    args = parser.parse_args()

    from datetime import datetime, timedelta
    from_dt = to_dt = None
    if args.date:
        from_dt = datetime.strptime(args.date, '%Y-%m-%d')
        to_dt   = from_dt + timedelta(days=1)
        print(f'対象日: {args.date}')

    cfg = load_config(args.config)
    store = EventStore(db_path=cfg.storage.db_path)

    rows, total = store.get_events_filtered(
        detection_type='other', from_dt=from_dt, to_dt=to_dt, limit=0
    )
    print(f'"other" イベント合計: {total} 件')

    targets = [r for r in rows if is_false_positive(r.detections_json)]
    print(f'削除対象（target_classes 外の誤検知）: {len(targets)} 件')

    if not targets:
        print('削除対象なし')
        return

    class_counts: dict[str, int] = {}
    for row in targets:
        dets = json.loads(row.detections_json) if isinstance(row.detections_json, str) else (row.detections_json or [])
        if not dets:
            class_counts['(空)'] = class_counts.get('(空)', 0) + 1
        else:
            for d in dets:
                cn = d.get('class_name', '?')
                class_counts[cn] = class_counts.get(cn, 0) + 1

    print('検出クラス内訳:')
    for k, v in sorted(class_counts.items(), key=lambda x: -x[1]):
        print(f'  {k}: {v}')

    if args.delete:
        print(f'\n{len(targets)} 件を削除中...')
        deleted = sum(1 for r in targets if store.delete_event(r.event_id))
        print(f'削除完了: {deleted} 件')
    else:
        print('\n[dry-run] --delete を付けると実際に削除します')
        print('例: python tools/cleanup_other.py --delete')


if __name__ == '__main__':
    main()
