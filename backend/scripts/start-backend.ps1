# Start backend — frees port 8000 if stuck, then runs uvicorn
$ErrorActionPreference = "Stop"
$Backend = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Backend

$port = 8000
$conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $pid = $conn[0].OwningProcess
    Write-Host "Port $port in use by PID $pid — stopping..." -ForegroundColor Yellow
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

Write-Host "Starting API on http://localhost:$port" -ForegroundColor Green
& "$Backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port $port
