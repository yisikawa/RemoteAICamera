# RemoteAICamera スケジュールタスク登録スクリプト
# 管理者として実行してください

$stopAction = New-ScheduledTaskAction -Execute "D:\LLMprojects\RemoteAICamera\stop.bat"
$stopTrigger = New-ScheduledTaskTrigger -Daily -At "03:30"
$stopSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
$stopSettings.WakeToRun = $true
$stopSettings.StartWhenAvailable = $true
$stopSettings.DisallowStartIfOnBatteries = $false
$stopSettings.StopIfGoingOnBatteries = $false
Register-ScheduledTask -TaskName "RemoteAICamera_Stop" -Action $stopAction -Trigger $stopTrigger -Settings $stopSettings -RunLevel Highest -Force
Write-Host "[OK] RemoteAICamera_Stop タスク登録完了 (毎日 02:00 停止)" -ForegroundColor Green

$startAction = New-ScheduledTaskAction `
    -Execute "pwsh.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -File `"D:\LLMprojects\RemoteAICamera\start_scheduled.ps1`""
$startTrigger = New-ScheduledTaskTrigger -Daily -At "04:30"
$startSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
$startSettings.WakeToRun = $true
$startSettings.StartWhenAvailable = $true
$startSettings.DisallowStartIfOnBatteries = $false
$startSettings.StopIfGoingOnBatteries = $false
Register-ScheduledTask -TaskName "RemoteAICamera_Start" -Action $startAction -Trigger $startTrigger -Settings $startSettings -RunLevel Highest -Force
Write-Host "[OK] RemoteAICamera_Start タスク更新完了 (毎日 04:30 起動 / バックグラウンド)" -ForegroundColor Green

Write-Host ""
Write-Host "登録済みタスク確認:" -ForegroundColor Cyan
Get-ScheduledTask -TaskName "RemoteAICamera_*" | Select-Object TaskName, State
