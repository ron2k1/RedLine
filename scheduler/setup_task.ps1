$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Find Python
$VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $PythonExe) {
        Write-Error "Python not found. Install Python or create a venv."
        exit 1
    }
}

# Ensure logs dir
$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Create scheduled task
$BatFile = Join-Path $ProjectRoot "scheduler\run_pipeline.bat"
$Action = New-ScheduledTaskAction -Execute $BatFile -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At "06:00"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "Redline Pipeline" -Action $Action -Trigger $Trigger -Settings $Settings -Force

Write-Host "Scheduled task 'Redline Pipeline' created successfully."
Write-Host "Python: $PythonExe"
Write-Host "Batch:  $BatFile"
Write-Host "Logs:   $LogDir"
