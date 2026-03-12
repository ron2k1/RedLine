@echo off
setlocal

:: Project root is parent of this script's directory
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

:: Find Python: prefer venv
set "PYTHON=%PROJECT_ROOT%\venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    set "PYTHON=python"
)

:: Ensure logs directory
if not exist "%PROJECT_ROOT%\logs" mkdir "%PROJECT_ROOT%\logs"

:: ISO date for log filename (locale-independent)
for /f "tokens=*" %%d in ('powershell -Command "Get-Date -Format ''yyyy-MM-dd''"') do set "TODAY=%%d"

:: Run pipeline with logging
cd /d "%PROJECT_ROOT%"
"%PYTHON%" -m redline.pipeline >> "%PROJECT_ROOT%\logs\pipeline_%TODAY%.log" 2>&1
