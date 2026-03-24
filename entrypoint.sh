#!/bin/bash
set -e

mkdir -p data

if [ -n "$GMAIL_TOKEN_B64" ]; then
    echo "$GMAIL_TOKEN_B64" | base64 -d > data/token.json
    echo "✓ Gmail token restored"
fi

if [ -n "$CREDENTIALS_B64" ]; then
    echo "$CREDENTIALS_B64" | base64 -d > data/credentials.json
    echo "✓ Gmail credentials restored"
fi

python3 -m db.database
python3 run_briefing.py &

SAGE_DB_PATH=data/sage.db ./server/sage-server
