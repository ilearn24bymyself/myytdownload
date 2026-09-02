# First-run auto-installer for 3-4.Yt-down-sub
# Called automatically by 01/02/03 .bat launchers when venv_gpu or bin\ffmpeg.exe/ffprobe.exe
# is missing. Requires nothing pre-installed beyond Windows 10/11's built-in PowerShell.
# Each step only acts when something is actually missing, so it's safe and fast to call
# this script on every launch as a check.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # 關掉PowerShell內建的下載進度條(在PS5.1上會嚴重拖慢大檔案下載速度)
                                            # 進度改用下面Invoke-DownloadWithProgress自己算、自己印,不吃這個效能懲罰
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

# ---- 帶百分比進度的下載函式,取代Invoke-WebRequest,避免PowerShell內建進度條拖慢速度 ----
function Invoke-DownloadWithProgress {
    param(
        [Parameter(Mandatory)] [string]$Uri,
        [Parameter(Mandatory)] [string]$OutFile,
        [Parameter(Mandatory)] [string]$Label
    )

    $request = [System.Net.HttpWebRequest]::Create($Uri)
    $request.AllowAutoRedirect = $true
    $response = $request.GetResponse()
    $totalBytes = $response.ContentLength
    $responseStream = $response.GetResponseStream()
    $fileStream = [System.IO.File]::Create($OutFile)

    $buffer = New-Object byte[] 65536
    $totalRead = 0
    $lastPrintedPercent = -1

    try {
        while ($true) {
            $read = $responseStream.Read($buffer, 0, $buffer.Length)
            if ($read -le 0) { break }
            $fileStream.Write($buffer, 0, $read)
            $totalRead += $read

            if ($totalBytes -gt 0) {
                $percent = [math]::Floor(($totalRead / $totalBytes) * 100)
                if ($percent -ne $lastPrintedPercent) {
                    $mbRead = [math]::Round($totalRead / 1MB, 1)
                    $mbTotal = [math]::Round($totalBytes / 1MB, 1)
                    Write-Host -NoNewline "`r[Setup] $Label : $percent% ($mbRead MB / $mbTotal MB)   "
                    $lastPrintedPercent = $percent
                }
            }
        }
    } finally {
        $fileStream.Close()
        $responseStream.Close()
        $response.Close()
    }
    Write-Host ""
}

$venvDir = Join-Path $root "venv_gpu"
$pythonExe = Join-Path $venvDir "python.exe"
$flavorMarker = Join-Path $venvDir "_installed_flavor.txt"
$requestedFlavor = if ($env:FORCE_CPU -eq "1") { "CPU" } else { "GPU" }
$requirementsFileName = if ($requestedFlavor -eq "CPU") { "requirements_CPU.txt" } else { "requirements_GPU.txt" }

Write-Host "[Setup] 步驟1/2:安裝Python執行環境($requestedFlavor 模式)"

# ---- 1a. Portable Python本體(只看python.exe在不在,這部分不會半途而廢——
#           解壓縮是原子性的資料夾操作,沒有「解壓一半」這種中間狀態) ----
if (-not (Test-Path $pythonExe)) {
    Write-Host "[Setup] Runtime not found, installing portable Python (about 30MB)..."

    if (Test-Path $venvDir) {
        Remove-Item -Recurse -Force $venvDir
    }

    $pyZip = Join-Path $root "python_3.10.11.zip"
    $pyUrl = "https://www.nuget.org/api/v2/package/python/3.10.11"
    Invoke-DownloadWithProgress -Uri $pyUrl -OutFile $pyZip -Label "下載Python執行環境"

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
    Write-Host "[Setup] Python執行檔已就緒。"
} else {
    Write-Host "[Setup] Python執行檔已存在,略過解壓縮這步。"
}

# ---- 1b. pip套件——不能只看python.exe在不在就判斷「裝好了」,pip install本身
#           可能中途失敗/被中斷(斷網、防毒軟體、使用者提早關視窗都可能發生),
#           那樣python.exe會留下來但套件是空的,之後每次啟動都會被誤判成「已裝好」。
#           改成直接檢查關鍵套件(streamlit)資料夾在不在,搭配flavor是否吻合,
#           兩者只要有一個沒過,就重新跑一次pip install(pip install本身是冪等的,
#           已經裝好的套件不會重複下載,只會補齊缺的/不合flavor的)。----
$streamlitMarker = Join-Path $venvDir "Lib\site-packages\streamlit"
$hasMarker = Test-Path $flavorMarker
$installedFlavor = if ($hasMarker) { (Get-Content $flavorMarker -Raw).Trim() } else { "" }
$packagesOk = (Test-Path $streamlitMarker) -and ($installedFlavor -eq $requestedFlavor)

if (-not $packagesOk) {
    if (Test-Path $streamlitMarker) {
        Write-Host "[Setup] 偵測到目前環境是用「$installedFlavor」模式安裝的,但這次啟動要求「$requestedFlavor」模式,重新安裝對應套件..."
    } else {
        Write-Host "[Setup] 套件尚未安裝完成(可能是上次安裝中途中斷),開始安裝..."
    }

    $sizeLabel = if ($requestedFlavor -eq "CPU") { "約1GB,不含PyTorch" } else { "約5GB,含PyTorch" }
    Write-Host "[Setup] 正在安裝套件($sizeLabel,這是整個安裝過程最花時間的部分,請耐心等候)..."
    & $pythonExe -m pip install --upgrade pip -q
    & $pythonExe -m pip install -r (Join-Path $root $requirementsFileName)
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $streamlitMarker)) {
        Write-Host "[Setup][ERROR] Package install failed. Check your internet connection and run this again."
        exit 1
    }
    Set-Content -Path $flavorMarker -Value $requestedFlavor
    Write-Host "[Setup] 套件安裝完成。"
} else {
    Write-Host "[Setup] 套件已安裝完成($requestedFlavor 模式),略過。"
}

# ---- 2. ffmpeg / ffprobe ----
Write-Host "[Setup] 步驟2/2:下載ffmpeg/ffprobe"

$binDir = Join-Path $root "bin"
$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
$ffprobeExe = Join-Path $binDir "ffprobe.exe"

if (-not (Test-Path $ffmpegExe) -or -not (Test-Path $ffprobeExe)) {
    Write-Host "[Setup] ffmpeg/ffprobe not found, downloading (about 160MB)..."
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null

    $ffZip = Join-Path $root "ffmpeg_tmp.zip"
    $ffUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    Invoke-DownloadWithProgress -Uri $ffUrl -OutFile $ffZip -Label "下載ffmpeg"

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
