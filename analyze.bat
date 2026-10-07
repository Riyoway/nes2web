@echo off
cd /d %~dp0
if "%~1"=="" (echo Drag a .nes ROM onto this file.& pause& exit /b 1)
python -m nes2web port "%~1" -o "output\%~n1"
pause
