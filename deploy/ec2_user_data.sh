#!/bin/bash
# ==============================================================================
# AWS EC2 / Ubuntu Cloud Bootstrap Script for ICVFX Autonomous Sync Engine
# Paste this into AWS EC2 "Advanced Details > User Data" or run via SSH
# ==============================================================================

set -e
export DEBIAN_FRONTEND=noninteractive

echo "===> [1/5] Updating system packages..."
apt-get update -y && apt-get upgrade -y

echo "===> [2/5] Installing Docker & Docker Compose..."
apt-get install -y ca-certificates curl gnupg lsb-release git

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu || true

echo "===> [3/5] Setting up ICVFX Sync Engine..."
mkdir -p /opt/icvfx-sync-engine
cd /opt/icvfx-sync-engine

# Note: Replace with your repository URL or sync files
if [ ! -f "docker-compose.prod.yml" ]; then
    echo "Directory ready for code deployment."
fi

echo "===> [4/5] Starting services via Docker Compose..."
# If docker-compose.prod.yml is present:
if [ -f "docker-compose.prod.yml" ]; then
    docker compose -f docker-compose.prod.yml up -d --build
fi

echo "===> [5/5] Deployment complete!"
echo "Endpoints:"
echo "  - Mission Control Dashboard: http://$(curl -s http://checkip.amazonaws.com):5173"
echo "  - Grafana Observability:     http://$(curl -s http://checkip.amazonaws.com):3000"
echo "  - Prometheus Metrics:        http://$(curl -s http://checkip.amazonaws.com):9090"
