# Setup Weekly Backup Task
# Run this script as Administrator

$ErrorActionPreference = "Stop"

Write-Host "Setting up Weekly Data Backup Task..." -ForegroundColor Cyan

# Define task parameters
$taskName = "WeeklyDataBackup"
$scriptPath = "C:\Users\admin\Server\FlaskApp\scripts\backup_weekly_data.py"
$workingDir = "C:\Users\admin\Server\FlaskApp\scripts"

# Create action
$action = New-ScheduledTaskAction `
    -Execute "python" `
    -Argument $scriptPath `
    -WorkingDirectory $workingDir

# Create trigger (every Sunday at 00:00)
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Sunday `
    -At "00:00"

# Create principal (run as current user)
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Highest

# Create settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# Register task
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Weekly backup of GeneralReviews, DatasetScr, and DatasetScrBooking files every Sunday at 00:00" `
        -Force | Out-Null
    
    Write-Host "SUCCESS: Task '$taskName' created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Schedule: Every Sunday at 00:00" -ForegroundColor Yellow
    Write-Host "Script: $scriptPath" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To verify the task, run: Get-ScheduledTask -TaskName '$taskName'" -ForegroundColor Cyan
    Write-Host "To test the backup now, run: python '$scriptPath'" -ForegroundColor Cyan
}
catch {
    Write-Host "ERROR: Failed to create scheduled task" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
