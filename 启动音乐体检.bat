@echo off
chcp 65001 >nul
cd /d "%~dp0"
title MusicFree 入库前体检
"D:\Program Files\Python\python.exe" "musicfree_check.py" %*
echo.
pause
