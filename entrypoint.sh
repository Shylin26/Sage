#!/bin/bash
set -e

mkdir -p data

# Restore Gmail OAuth token from environment variable (base64 encoded)
# LEARN: You can't store files in environment variables, so we encode
# the token as base64, store it as an env var, and decode it at startup.
if [ -n "$GMAIL_TOKEN_B64" ]; then
    echo "$GMAIL_TOKEN_B64" | base64 -d > data/token.json
    echo "✓ Gmail token restored"
fi

if [ -n "$CREDENTIALS_B64" ]; then
    echo "$CREDENTIALS_B64" | base64 -d > data/credentials.json
    echo "✓ Gmail credentials restored"
fi

# Initialise the database (creates tables if they don't exist)
python3 -m db.database
echo "✓ Database initialised"

# Start FastAPI with uvicorn
# The APScheduler inside main.py handles the 6 PM cron job automatically
# --host 0.0.0.0 makes it accessible from outside the container
echo "✓ Starting SAGE server..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
