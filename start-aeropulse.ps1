$ErrorActionPreference = "Stop"

$repoZip = "https://github.com/hareshkumar6808/dbs/archive/refs/heads/main.zip"
$projectDir = Join-Path $HOME "AeroPulse"
$dockerExe = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
$desktopExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"

Write-Host "=== AeroPulse setup ===" -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and -not (Test-Path $dockerExe)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "Please install Docker Desktop first: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "Docker Desktop is missing. Installing it now..." -ForegroundColor Yellow
    winget install --id Docker.DockerDesktop --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Docker Desktop installation did not finish. Complete it, restart Windows if requested, then run this command again." -ForegroundColor Yellow
        exit 1
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path $dockerExe)) {
    $env:Path = "$(Split-Path $dockerExe);$env:Path"
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker was installed. Restart PowerShell and run this command again." -ForegroundColor Yellow
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
    Write-Host "Docker Engine is not ready. Open Docker Desktop, wait until it says Engine running, then run this command again." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $projectDir "docker-compose.yml"))) {
    Write-Host "Downloading AeroPulse..."
    $tempZip = Join-Path $env:TEMP "aeropulse-main.zip"
    $tempDir = Join-Path $env:TEMP "aeropulse-extract"
    Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest $repoZip -OutFile $tempZip
    Expand-Archive $tempZip -DestinationPath $tempDir -Force
    New-Item -ItemType Directory -Path (Split-Path $projectDir) -Force | Out-Null
    if (Test-Path $projectDir) {
        Remove-Item $projectDir -Recurse -Force
    }
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

Write-Host "AeroPulse is starting. Opening http://localhost:3000 ..." -ForegroundColor Green
Start-Process "http://localhost:3000"
Write-Host "Project folder: $projectDir"
Write-Host "To stop AeroPulse later, run: docker compose down (from the project folder)"
