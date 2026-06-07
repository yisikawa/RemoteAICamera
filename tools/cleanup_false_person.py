"""
"person" イベントのうち、target_classes 外クラスの最高信頼度が
person (class_id=0) の最高信頼度を上回る誤検知を削除する

判定ロジック:
  max_conf(non-target classes) > max_conf(person class) → 誤検知候補

dry-run (デフォルト): 削除候補をスナップショット URL 付きで表示
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


def _max_conf(dets: list, class_set: set) -> float:
    confs = [d.get('confidence', 0) for d in dets if d.get('class_id') in class_set]
    return max(confs) if confs else 0.0


def _max_conf_non_target(dets: list) -> float:
    confs = [d.get('confidence', 0) for d in dets if d.get('class_id') not in TARGET_CLASSES]
    return max(confs) if confs else 0.0


def _top_detections(dets: list, n: int = 5) -> list[str]:
    sorted_dets = sorted(dets, key=lambda d: d.get('confidence', 0), reverse=True)
    return [f"{d.get('class_name','?')}({d.get('confidence',0):.2f})" for d in sorted_dets[:n]]


def main():
    parser = argparse.ArgumentParser(
        description='Cleanup false "person" events based on confidence comparison'
    )
    parser.add_argument('--delete', action='store_true', help='実際に削除する（省略時はdry-run）')
    parser.add_argument('--config', default='config.yaml', help='設定ファイルパス')
    args = parser.parse_args()

    cfg = load_config(args.config)
    store = EventStore(db_path=cfg.storage.db_path)

    rows, total = store.get_events_filtered(detection_type='person', limit=0)
    print(f'"person" イベント合計: {total} 件')
    print(f'判定: non-target クラス最高信頼度 > person 最高信頼度 → 誤検知候補')
    print()

    targets = []
    for row in rows:
        dets = json.loads(row.detections_json) if isinstance(row.detections_json, str) else (row.detections_json or [])
        mc_person = _max_conf(dets, {0})
        mc_other  = _max_conf_non_target(dets)
        if mc_other > mc_person:
            targets.append((row, mc_person, mc_other, dets))

    print(f'誤検知候補: {len(targets)} 件')

    if not targets:
        print('削除対象なし')
        return

    print()
    print('候補一覧（信頼度の高い検出順）:')
    for row, cp, co, dets in targets:
        top = _top_detections(dets)
        snap = ''
        if row.snapshot_path and Path(row.snapshot_path).exists():
            snap = f'/media/snapshots/{Path(row.snapshot_path).relative_to("data/snapshots").as_posix()}'
        print(f'  {row.event_id}')
        print(f'    時刻: {row.started_at}')
        print(f'    person={cp:.2f}  non-target_max={co:.2f}')
        print(f'    検出: {", ".join(top)}')
        if snap:
            print(f'    snap: {snap}')

    if args.delete:
        print(f'\n{len(targets)} 件を削除中...')
        deleted = sum(1 for row, *_ in targets if store.delete_event(row.event_id))
        print(f'削除完了: {deleted} 件')
    else:
        print()
        print('[dry-run] スナップショットを確認してから削除してください')
        print('例: python tools/cleanup_false_person.py --delete')


if __name__ == '__main__':
    main()
