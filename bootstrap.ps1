# 3-4.Yt-down-sub 首次執行自動安裝
# 由 01/02/03 這幾支 .bat 在偵測到缺少 venv_gpu 或 bin\ffmpeg.exe/ffprobe.exe 時自動呼叫，
# 不需要使用者事先裝任何東西(只依賴 Windows 10/11 內建的 PowerShell)。
# 每個步驟都只在「真的缺少」時才動作，已經裝好的部分直接跳過，
# 所以每次啟動都呼叫這支腳本做檢查是安全、快速的。

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest 內建進度條在大檔案上會拖慢下載速度，關掉
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venvDir = Join-Path $root "venv_gpu"
$pythonExe = Join-Path $venvDir "python.exe"

# ── 1. Portable Python + 套件 ──────────────────────────────────
if (-not (Test-Path $pythonExe)) {
    Write-Host "[Setup] 找不到執行環境，開始安裝 portable Python（約30MB）..."

    if (Test-Path $venvDir) {
        Remove-Item -Recurse -Force $venvDir
    }

    $pyZip = Join-Path $root "python_3.10.11.zip"
    $pyUrl = "https://www.nuget.org/api/v2/package/python/3.10.11"
    Invoke-WebRequest -Uri $pyUrl -OutFile $pyZip

    $extractDir = Join-Path $root "_py_extract_tmp"
    if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
    Expand-Archive -Path $pyZip -DestinationPath $extractDir -Force

    Move-Item -Path (Join-Path $extractDir "tools") -Destination $venvDir
    Remove-Item -Recurse -Force $extractDir
    Remove-Item -Force $pyZip

    # 開啟 site-packages（embeddable python預設關閉，pip安裝的套件才讀得到）
    $pthFile = Join-Path $venvDir "python310._pth"
    if (Test-Path $pthFile) {
        (Get-Content $pthFile) -replace '^#import site$', 'import site' | Set-Content $pthFile
    }

    Write-Host "[Setup] 安裝套件中（會下載約 5GB，含 PyTorch，請耐心等候，視網速可能要 10-30 分鐘）..."
    & $pythonExe -m pip install --upgrade pip -q
    & $pythonExe -m pip install -r (Join-Path $root "requirements_GPU.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[Setup][錯誤] 套件安裝失敗，請檢查網路連線後重新執行。"
        exit 1
    }
    Write-Host "[Setup] Python 執行環境安裝完成。"
} else {
    Write-Host "[Setup] 執行環境已存在，略過。"
}

# ── 2. ffmpeg / ffprobe ──────────────────────────────────
$binDir = Join-Path $root "bin"
$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
$ffprobeExe = Join-Path $binDir "ffprobe.exe"

if (-not (Test-Path $ffmpegExe) -or -not (Test-Path $ffprobeExe)) {
    Write-Host "[Setup] 找不到 ffmpeg/ffprobe，開始下載（約160MB）..."
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null

    $ffZip = Join-Path $root "ffmpeg_tmp.zip"
    $ffUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    Invoke-WebRequest -Uri $ffUrl -OutFile $ffZip

    $ffExtractDir = Join-Path $root "_ffmpeg_extract_tmp"
    if (Test-Path $ffExtractDir) { Remove-Item -Recurse -Force $ffExtractDir }
    Expand-Archive -Path $ffZip -DestinationPath $ffExtractDir -Force

    $foundFfmpeg = Get-ChildItem -Path $ffExtractDir -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
    $foundFfprobe = Get-ChildItem -Path $ffExtractDir -Recurse -Filter "ffprobe.exe" | Select-Object -First 1
    if (-not $foundFfmpeg -or -not $foundFfprobe) {
        Write-Host "[Setup][錯誤] 下載的壓縮檔裡找不到 ffmpeg.exe/ffprobe.exe，安裝失敗。"
        exit 1
    }
    Copy-Item $foundFfmpeg.FullName $ffmpegExe -Force
    Copy-Item $foundFfprobe.FullName $ffprobeExe -Force

    Remove-Item -Recurse -Force $ffExtractDir
    Remove-Item -Force $ffZip
    Write-Host "[Setup] ffmpeg/ffprobe 安裝完成。"
} else {
    Write-Host "[Setup] ffmpeg/ffprobe 已存在，略過。"
}

Write-Host "[Setup] 全部安裝完成！"
