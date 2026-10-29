@echo off
rem CraftLaunch Minecraft Java Launcher - Windows entry
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python launcher.py %*
echo.
echo Done. Press any key to close...
pause >nul
