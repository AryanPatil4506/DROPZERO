# Start DROPZERO: backend and frontend in two windows, then open the browser.
#   powershell -ExecutionPolicy Bypass -File .\start.ps1
# Stop: press Ctrl+C in each window (or close them).
Set-Location $PSScriptRoot
$root = $PSScriptRoot

# a leftover backend from an earlier run would block port 8000
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

$be = "Set-Location '$root'; .venv\Scripts\activate; `$env:PYTHONIOENCODING='utf-8'; `$env:HF_HUB_OFFLINE='1'; `$host.UI.RawUI.WindowTitle='DROPZERO backend'; uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $be

if (-not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) {
    $fe = "Set-Location '$root\frontend'; `$host.UI.RawUI.WindowTitle='DROPZERO frontend'; npx vite --host 127.0.0.1 --port 5173"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $fe
}

Write-Host "Waiting for the backend..."
for ($i = 0; $i -lt 120; $i++) {
    try { Invoke-RestMethod http://127.0.0.1:8000/api/health -TimeoutSec 3 | Out-Null; break } catch { Start-Sleep 1 }
}
Start-Process "http://127.0.0.1:5173"
Write-Host "DROPZERO is running at http://127.0.0.1:5173"
