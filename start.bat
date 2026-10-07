@echo off
cd /d %~dp0
if "%~1"=="" (
  echo Drag a .nes ROM onto start.bat
  echo or: start.bat game.nes
  pause
  exit /b 1
)
set "ROM=%~1"
set "NAME=%~n1"
python -m nes2web port "%ROM%" -o "output\%NAME%"
if errorlevel 1 (
  pause
  exit /b 1
)
call "output\%NAME%\web\start.bat"
