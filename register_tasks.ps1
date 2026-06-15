# RemoteAICamera スケジュールタスク登録スクリプト
# 管理者として実行してください

$stopAction = New-ScheduledTaskAction -Execute "D:\LLMprojects\RemoteAICamera\stop.bat"
$stopTrigger = New-ScheduledTaskTrigger -Daily -At "02:00"
$stopSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
$stopSettings.WakeToRun = $true
Register-ScheduledTask -TaskName "RemoteAICamera_Stop" -Action $stopAction -Trigger $stopTrigger -Settings $stopSettings -RunLevel Highest -Force
Write-Host "[OK] RemoteAICamera_Stop タスク登録完了 (毎日 02:00 停止)" -ForegroundColor Green

$startAction = New-ScheduledTaskAction -Execute "D:\LLMprojects\RemoteAICamera\start.bat"
$startTrigger = New-ScheduledTaskTrigger -Daily -At "04:30"
$startSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
$startSettings.WakeToRun = $true
Register-ScheduledTask -TaskName "RemoteAICamera_Start" -Action $startAction -Trigger $startTrigger -Settings $startSettings -RunLevel Highest -Force
Write-Host "[OK] RemoteAICamera_Start タスク登録完了 (毎日 04:30 起動)" -ForegroundColor Green

Write-Host ""
Write-Host "登録済みタスク確認:" -ForegroundColor Cyan
Get-ScheduledTask -TaskName "RemoteAICamera_*" | Select-Object TaskName, State
