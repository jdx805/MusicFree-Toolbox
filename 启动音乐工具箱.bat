@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 音乐工具箱
start "" "D:\Program Files\Python\pythonw.exe" "music_toolbox.py"
exit /b
