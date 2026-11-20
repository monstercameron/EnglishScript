@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run.ps1" %*
set "desk_status=%errorlevel%"
if "%~1"=="" pause
exit /b %desk_status%
