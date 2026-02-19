#!/bin/bash
set -e

cd "$(dirname "$0")"

# Create .env from example if it doesn't exist
if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i '' "s/change-me-to-a-random-32-char-string/$SECRET/" .env
  echo "Created .env with a random SECRET_KEY"
fi

# Create data directories
mkdir -p data/backups/pc data/backups/deck data/keys data/tmp

# Create virtualenv if it doesn't exist
if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# Activate and install dependencies
source .venv/bin/activate
pip install -q -r backend/requirements.txt

echo ""
echo "Starting Enigma Engine → http://localhost:8080"
echo ""

DATA_DIR="$(pwd)/data" \
  DATABASE_URL="sqlite+aiosqlite:///$(pwd)/data/db.sqlite" \
  uvicorn backend.main:app --host 0.0.0.0 --port 8080
