# Trading Research Scanner - Windows setup
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "=== Trading Research Scanner Setup ===" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example - add your API keys." -ForegroundColor Yellow
}

$venvPath = Join-Path $Root "backend\.venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating Python virtual environment..."
    python -m venv $venvPath
}
& "$venvPath\Scripts\python.exe" -m pip install --upgrade pip
& "$venvPath\Scripts\pip.exe" install -r (Join-Path $Root "backend\requirements.txt")

New-Item -ItemType Directory -Force -Path (Join-Path $Root "backend\data") | Out-Null

$frontend = Join-Path $Root "frontend"
if (Test-Path (Join-Path $frontend "package.json")) {
    Push-Location $frontend
    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing frontend dependencies..."
        npm install
    }
    Pop-Location
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "  1. Edit .env with API keys"
Write-Host "  2. Backend: cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000"
Write-Host "  3. Frontend: cd frontend; npm run dev"
Write-Host "  4. API docs: http://localhost:8000/docs"
