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

# Create host-side data directories
mkdir -p data/backups/pc data/backups/deck data/keys data/tmp data/staging

echo ""
echo "Starting Enigma Engine → http://localhost:8080"
echo ""

docker compose up --build "$@"
