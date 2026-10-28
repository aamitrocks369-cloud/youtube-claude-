@echo off
REM Windows: double-click to start Studio
cd /d "%~dp0.."
py -3 studio\app.py
pause
