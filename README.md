# RemoteAICamera

TP-Link Tapo C520W カメラ + ローカル AI (LM Studio) を使った、プライベート監視・人物/車両認識・記録システム。

クラウド不使用・完全ローカル動作を優先設計。

---

## 機能概要

| フェーズ | 機能 | 状態 |
|---|---|---|
| Phase 1 | RTSP受信・YOLOv8人体/車両検出・静止画/動画保存・SQLite記録 | ✅ 完了 |
| Phase 2 | 顔認識 (InsightFace)・ナンバープレート認識 (EasyOCR) | 🔲 予定 |
| Phase 3 | LM Studio連携 (初見人物描写・自然言語クエリ) | 🔲 予定 |
| Phase 4 | Web ダッシュボード (FastAPI + React) | 🔲 予定 |

---

## システム構成

```
Tapo C520W (RTSP)
       │
       ▼
RTSPCapture  ─────────────────────────────────────────┐
(別スレッド・自動再接続)                               │
       │                                               │
       ▼                                        FrameRingBuffer
YOLOv8 (GPU推論)                             (イベント前フレーム保持)
       │
       ▼
EventFilter (デバウンス)
       │ イベント確定
       ├──▶ FileStore ──▶ data/snapshots/ (JPEG)
       │               ──▶ data/clips/    (MP4)
       └──▶ EventStore ──▶ data/events.db (SQLite)
```

複数カメラは各自スレッドで並列処理。YOLOv8モデルは全カメラで共有 (VRAM節約)。

---

## 動作環境

| 項目 | 要件 |
|---|---|
| OS | Windows 11 |
| Python | 3.11 以上 |
| GPU | NVIDIA RTX シリーズ (CUDA 12.x) |
| カメラ | TP-Link Tapo C520W (RTSP対応モデル) |
| AI推論 | LM Studio (Phase 3以降) |

開発・検証環境: RTX 4060 16GB / CUDA 12.8 / PyTorch cu126

---

## セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/yisikawa/RemoteAICamera.git
cd RemoteAICamera
```

### 2. 仮想環境の作成

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. 依存パッケージのインストール

`setup.bat` を実行します (PyTorch CUDA + 全パッケージを一括インストール)。

```bat
setup.bat
```

手動で行う場合:

```bash
# PyTorch (CUDA 12.6 ホイール / CUDA 12.8 互換)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

# その他パッケージ
pip install -r requirements.txt
```

### 4. 設定ファイルの作成

```bash
copy config.yaml.example config.yaml
```

`config.yaml` を編集してカメラ情報を入力します。

```yaml
cameras:
  - name: "frontCamera"
    host: "192.168.1.100"           # カメラの IP アドレス
    username: "admin"               # カメラのユーザー名
    password: "your_password"       # ローカル管理パスワード
    stream_password: ""             # RTSP用パスワード (空なら password を流用)
    cloud_password: ""              # Tapo クラウドPW (KLAP認証が必要な場合)
    rtsp_stream: 1
```

> **カメラIPの確認方法**
> ```bash
> python discover.py --password YOUR_PASSWORD
> ```

### 5. 起動

```bash
# 通常起動
python main.py

# 検出ウィンドウを表示しながら起動
python main.py --show
```

---

## ディレクトリ構成

```
RemoteAICamera/
├── camera/
│   ├── tapo_client.py      # Tapo API 接続・イベント取得
│   └── rtsp_capture.py     # RTSP受信・自動再接続・フレームバッファ
├── pipeline/
│   ├── detector.py         # YOLOv8 GPU推論ラッパー
│   └── event_filter.py     # 連続検出をデバウンスしてイベント化
├── db/
│   ├── models.py           # SQLite ORM モデル定義
│   └── store.py            # DB操作ファサード
├── storage/
│   └── file_store.py       # 静止画・動画クリップ保存 + リングバッファ
├── data/                   # (gitignore) 実行時に自動生成
│   ├── snapshots/          # 静止画 (日付フォルダ別)
│   ├── clips/              # 動画クリップ (日付フォルダ別)
│   ├── models/             # YOLOv8 ウェイトキャッシュ
│   ├── faces/              # 顔エンコーディング (Phase 2)
│   └── events.db           # SQLite データベース
├── main.py                 # エントリーポイント
├── config.py               # 設定ファイルローダー
├── discover.py             # カメラ IP 自動検出ツール
├── config.yaml             # (gitignore) 実際の設定 (パスワード含む)
├── config.yaml.example     # 設定テンプレート
├── requirements.txt        # 依存パッケージ一覧
└── setup.bat               # Windows セットアップスクリプト
```

---

## カメラの追加

`config.yaml` に `cameras:` ブロックを追加するだけで、自動的に並列スレッドで処理されます。

```yaml
cameras:
  - name: "eastCamera"
    host: "192.168.1.100"
    ...
  - name: "southCamera"
    host: "192.168.1.101"
    ...
```

---

## Tapo 認証について

Tapo C520W はファームウェアバージョンによって認証方式が異なります。

| 認証方式 | config.yaml の設定 |
|---|---|
| ローカル管理 (旧) | `password` のみ設定 |
| KLAP 認証 (新) | `password` + `cloud_password` を設定 |
| RTSP パスワード別 | `stream_password` を設定 |

pytapo API 接続に失敗しても RTSP ストリームは独立して動作します。

---

## VRAM 使用量の目安 (RTX 4060 16GB)

| モデル | 使用量 |
|---|---|
| YOLOv8s (常駐) | ~0.5 GB |
| InsightFace buffalo_l (Phase 2) | ~1.0 GB |
| EasyOCR (Phase 2) | ~1.5 GB |
| Qwen2-VL 7B Q4 via LM Studio (Phase 3) | ~6.0 GB |
| **合計 (最大)** | **~9.0 GB** |

---

## ロードマップ

### Phase 2: 顔認識・ナンバープレート認識
- InsightFace による顔エンコーディング登録・照合
- EasyOCR / PaddleOCR による日本語ナンバープレート認識
- 車両色・車種分類
- 既知人物・既知車両の通過ログ蓄積

### Phase 3: LM Studio ローカル AI 連携
- Qwen2-VL による初見人物・初見車両の状況説明生成
- 自然言語クエリ対応 (「昨日Aさんは何時に来た？」)
- 日次イベントレポート自動生成

### Phase 4: Web ダッシュボード
- FastAPI + React によるリアルタイムタイムライン表示
- 顔・ナンバープレート登録管理 UI
- LM Studio チャット UI

---

## 注意事項

- 本システムで取得する映像・顔情報・車両情報は**個人情報保護法**の対象となる場合があります
- **私有地内・私的利用**の範囲で使用してください
- pytapo は非公式ライブラリのため、カメラのファームウェア更新で動作が変わる可能性があります

---

## ライセンス

MIT License
