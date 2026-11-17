@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "" "D:\Program Files\Python\pythonw.exe" "lyric_offset_gui.py"
exit /b
