@echo off
rem CraftLaunch Minecraft Launcher - GUI entry (no console window)
rem Prefers a Python install that has tkinter; falls back to pyw / pythonw / python.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

set "FOUND="
for %%C in (
    "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
    "C:\Python314\pythonw.exe"
    "C:\Python313\pythonw.exe"
    "C:\Python312\pythonw.exe"
) do (
    if not defined FOUND if exist "%%~C" set "FOUND=%%~C"
)
if not defined FOUND ( where pyw >nul 2>nul && set "FOUND=pyw" )
if not defined FOUND ( where pythonw >nul 2>nul && set "FOUND=pythonw.exe" )
if not defined FOUND ( where python >nul 2>nul && set "FOUND=python.exe" )
if not defined FOUND (
    echo Python not found. Please install Python 3.9 or newer from https://www.python.org/
    pause
    exit /b 1
)
start "" "%FOUND%" gui.py
