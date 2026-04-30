param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$DocumentPath = "./data/NYSE_KO_2024.pdf",
    [string]$DocumentName = "NYSE_KO_2024",
    [string]$Question = "What was Coca-Cola revenue in 2024?",
    [string]$SessionId = "ps-test-session",
    [string]$StreamOutputPath = "stream_output.txt",
    [switch]$AllowMissingApiKey
)

$ErrorActionPreference = "Stop"
$failedChecks = @()

function Assert-Check {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if ($Condition) {
        Write-Host "[PASS] $Message" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $Message" -ForegroundColor Red
        $script:failedChecks += $Message
    }
}

Write-Host "==> Upload/Ingest"
$uploadRaw = curl.exe -sS -X POST "$BaseUrl/upload" `
  -F "document_path=$DocumentPath" `
  -F "document_name=$DocumentName" `
  -F "rebuild_index=true" 2>&1
try {
    $uploadResp = $uploadRaw | ConvertFrom-Json
    $uploadResp | ConvertTo-Json -Depth 8
    if ($AllowMissingApiKey) {
        $uploadDetail = "$($uploadResp.detail)"
        Assert-Check ($uploadDetail -match "OPENAI_API_KEY is not configured") "Upload returns expected missing key message"
    } else {
        Assert-Check ($uploadResp.pages -gt 0) "Upload returns pages > 0"
        Assert-Check ($uploadResp.chunks -gt 0) "Upload returns chunks > 0"
        Assert-Check ($uploadResp.vectors -gt 0) "Upload returns vectors > 0"
    }
} catch {
    Assert-Check $false "Upload response is valid JSON"
    Write-Host $uploadRaw
}

Write-Host "`n==> Chat"
$chatBody = @{
    question   = $Question
    session_id = $SessionId
} | ConvertTo-Json
try {
    $chatResp = Invoke-RestMethod -Uri "$BaseUrl/chat" -Method Post -ContentType "application/json" -Body $chatBody
    $chatResp | ConvertTo-Json -Depth 8
    if ($AllowMissingApiKey) {
        Assert-Check $false "Chat should fail when key missing"
    } else {
        Assert-Check (-not [string]::IsNullOrWhiteSpace($chatResp.answer)) "Chat answer is non-empty"
        Assert-Check ($null -ne $chatResp.sources) "Chat sources field exists"
        Assert-Check ($chatResp.sources -is [System.Array]) "Chat sources is an array"
    }
} catch {
    if ($AllowMissingApiKey) {
        $errText = $_.ErrorDetails.Message
        Assert-Check ($errText -match "OPENAI_API_KEY is not configured") "Chat returns expected missing key message"
    } else {
        throw
    }
}

Write-Host "`n==> Chat Stream (raw SSE)"
$streamBody = @{
    question   = $Question
    session_id = $SessionId
} | ConvertTo-Json -Compress

if (Test-Path $StreamOutputPath) {
    Remove-Item $StreamOutputPath -Force
}

if ($AllowMissingApiKey) {
    try {
        $streamResp = Invoke-WebRequest -Uri "$BaseUrl/chat/stream" -Method Post -ContentType "application/json" -Body $streamBody
        $streamText = $streamResp.Content
    } catch {
        $streamText = $_.ErrorDetails.Message
    }
    $streamText | Out-File -FilePath $StreamOutputPath -Encoding utf8
    Assert-Check ($streamText -match "OPENAI_API_KEY is not configured") "Stream returns expected missing key message"
} else {
    $streamResult = curl.exe -sS -N -X POST "$BaseUrl/chat/stream" `
      -H "Content-Type: application/json" `
      -d $streamBody 2>&1
    $streamResult | Out-File -FilePath $StreamOutputPath -Encoding utf8
    $streamText = ($streamResult | Out-String)
    Assert-Check ($streamText -match "event:\s*done") "Stream contains done event"
    Assert-Check ($streamText -match "event:\s*sources") "Stream contains sources event"
    Assert-Check ($streamText -match "data:") "Stream emits SSE data lines"
}

Write-Host "`nSaved stream output to $StreamOutputPath"

if ($failedChecks.Count -gt 0) {
    Write-Host "`nSmoke test failed with $($failedChecks.Count) check(s):" -ForegroundColor Red
    $failedChecks | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "`nAll smoke checks passed." -ForegroundColor Green
exit 0
