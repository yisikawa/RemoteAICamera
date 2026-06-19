# RemoteAICamera スケジューラ用停止スクリプト
foreach ($port in @(8000, 5173)) {
    $pids = (netstat -ano | Select-String ":$port .*LISTENING") -replace '.*\s+(\d+)$','$1'
    foreach ($p in $pids) {
        if ($p -match '^\d+$') {
            Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue
        }
    }
}
