$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    $python312 = $null
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $python312 = & python -c "import sys; print(sys.executable if sys.version_info[:2] == (3, 12) else '')" 2>$null
    }
    if ($python312) {
        & $python312 -m venv .venv
    } else {
        py -3.12 -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required (on PATH or registered with py).' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path -LiteralPath 'vendor\opencv_zoo_runtime\models\palm_detection_mediapipe\mp_palmdet.py')) {
    throw 'Bundled OpenCV Zoo source is missing. Download or clone the complete project.'
}
& '.\.venv\Scripts\python.exe' download_models.py
if ($LASTEXITCODE -ne 0) { throw 'Model verification failed.' }
Write-Host 'Ready. Double-click start.cmd to launch.'
