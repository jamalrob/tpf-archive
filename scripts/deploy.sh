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

# Fix permissions FIRST so rsync can write
ssh -t ${DEPLOY_USER}@${DEPLOY_HOST} "
    echo 'Preparing directory for rsync...'
    sudo chown -R ${DEPLOY_USER}:${DEPLOY_USER} ${DEPLOY_PATH} && echo '✓ Ownership set to ${DEPLOY_USER} for rsync'
    sudo chmod -R 755 ${DEPLOY_PATH} && echo '✓ Write permissions enabled'
"

# Deploy files (now rsync can write)
rsync -rlDzv --no-owner --no-group --no-times build/static_archive/ ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}

# Fix permissions back to secure web serving
ssh -t ${DEPLOY_USER}@${DEPLOY_HOST} "
    echo 'Securing permissions for web serving...'
    sudo chown -R www-data:www-data ${DEPLOY_PATH} && echo '✓ Ownership set to www-data'
    sudo chmod -R 755 ${DEPLOY_PATH} && echo '✓ Directory permissions secured'
    sudo find ${DEPLOY_PATH} -type f -exec chmod 644 {} \; && echo '✓ File permissions secured'
    echo 'Permission fix complete!'
"

echo "✅ Deployment complete!"