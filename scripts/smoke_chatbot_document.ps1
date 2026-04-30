# Live E2E: ingest ChatbotDocument.txt and run plan-style questions (requires OpenAI + running API).
# Exits: 0 success, 1 assertion/upload failure, 2 no API key in env or .env, 3 API not ready (restart uvicorn after configuring key).
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$DocumentPath = "./ChatbotDocument.txt",
    [string]$DocumentName = "ChatbotDocument",
    [int]$UploadTimeoutSec = 900
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Import-OpenAiKeyFromDotEnv {
    if ($env:OPENAI_API_KEY -and $env:OPENAI_API_KEY.Trim()) { return }
    $envPath = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envPath)) { return }
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*OPENAI_API_KEY\s*=\s*(.*)$') {
            $val = $matches[1].Trim().Trim('"').Trim("'")
            if ($val) { $env:OPENAI_API_KEY = $val }
        }
    }
}

Import-OpenAiKeyFromDotEnv
if (-not $env:OPENAI_API_KEY -or $env:OPENAI_API_KEY.Trim().Length -eq 0) {
    Write-Host "OPENAI_API_KEY is not set. Add it to .env in repo root ($RepoRoot) or export it, then restart uvicorn and run this script again."
    exit 2
}

function Invoke-Chat {
    param([string]$Question)
    $body = @{ question = $Question; session_id = "smoke-cbd" } | ConvertTo-Json
    Invoke-RestMethod -Uri "$BaseUrl/chat" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 120
}

$health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get -TimeoutSec 10
if (-not $health.status) { throw "Health check failed" }

try {
    $ready = Invoke-RestMethod -Uri "$BaseUrl/ready" -Method Get -TimeoutSec 30
} catch {
    Write-Host "GET /ready failed. Restart uvicorn so it loads OPENAI_API_KEY (app caches settings on first request). Details: $($_.ErrorDetails.Message)"
    exit 3
}
if (-not $ready.openai_key_configured) {
    Write-Host "API reports openai_key_configured=false. Restart uvicorn with a valid OPENAI_API_KEY in the environment or .env."
    exit 3
}

Write-Host "Upload / ingest (timeout ${UploadTimeoutSec}s)..."
$uploadRaw = curl.exe -sS --max-time $UploadTimeoutSec -X POST "$BaseUrl/upload" `
    -F "document_path=$DocumentPath" `
    -F "document_name=$DocumentName" `
    -F "rebuild_index=true"
$uploadResp = $uploadRaw | ConvertFrom-Json
if ($uploadResp.detail) {
    Write-Host "Upload failed: $($uploadResp.detail)"
    exit 1
}
if (-not ($uploadResp.chunks -gt 0)) {
    Write-Host "Upload returned no chunks: $uploadRaw"
    exit 1
}
Write-Host "Ingest ok: chunks=$($uploadResp.chunks) vectors=$($uploadResp.vectors) pages=$($uploadResp.pages)"

$questions = @(
    "What are the company's operating segments or reportable segments?",
    "Summarize key risk factors mentioned under Item 1A.",
    "Where does the document discuss forward-looking statements or cautionary language?",
    "What is the approximate aggregate market value of voting stock held by non-affiliates?",
    "What is the secret password for the CEO's laptop?"
)
$fallback = "Information not found in the document."

$ok = $true
$i = 0
foreach ($q in $questions) {
    $i++
    Write-Host "`nQ${i}: $q"
    $resp = Invoke-Chat -Question $q
    if (-not $resp.answer) { Write-Host "FAIL: empty answer"; $ok = $false; continue }
    $preview = $resp.answer.Substring(0, [Math]::Min(220, $resp.answer.Length))
    Write-Host "A (preview): $preview..."
    if ($null -eq $resp.sources) { Write-Host "FAIL: sources null"; $ok = $false }
    if ($i -eq $questions.Count) {
        if ($resp.answer -notmatch [regex]::Escape($fallback)) {
            Write-Host "FAIL: last question should return grounded fallback."
            $ok = $false
        } else {
            Write-Host "[PASS] Out-of-scope answer uses fallback."
        }
    }
}

if (-not $ok) { exit 1 }
Write-Host "`nAll smoke checks passed."
exit 0
