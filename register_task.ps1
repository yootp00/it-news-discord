# 5분마다 news_bot.py 를 백그라운드(창 없음)로 실행하는 Windows 작업 스케줄러 등록
# 해제: Unregister-ScheduledTask -TaskName "IT News Discord" -Confirm:$false
$dir = $PSScriptRoot
$pythonw = "C:\Users\yootp\AppData\Local\Programs\Python\Python312\pythonw.exe"

$action   = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$dir\news_bot.py`"" -WorkingDirectory $dir
$trigger  = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "IT News Discord" -Action $action -Trigger $trigger -Settings $settings -Force
