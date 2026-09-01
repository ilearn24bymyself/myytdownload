# First-run auto-installer for 3-4.Yt-down-sub
# Called automatically by 01/02/03 .bat launchers when venv_gpu or bin\ffmpeg.exe/ffprobe.exe
# is missing. Requires nothing pre-installed beyond Windows 10/11's built-in PowerShell.
# Each step only acts when something is actually missing, so it's safe and fast to call
# this script on every launch as a check.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest's built-in progress bar badly slows down large downloads on PS 5.1
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# PyTorch ships deeply nested header files under site-packages\torch\include\...\*.h.
# Combined with venv_gpu\Lib\site-packages\torch\include\..., the longest of those
# filenames adds about 145 characters after the project root. Windows' classic 260-char
# MAX_PATH limit means pip install silently fails with a confusing OSError if this
# folder sits too deep (e.g. inside several layers of Downloads/OneDrive folders).
# Warn early with a clear message instead of failing 10+ minutes into the install.
if ($root.Length -gt 110) {
    Write-Host "[Setup][WARNING] This folder's path is $($root.Length) characters long:"
    Write-Host "  $root"
    Write-Host "  PyTorch installation can fail on Windows if the path is too deep (long-path limit)."
    Write-Host "  If setup fails below, move this whole folder somewhere shorter (e.g. C:\ytdownload) and run it again."
    Write-Host ""
}

$venvDir = Join-Path $root "venv_gpu"
$pythonExe = Join-Path $venvDir "python.exe"

# ---- 1. Portable Python + packages ----
if (-not (Test-Path $pythonExe)) {
    Write-Host "[Setup] Runtime not found, installing portable Python (about 30MB)..."

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

    # Enable site-packages (embeddable python ships with it disabled by default,
    # otherwise pip-installed packages can't be imported)
    $pthFile = Join-Path $venvDir "python310._pth"
    if (Test-Path $pthFile) {
        (Get-Content $pthFile) -replace '^#import site$', 'import site' | Set-Content $pthFile
    }

    Write-Host "[Setup] Installing packages (about 5GB including PyTorch, this can take 10-30 minutes depending on your connection)..."
    & $pythonExe -m pip install --upgrade pip -q
    & $pythonExe -m pip install -r (Join-Path $root "requirements_GPU.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[Setup][ERROR] Package install failed. Check your internet connection and run this again."
        exit 1
    }
    Write-Host "[Setup] Python runtime installed."
} else {
    Write-Host "[Setup] Runtime already present, skipping."
}

# ---- 2. ffmpeg / ffprobe ----
$binDir = Join-Path $root "bin"
$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
$ffprobeExe = Join-Path $binDir "ffprobe.exe"

if (-not (Test-Path $ffmpegExe) -or -not (Test-Path $ffprobeExe)) {
    Write-Host "[Setup] ffmpeg/ffprobe not found, downloading (about 160MB)..."
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
        Write-Host "[Setup][ERROR] ffmpeg.exe/ffprobe.exe not found inside the downloaded archive. Install failed."
        exit 1
    }
    Copy-Item $foundFfmpeg.FullName $ffmpegExe -Force
    Copy-Item $foundFfprobe.FullName $ffprobeExe -Force

    Remove-Item -Recurse -Force $ffExtractDir
    Remove-Item -Force $ffZip
    Write-Host "[Setup] ffmpeg/ffprobe installed."
} else {
    Write-Host "[Setup] ffmpeg/ffprobe already present, skipping."
}

Write-Host "[Setup] All done!"
