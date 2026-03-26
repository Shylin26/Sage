#!/bin/bash
set -e

mkdir -p data

if [ -n "$GMAIL_TOKEN_B64" ]; then
    echo "$GMAIL_TOKEN_B64" | base64 -d > data/token.json 2>/dev/null && echo "✓ Gmail token restored" || echo "⚠ Gmail token decode failed — skipping"
fi

if [ -n "$CREDENTIALS_B64" ]; then
    echo "$CREDENTIALS_B64" | base64 -d > data/credentials.json 2>/dev/null && echo "✓ Gmail credentials restored" || echo "⚠ Gmail credentials decode failed — skipping"
fi

python3 -m db.database
echo "✓ Database initialised"

echo "✓ Starting SAGE server..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
