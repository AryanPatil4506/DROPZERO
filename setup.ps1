# DROPZERO one-time setup (Windows, NVIDIA GPU). Run from the project folder in PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
# Needs internet once (~12 GB total: Python packages + AI models). Safe to re-run.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Need($cmd, $wingetId, $label) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "Installing $label ..." -ForegroundColor Cyan
        winget install --id $wingetId -e --accept-source-agreements --accept-package-agreements --silent
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    }
}

Write-Host "== 1/6 Tools (Python 3.12, uv, Node.js, FFmpeg)" -ForegroundColor Green
Need "python" "Python.Python.3.12" "Python 3.12"
Need "uv" "astral-sh.uv" "uv"
Need "node" "OpenJS.NodeJS.LTS" "Node.js"
Need "git" "Git.Git" "Git"
winget list --id Gyan.FFmpeg -e *> $null
if ($LASTEXITCODE -ne 0) { winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent }

Write-Host "== 2/6 Python environment and packages" -ForegroundColor Green
if (-not (Test-Path .venv)) { uv venv .venv --python 3.12 }
uv pip install --python .venv\Scripts\python.exe -r requirements.txt

Write-Host "== 3/6 PyTorch with CUDA (matched to your GPU)" -ForegroundColor Green
$gpu = (nvidia-smi --query-gpu=name --format=csv,noheader 2>$null) -join " "
Write-Host "GPU: $gpu"
if ($gpu -match "RTX 50|RTX PRO|Blackwell") {
    # RTX 50xx (Blackwell) needs CUDA 12.8 builds. Its newer cuDNN also suits the newer Whisper engine.
    uv pip install --python .venv\Scripts\python.exe --reinstall torch --index-url https://download.pytorch.org/whl/cu128
    uv pip install --python .venv\Scripts\python.exe "ctranslate2>=4.6,<5"
} else {
    uv pip install --python .venv\Scripts\python.exe --reinstall "torch==2.6.0" --index-url https://download.pytorch.org/whl/cu124
}

Write-Host "== 4/6 Frontend packages" -ForegroundColor Green
Push-Location frontend; npm install --no-audit --no-fund; Pop-Location

Write-Host "== 5/6 Encryption key (.env)" -ForegroundColor Green
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    $key = (& .venv\Scripts\python.exe scripts\gen_key.py).Split("=", 2)[1]
    (Get-Content .env) -replace '^DROPZERO_MEDIA_KEY=.*', "DROPZERO_MEDIA_KEY=$key" | Set-Content .env
    Write-Host "New key written to .env (keep it private; it never leaves this machine)."
} else { Write-Host ".env already exists, kept." }

Write-Host "== 6/6 AI models (~9 GB, one time)" -ForegroundColor Green
$env:PYTHONIOENCODING = "utf-8"
& .venv\Scripts\python.exe scripts\download_models.py

Write-Host "`nSetup complete. Start the app with:  powershell -ExecutionPolicy Bypass -File .\start.ps1" -ForegroundColor Green
Write-Host "Optional demo video:  .venv\Scripts\python scripts\make_demo_video.py  (then upload it, or run scripts\precompute.py)"
