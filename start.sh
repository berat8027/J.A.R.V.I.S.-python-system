#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  J.A.R.V.I.S. - Just A Rather Very Intelligent System"
echo "============================================================"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found."
    exit 1
fi

# Check .env
if [ ! -f ".env" ]; then
    echo "[WARNING] .env not found – copying .env.example"
    cp .env.example .env
    echo "Please edit .env and set GEMINI_API_KEY, then re-run."
    ${EDITOR:-nano} .env
    exit 1
fi

# Virtual env
if [ ! -d "venv" ]; then
    echo "[SETUP] Creating virtual environment..."
    python3 -m venv venv
    echo "[SETUP] Installing dependencies..."
    venv/bin/pip install -r requirements.txt
fi

source venv/bin/activate
echo "[BOOT] Starting J.A.R.V.I.S. ..."
python main.py
