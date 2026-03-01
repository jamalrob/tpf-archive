#!/bin/bash
cd "$(dirname "$0")/.."

# Load environment variables
if [ -f .env ]; then
    source .env
else
    echo "❌ Error: .env file not found"
    echo "Please create .env file with DEPLOY_USER, DEPLOY_HOST, and DEPLOY_PATH"
    exit 1
fi

# Validate required environment variables
if [ -z "$DEPLOY_USER" ] || [ -z "$DEPLOY_HOST" ] || [ -z "$DEPLOY_PATH" ]; then
    echo "❌ Error: Missing required environment variables in .env file"
    echo "Required: DEPLOY_USER, DEPLOY_HOST, DEPLOY_PATH"
    exit 1
fi

echo "🚀 Starting deployment to $DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_PATH"

rsync -rlDzv --no-owner --no-group --no-times --chmod=D775,F664 build/static_archive/ ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}

echo "✅ Deployment complete!"