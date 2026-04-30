# Push this project to https://github.com/Nabeel5160/Chatbot
# Requires: Git for Windows, a GitHub PAT or SSH auth for push.
# Run from repo root: powershell -ExecutionPolicy Bypass -File .\scripts\push_to_github.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$gitCandidates = @(
    "C:\Program Files\Git\bin\git.exe",
    "C:\Program Files (x86)\Git\bin\git.exe",
    "$env:ProgramFiles\Git\bin\git.exe"
)
$git = $gitCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $git) {
    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if ($gitCmd) { $git = $gitCmd.Source }
}
if (-not $git) {
    Write-Host "Git not found. Install: winget install Git.Git"
    Write-Host "Then close and reopen PowerShell and run this script again."
    exit 1
}

Write-Host "Using: $git"
& $git --version

$remoteUrl = "https://github.com/Nabeel5160/Chatbot.git"

if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    Write-Host "Initializing git repository..."
    & $git init
}

$hasRemote = & $git remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    & $git remote add origin $remoteUrl
} else {
    & $git remote set-url origin $remoteUrl
}

Write-Host "Fetching default branch name..."
$branch = "main"
& $git branch -M $branch 2>$null

Write-Host "Staging all tracked files (respects .gitignore)..."
& $git add -A
$status = & $git status --porcelain
if (-not $status) {
    Write-Host "Nothing to commit (working tree clean)."
} else {
    & $git commit -m "Sync local Chatbot project to GitHub"
}

Write-Host "Pushing to origin $branch ..."
& $git push -u origin $branch
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Push failed. Common fixes:"
    Write-Host "  1) Create the empty repo on GitHub: https://github.com/new  (name: Chatbot, do not add README if you already have commits)"
    Write-Host "  2) Use a Personal Access Token when Git asks for password (GitHub no longer accepts account passwords for HTTPS)"
    Write-Host "     https://github.com/settings/tokens"
    Write-Host "  3) Or use SSH: git remote set-url origin git@github.com:Nabeel5160/Chatbot.git"
    exit 1
}

Write-Host "Done. Repository: https://github.com/Nabeel5160/Chatbot"
exit 0
