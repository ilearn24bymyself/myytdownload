@echo off
chcp 65001 > nul
echo =========================================
echo  YouTube Whisperer - 更新 yt-dlp
echo =========================================
echo.
set VENV_DIR=venv_gpu

if not exist "%VENV_DIR%\python.exe" (
    echo [System] 找不到執行環境，先執行 01/02 啟動檔完成首次安裝，再回來更新 yt-dlp。
    pause
    exit /b
)

echo [System] 目前版本：
"%VENV_DIR%\python.exe" -m pip show yt-dlp | findstr /B "Version"
echo.
echo [System] 正在更新 yt-dlp 至最新版...
echo.
"%VENV_DIR%\python.exe" -m pip install --upgrade yt-dlp

echo.
echo [System] 更新後版本：
"%VENV_DIR%\python.exe" -m pip show yt-dlp | findstr /B "Version"
echo.
echo [System] 完成。若下載仍失敗，可能是其他原因，請回報錯誤訊息。
pause
