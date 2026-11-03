$ErrorActionPreference = "Stop"

$repoZip = "https://github.com/hareshkumar6808/dbs/archive/refs/heads/main.zip"
$projectDir = Join-Path $HOME "AeroPulse"
$dockerExe = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
$desktopExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"

Write-Host "=== AeroPulse setup ===" -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and -not (Test-Path $dockerExe)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "Install Docker Desktop first: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "Docker Desktop is missing. Installing it now..." -ForegroundColor Yellow
    winget install --id Docker.DockerDesktop --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Finish Docker Desktop installation, restart Windows if requested, then run this same command again." -ForegroundColor Yellow
        exit 1
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path $dockerExe)) {
    $env:Path = "$(Split-Path $dockerExe);$env:Path"
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker was installed. Close and reopen PowerShell, then run this same command again." -ForegroundColor Yellow
    exit 1
}

if (Test-Path $desktopExe) {
    if (-not (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Write-Host "Starting Docker Desktop..."
        Start-Process $desktopExe
    }
}

Write-Host "Waiting for Docker Engine..."
$engineReady = $false
for ($i = 0; $i -lt 60; $i++) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        $engineReady = $true
        break
    }
    Start-Sleep -Seconds 5
}
if (-not $engineReady) {
    Write-Host "Open Docker Desktop, wait until it says Engine running, then run this same command again." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $projectDir "docker-compose.yml"))) {
    if (Test-Path $projectDir) {
        throw "The folder $projectDir already exists but is not an AeroPulse checkout. Rename it and run this command again."
    }
    Write-Host "Downloading AeroPulse..."
    $tempZip = Join-Path $env:TEMP "aeropulse-main.zip"
    $tempDir = Join-Path $env:TEMP "aeropulse-extract"
    Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest $repoZip -OutFile $tempZip -UseBasicParsing
    Expand-Archive $tempZip -DestinationPath $tempDir -Force
    New-Item -ItemType Directory -Path (Split-Path $projectDir) -Force | Out-Null
    Move-Item (Join-Path $tempDir "dbs-main") $projectDir
    Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}

Set-Location $projectDir
Write-Host "Building and starting AeroPulse. The first run can take several minutes..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "AeroPulse could not start. Check Docker Desktop and try again."
}

Write-Host "Waiting for AeroPulse to become available..."
$appReady = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-WebRequest "http://localhost:3000" -UseBasicParsing -TimeoutSec 3 | Out-Null
        $appReady = $true
        break
    } catch {
        Start-Sleep -Seconds 5
    }
}
if ($appReady) {
    Start-Process "http://localhost:3000"
    Write-Host "AeroPulse is ready: http://localhost:3000" -ForegroundColor Green
} else {
    Write-Host "Containers started. The app may still be initializing; open http://localhost:3000 in a minute." -ForegroundColor Yellow
}
Write-Host "Project folder: $projectDir"
Write-Host "To stop AeroPulse later: open PowerShell, run 'cd $projectDir', then 'docker compose down'."
