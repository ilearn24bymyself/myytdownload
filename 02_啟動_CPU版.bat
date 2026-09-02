@echo off
chcp 65001 > nul
echo =========================================
echo  YouTube Whisperer - CPU Mode (Shared Env)
echo =========================================
echo.
set VENV_DIR=venv_gpu
set MODE=CPU
set FORCE_CPU=1
echo [System] Mode: %MODE% (Using shared %VENV_DIR%)
echo.

:: 檢查執行環境跟 ffmpeg/ffprobe 是否齊全，缺什麼就自動跑 bootstrap.ps1 補齊
if not exist "%VENV_DIR%\python.exe" goto :need_setup
if not exist "bin\ffmpeg.exe" goto :need_setup
if not exist "bin\ffprobe.exe" goto :need_setup
goto :setup_done

:need_setup
echo [System] 首次執行，開始自動安裝執行環境(會下載約5GB，請耐心等候，視網速可能要10-30分鐘)...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"
if not exist "%VENV_DIR%\python.exe" (
    echo.
    echo [錯誤] 自動安裝失敗，請檢查網路連線後重新執行這個檔案。
    pause
    exit /b
)

:setup_done
echo [System] Starting Streamlit with Dynamic Port...
echo.
"%VENV_DIR%\python.exe" run.py 2>> startup.log
echo.
echo [System] Server stopped.
pause
