param(
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5173,
    [string]$NgrokExe = "ngrok",
    [string]$PythonExe = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Test-UrlReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $null = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 4
            return $true
        } catch {
            Start-Sleep -Milliseconds 800
        }
    }
    return $false
}

function Get-NgrokPublicUrl {
    param([int]$TimeoutSeconds = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 3
            $httpsTunnel = $resp.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
            if ($httpsTunnel -and $httpsTunnel.public_url) {
                return $httpsTunnel.public_url
            }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    return ""
}

function Resolve-NgrokExe {
    param([string]$Requested)
    $cmd = Get-Command $Requested -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        (Join-Path $HOME "ngrok.exe"),
        (Join-Path $HOME "Downloads\ngrok.exe"),
        (Join-Path $HOME "Desktop\ngrok.exe"),
        "C:\ProgramData\chocolatey\bin\ngrok.exe"
    )

    foreach ($path in $candidates) {
        if (Test-Path $path) {
            return $path
        }
    }

    $downloadMatches = Get-ChildItem -Path (Join-Path $HOME "Downloads") -Filter "ngrok.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($downloadMatches) {
        return $downloadMatches.FullName
    }

    return ""
}

if (-not (Test-Path $PythonExe)) {
    throw "Python not found at '$PythonExe'. Create venv first: python -m venv .venv"
}

$resolvedNgrokExe = Resolve-NgrokExe -Requested $NgrokExe
if (-not $resolvedNgrokExe) {
    throw "ngrok was not found. Install from https://ngrok.com/download, run: ngrok config add-authtoken <token>, or pass -NgrokExe with full path."
}

$apiProc = $null
$frontendProc = $null
$ngrokProc = $null

try {
    Write-Step "Starting FastAPI on port $ApiPort"
    $apiProc = Start-Process -FilePath $PythonExe `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$ApiPort" `
        -PassThru

    if (-not (Test-UrlReady -Url "http://127.0.0.1:$ApiPort/health" -TimeoutSeconds 120)) {
        throw "FastAPI did not become ready at /health."
    }

    Write-Step "Starting Vite frontend on port $FrontendPort"
    $frontendProc = Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run", "dev", "--", "--host", "0.0.0.0", "--port", "$FrontendPort", "--strictPort" `
        -WorkingDirectory "frontend" `
        -PassThru

    if (-not (Test-UrlReady -Url "http://127.0.0.1:$FrontendPort" -TimeoutSeconds 90)) {
        throw "Vite dev server did not become ready."
    }

    Write-Step "Starting ngrok tunnel for frontend port $FrontendPort"
    $ngrokProc = Start-Process -FilePath $resolvedNgrokExe `
        -ArgumentList "http", "$FrontendPort", "--host-header=localhost:$FrontendPort" `
        -PassThru

    $publicUrl = Get-NgrokPublicUrl
    if (-not $publicUrl) {
        throw "ngrok started but public URL was not detected from http://127.0.0.1:4040/api/tunnels"
    }

    Write-Host ""
    Write-Host "Public app URL (share this): $publicUrl" -ForegroundColor Green
    Write-Host "Local frontend URL: http://127.0.0.1:$FrontendPort"
    Write-Host "Local API URL: http://127.0.0.1:$ApiPort"
    Write-Host ""
    Write-Host "Keep this window open to keep the tunnel alive."
    Write-Host "Press Ctrl+C to stop."

    while ($true) {
        if ($apiProc.HasExited) { throw "FastAPI exited unexpectedly." }
        if ($frontendProc.HasExited) { throw "Frontend dev server exited unexpectedly." }
        if ($ngrokProc.HasExited) { throw "ngrok exited unexpectedly." }
        Start-Sleep -Seconds 2
    }
} finally {
    foreach ($proc in @($ngrokProc, $frontendProc, $apiProc)) {
        if ($null -ne $proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force
        }
    }
}
