# RemoteAICamera スケジューラ用起動スクリプト（バックグラウンド実行）
$root = "D:\LLMprojects\RemoteAICamera"

# 既存プロセス停止
foreach ($port in @(8000)) {
    $pids = (netstat -ano | Select-String ":$port .*LISTENING") -replace '.*\s+(\d+)$','$1'
    foreach ($p in $pids) { if ($p) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } }
}
Start-Sleep -Seconds 1

# Backend 起動
Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
    -ArgumentList "main.py" `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$root\logs\backend.log" `
    -RedirectStandardError "$root\logs\backend_err.log"
