param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$PythonExe = "python",
    [string]$VenvDir = ".venv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Wait-ForHealth {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-RestMethod -Uri "$Url/health" -Method Get -TimeoutSec 5
            if ($resp.status -eq "ok") {
                return $true
            }
        } catch {
            Start-Sleep -Milliseconds 800
        }
    }
    return $false
}

function Get-OpenAIKey {
    if ($env:OPENAI_API_KEY) {
        return $env:OPENAI_API_KEY
    }
    if (Test-Path ".env") {
        $line = Get-Content ".env" | Where-Object { $_ -match "^\s*OPENAI_API_KEY\s*=" } | Select-Object -First 1
        if ($line) {
            $value = ($line -split "=", 2)[1].Trim()
            if ($value) {
                return $value
            }
        }
    }
    return ""
}

Write-Step "Create virtual environment (if missing)"
if (-not (Test-Path $VenvDir)) {
    & $PythonExe -m venv $VenvDir
}

$venvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment python not found at $venvPython"
}

Write-Step "Install dependencies"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Step "Ensure PDF exists in data/"
if (-not (Test-Path "data")) {
    New-Item -ItemType Directory -Path "data" | Out-Null
}
if (-not (Test-Path "data/NYSE_KO_2024.pdf") -and (Test-Path "NYSE_KO_2024.pdf")) {
    Copy-Item "NYSE_KO_2024.pdf" "data/NYSE_KO_2024.pdf" -Force
}
if (-not (Test-Path "data/NYSE_KO_2024.pdf")) {
    throw "data/NYSE_KO_2024.pdf not found."
}

Write-Step "Compile project"
& $venvPython -m compileall app tests scripts

Write-Step "Run unit tests"
& $venvPython -m pytest -q

$openaiKey = Get-OpenAIKey
$allowMissingKeyMode = $false
if (-not $openaiKey) {
    Write-Host "OPENAI_API_KEY missing: running smoke tests in missing-key contract mode." -ForegroundColor Yellow
    $allowMissingKeyMode = $true
}

$serverProc = $null
try {
    Write-Step "Start FastAPI server"
    $serverProc = Start-Process -FilePath $venvPython `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" `
        -PassThru

    if (-not (Wait-ForHealth -Url $BaseUrl -TimeoutSeconds 90)) {
        throw "API health check did not pass in time."
    }

    Write-Step "Run endpoint smoke tests"
    if ($allowMissingKeyMode) {
        powershell -ExecutionPolicy Bypass -File ".\scripts\test_endpoints.ps1" -BaseUrl $BaseUrl -AllowMissingApiKey
    } else {
        powershell -ExecutionPolicy Bypass -File ".\scripts\test_endpoints.ps1" -BaseUrl $BaseUrl
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Endpoint smoke tests failed with exit code $LASTEXITCODE"
    }

    Write-Step "All checks completed successfully"
} finally {
    if ($null -ne $serverProc -and -not $serverProc.HasExited) {
        Write-Step "Stopping FastAPI server"
        Stop-Process -Id $serverProc.Id -Force
    }
}
