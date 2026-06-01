@echo off
REM ============================================================
REM RemoteAICamera - Phase 1 セットアップスクリプト
REM 実行前に config.yaml のカメラ IP・パスワードを設定してください
REM ============================================================

echo [1/4] PyTorch (CUDA 12.6 wheels / CUDA 12.8 互換) インストール中...
.venv\Scripts\pip.exe install torch torchvision --index-url https://download.pytorch.org/whl/cu126

echo [2/4] OpenCV インストール中...
.venv\Scripts\pip.exe install opencv-python==4.10.0.84

echo [3/4] YOLOv8 インストール中...
.venv\Scripts\pip.exe install ultralytics==8.3.0

echo [4/4] 残りの依存パッケージインストール中...
.venv\Scripts\pip.exe install -r requirements.txt

echo.
echo セットアップ完了!
echo 起動: .venv\Scripts\python.exe main.py --show
echo 設定: config.yaml の camera.host / password を変更してください
pause
