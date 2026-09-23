$ErrorActionPreference = 'Stop'
Start-Transcript -Path (Join-Path $PSScriptRoot 'startup-setup.log') -Force
try {
    Start-Service iphlpsvc
    $pythonExe = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
    & $pythonExe (Join-Path $PSScriptRoot 'forward_ports.py')
    if ($LASTEXITCODE -ne 0) { throw 'Port forwarding failed.' }
    $scriptPath = Join-Path $PSScriptRoot 'start-services.ps1'
    $taskName = 'UMI Podman Services'
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        throw 'Startup task already exists; inspect it before replacing it.'
    }
    $arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $scriptPath + '"'
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
    $user = "$env:USERDOMAIN\$env:USERNAME"
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings
    Write-Output 'Port forwarding and logon startup configured.'
} finally {
    Stop-Transcript
}
