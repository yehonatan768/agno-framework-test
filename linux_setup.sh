#!/usr/bin/env bash
set -e

echo "== Agno Project Bootstrap (Linux) =="

# -----------------------------------
# 1. Ensure Python 3.11 exists
# -----------------------------------
if ! command -v python3.11 >/dev/null 2>&1; then
    echo "Python 3.11 not found. Installing..."

    sudo apt update
    sudo apt install -y software-properties-common
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt update
    sudo apt install -y python3.11 python3.11-venv python3.11-distutils
else
    echo "Python 3.11 found"
fi

# -----------------------------------
# 2. Create virtual environment
# -----------------------------------
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3.11 -m venv .venv
else
    echo ".venv already exists"
fi

# -----------------------------------
# 3. Activate venv
# -----------------------------------
source .venv/bin/activate

# -----------------------------------
# 4. Upgrade pip
# -----------------------------------
python -m pip install --upgrade pip setuptools wheel

# -----------------------------------
# 5. Install project dependencies
# -----------------------------------
if [ ! -f "requirements.txt" ]; then
    echo "ERROR: requirements.txt not found"
    exit 1
fi

pip install -r requirements.txt

# -----------------------------------
# 6. Done
# -----------------------------------
echo ""
echo "===================================="
echo "Environment ready."
echo "Activate with:"
echo "   source .venv/bin/activate"
echo "===================================="
