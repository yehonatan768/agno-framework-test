Write-Host "== Agno Project Bootstrap (Windows) =="

# -----------------------------------
# 1. Check Python 3.11
# -----------------------------------
$python = Get-Command python -ErrorAction SilentlyContinue

$versionOK = $false
if ($python) {
    $version = python --version 2>&1
    if ($version -match "3\.11") {
        $versionOK = $true
    }
}

if (-not $versionOK) {
    Write-Host "Python 3.11 not found. Installing..."

    winget install --id Python.Python.3.11 -e --source winget
}

# Refresh PATH for this session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + `
            [System.Environment]::GetEnvironmentVariable("Path","User")

# -----------------------------------
# 2. Create venv
# -----------------------------------
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
} else {
    Write-Host ".venv already exists"
}

# -----------------------------------
# 3. Activate venv
# -----------------------------------
.\.venv\Scripts\Activate.ps1

# -----------------------------------
# 4. Upgrade pip
# -----------------------------------
python -m pip install --upgrade pip setuptools wheel

# -----------------------------------
# 5. Install dependencies
# -----------------------------------
if (-not (Test-Path "requirements.txt")) {
    Write-Host "ERROR: requirements.txt not found"
    exit 1
}

pip install -r requirements.txt

# -----------------------------------
# 6. Done
# -----------------------------------
Write-Host ""
Write-Host "===================================="
Write-Host "Environment ready."
Write-Host "Activate with:"
Write-Host "   .\.venv\Scripts\Activate.ps1"
Write-Host "===================================="
