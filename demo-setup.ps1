# demo-setup.ps1 — One-command demo setup for Nepal Legal Case Search
#
# Run from the project root (PowerShell):
#   .\demo-setup.ps1
#
# What it does:
#   1. Creates .env with secure random secrets (skipped if .env already exists)
#   2. Starts PostgreSQL in Docker on 127.0.0.1:5433
#   3. Applies all database migrations
#   4. Downloads + imports 100 Supreme Court judgment sample (skipped if data exists)
#   5. Processes documents, computes AI embeddings (~13 min on CPU — skipped if done)
#   6. Creates demo accounts: admin / analyst / viewer
#   7. Builds and starts the full app stack (backend + Caddy) on https://localhost:8443
#   8. Saves login credentials to .dev-credentials.txt
#
# Flags:
#   -SkipData    Skip the data download / import / embedding steps entirely
#   -ForceData   Re-import and re-embed even if data already exists
#   -DevOnly     Start db + backend only (no Docker full-stack); for local dev with npm run dev

param(
    [switch]$SkipData,
    [switch]$ForceData,
    [switch]$DevOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Helpers ────────────────────────────────────────────────────────────────────

function Write-Step([string]$msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "    !!  $msg" -ForegroundColor Yellow }
function Write-Fail([string]$msg) { Write-Host "    XX  $msg" -ForegroundColor Red; exit 1 }

function Require-Command([string]$name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Fail "$name is not installed or not in PATH. Install it and retry."
    }
}

function Generate-Secret {
    # 48 random bytes → 64-char URL-safe base64 string
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes) -replace '\+','-' -replace '/','_' -replace '=',''
}

# ── 0. Prerequisites ────────────────────────────────────────────────────────────

Write-Step "Checking prerequisites"
Require-Command "docker"
Require-Command "uv"

$dockerRunning = docker info 2>&1
if ($LASTEXITCODE -ne 0) { Write-Fail "Docker is not running. Start Docker Desktop and retry." }
Write-Ok "Docker is running"

# ── 1. Create .env ──────────────────────────────────────────────────────────────

Write-Step "Setting up .env"
if (Test-Path ".env") {
    Write-Ok ".env already exists — keeping it"
} else {
    Write-Warn ".env not found — generating one from .env.example with secure random secrets"
    $envContent = Get-Content ".env.example" -Raw

    # Replace placeholder secrets with generated values
    $jwtSecret   = Generate-Secret
    $auditSecret = Generate-Secret
    $dbPassword  = Generate-Secret

    $envContent = $envContent -replace "POSTGRES_PASSWORD=change-me", "POSTGRES_PASSWORD=$dbPassword"
    $envContent = $envContent -replace "JWT_SECRET=change-me",         "JWT_SECRET=$jwtSecret"
    $envContent = $envContent -replace "AUDIT_SECRET=change-me",       "AUDIT_SECRET=$auditSecret"

    Set-Content ".env" $envContent -Encoding UTF8
    Write-Ok ".env created with generated secrets"
}

# ── 2. Start the database ───────────────────────────────────────────────────────

Write-Step "Starting the database (PostgreSQL + pgvector)"
docker compose up -d db
if ($LASTEXITCODE -ne 0) { Write-Fail "docker compose up -d db failed" }

Write-Host "    Waiting for database to be healthy..." -ForegroundColor Gray
$tries = 0
do {
    Start-Sleep 3
    $health = docker compose ps db --format json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
    $tries++
    if ($tries -gt 20) { Write-Fail "Database did not become healthy after 60 s. Check: docker compose logs db" }
} until ($health.Health -eq "healthy" -or (docker compose ps db 2>&1) -match "healthy")
Write-Ok "Database is healthy"

# ── 3. Apply database migrations ───────────────────────────────────────────────

Write-Step "Applying database migrations"
Push-Location backend
try {
    uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Write-Fail "alembic upgrade head failed" }
    Write-Ok "Migrations applied"
} finally { Pop-Location }

# ── 4. Import sample data ───────────────────────────────────────────────────────

if (-not $SkipData) {
    Write-Step "Checking for existing case data"
    Push-Location backend
    try {
        # Count cases in the database
        $caseCount = uv run python -c @"
from app.db.session import SessionLocal
from app.db.models import CaseRecord
with SessionLocal() as s:
    n = s.query(CaseRecord).count()
    print(n)
"@
        if ($LASTEXITCODE -ne 0) { $caseCount = "0" }
    } catch { $caseCount = "0" }
    Pop-Location

    if ([int]$caseCount -gt 0 -and -not $ForceData) {
        Write-Ok "$caseCount cases already in the database — skipping data import (use -ForceData to re-import)"
    } else {
        Write-Warn "No cases found (or -ForceData set) — importing 100-judgment sample"
        Write-Warn "This will take 15–30 minutes total on a CPU-only machine (embedding step ~13 min)"

        Push-Location backend
        try {
            Write-Host "    Downloading sample judgments..." -ForegroundColor Gray
            uv run python -m scripts.sc_download
            if ($LASTEXITCODE -ne 0) { Write-Fail "sc_download failed" }

            Write-Host "    Importing judgments into the database..." -ForegroundColor Gray
            uv run python -m scripts.sc_import
            if ($LASTEXITCODE -ne 0) { Write-Fail "sc_import failed" }

            Write-Host "    Extracting text from documents..." -ForegroundColor Gray
            uv run python -m scripts.process_documents
            if ($LASTEXITCODE -ne 0) { Write-Fail "process_documents failed" }

            Write-Host "    Computing AI embeddings (~13 min on CPU — please wait)..." -ForegroundColor Gray
            uv run python -m scripts.embed_chunks
            if ($LASTEXITCODE -ne 0) { Write-Fail "embed_chunks failed" }

            Write-Host "    Extracting statutory provisions..." -ForegroundColor Gray
            uv run python -m scripts.extract_provisions
            if ($LASTEXITCODE -ne 0) { Write-Fail "extract_provisions failed" }

            Write-Host "    Extracting case timelines..." -ForegroundColor Gray
            uv run python -m scripts.extract_timeline
            if ($LASTEXITCODE -ne 0) { Write-Fail "extract_timeline failed" }

            Write-Ok "Sample data imported and processed"
        } finally { Pop-Location }
    }
} else {
    Write-Warn "-SkipData set — skipping data import (the app will start but searches will return no results)"
}

# ── 5. Create demo accounts ─────────────────────────────────────────────────────

Write-Step "Creating demo accounts"

$adminPw   = "Admin@Nepal2024!"
$analystPw = "Analyst@Nepal2024!"
$viewerPw  = "Viewer@Nepal2024!"

Push-Location backend
try {
    function Create-DemoUser([string]$username, [string]$password, [string]$role, [string]$clearance, [string]$displayName) {
        # Check if user already exists; if so, reset password to the demo value
        $exists = uv run python -c @"
from app.db.session import SessionLocal
from app.db.models import User
with SessionLocal() as s:
    u = s.query(User).filter_by(username='$username').first()
    print('yes' if u else 'no')
"@
        if ($exists.Trim() -eq "yes") {
            Write-Warn "  '$username' already exists — resetting password to demo value"
            $password | uv run python -m scripts.create_user $username --reset-password --password-stdin
        } else {
            $password | uv run python -m scripts.create_user $username `
                --role $role --clearance $clearance --name $displayName --password-stdin
        }
        if ($LASTEXITCODE -ne 0) { Write-Warn "  Could not create/update '$username' — continuing anyway" }
        else { Write-Ok "  $username ($role, clearance=$clearance)" }
    }

    Create-DemoUser "admin"   $adminPw   "admin"   "confidential" "Demo Admin"
    Create-DemoUser "analyst" $analystPw "analyst" "restricted"   "Demo Analyst"
    Create-DemoUser "viewer"  $viewerPw  "viewer"  "public"       "Demo Viewer"
} finally { Pop-Location }

# Save credentials to .dev-credentials.txt (git-ignored)
$credsContent = @"
# Demo login credentials — NEVER commit this file (it is in .gitignore)
# Generated by demo-setup.ps1 on $(Get-Date -Format "yyyy-MM-dd HH:mm")

URL: https://localhost:8443

admin    / $adminPw    (role=admin,   clearance=confidential — sees everything, audit log)
analyst  / $analystPw  (role=analyst, clearance=restricted   — search, upload, CDR)
viewer   / $viewerPw   (role=viewer,  clearance=public        — read-only)
"@
Set-Content ".dev-credentials.txt" $credsContent -Encoding UTF8
Write-Ok "Credentials saved to .dev-credentials.txt"

# ── 6. Start the full application ───────────────────────────────────────────────

if ($DevOnly) {
    Write-Step "Starting backend only (dev mode)"
    Push-Location backend
    Write-Ok "Run in a separate terminal: uv run uvicorn app.main:app --reload --port 8000"
    Write-Ok "Run in another terminal:   cd frontend && npm install && npm run dev"
    Pop-Location
} else {
    Write-Step "Building and starting the full application stack on https://localhost:8443"
    docker compose --profile app up -d --build
    if ($LASTEXITCODE -ne 0) { Write-Fail "docker compose --profile app up -d --build failed" }

    Write-Host "    Waiting for backend to become healthy..." -ForegroundColor Gray
    $tries = 0
    do {
        Start-Sleep 5
        $tries++
        if ($tries -gt 24) {
            Write-Warn "Backend health check timed out — it may still be starting. Check: docker compose logs backend"
            break
        }
        $healthOut = docker compose ps backend --format json 2>$null
    } until ($healthOut -match '"Health":"healthy"' -or $healthOut -match "healthy")
    Write-Ok "Application stack is up"
}

# ── 7. Trust the Caddy certificate (optional) ───────────────────────────────────

Write-Step "Caddy certificate"
Write-Warn "Your browser will show a certificate warning until you trust Caddy's root CA."
Write-Warn "To fix it once, run:"
Write-Host "    docker compose --profile app cp web:/data/caddy/pki/authorities/local/root.crt caddy-root.crt" -ForegroundColor Gray
Write-Host "    Then: open caddy-root.crt and install it into 'Trusted Root Certification Authorities'" -ForegroundColor Gray

# ── 8. Summary ──────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Nepal Legal Case Search — DEMO READY" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  URL:     https://localhost:8443" -ForegroundColor White
Write-Host "  HTTP:    http://localhost:8080  (redirects to HTTPS)" -ForegroundColor Gray
Write-Host ""
Write-Host "  admin    / $adminPw    (admin, confidential)" -ForegroundColor White
Write-Host "  analyst  / $analystPw  (analyst, restricted)" -ForegroundColor White
Write-Host "  viewer   / $viewerPw   (viewer, public)" -ForegroundColor White
Write-Host ""
Write-Host "  Credentials also saved in:  .dev-credentials.txt" -ForegroundColor Gray
Write-Host ""
Write-Host "  Stop:    docker compose --profile app down" -ForegroundColor Gray
Write-Host "  Logs:    docker compose --profile app logs -f" -ForegroundColor Gray
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
