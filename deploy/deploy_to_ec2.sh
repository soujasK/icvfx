#!/bin/bash
# ==============================================================================
# 1-Command Local -> EC2 Deployer
# Usage: ./deploy/deploy_to_ec2.sh <EC2_USER>@<EC2_PUBLIC_IP> <PATH_TO_PEM_KEY>
# Example: ./deploy/deploy_to_ec2.sh ubuntu@54.210.12.34 ~/.ssh/my-key.pem
# ==============================================================================

set -e

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <USER@EC2_IP> <PEM_KEY_PATH>"
    echo "Example: $0 ubuntu@54.210.12.34 ~/.ssh/my-key.pem"
    exit 1
fi

EC2_HOST="$1"
KEY_PATH="$2"
REMOTE_DIR="/home/ubuntu/icvfx-sync-engine"

echo "[1/4] Syncing project files to EC2 ($EC2_HOST)..."
rsync -avz --exclude 'node_modules' --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  -e "ssh -i $KEY_PATH -o StrictHostKeyChecking=no" \
  ./ "$EC2_HOST:$REMOTE_DIR"

echo "[2/4] Building and launching containers on EC2..."
ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no "$EC2_HOST" << 'EOF'
  cd /home/ubuntu/icvfx-sync-engine
  docker compose -f docker-compose.prod.yml down || true
  docker compose -f docker-compose.prod.yml up -d --build
EOF

echo "[3/4] Checking running containers..."
ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no "$EC2_HOST" "docker ps"

echo "[4/4] Deployment successful!"
echo "Open in your browser:"
echo "  - Mission Control: http://${EC2_HOST#*@}:5173"
echo "  - Grafana:         http://${EC2_HOST#*@}:3000"
