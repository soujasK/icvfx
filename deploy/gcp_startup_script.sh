#!/bin/bash
# ==============================================================================
# Google Cloud Platform (GCP) Compute Engine Startup Script
# Automatically provisions Docker, Docker Compose, and starts ICVFX Sync Engine
# Uses your ₹28,000 INR GCP Free Trial Credits!
# ==============================================================================

set -e
export DEBIAN_FRONTEND=noninteractive

echo "===> [1/4] Installing Docker and system dependencies on GCP VM..."
apt-get update -y
apt-get install -y ca-certificates curl gnupg git

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker

echo "===> [2/4] Setting up directory..."
mkdir -p /opt/icvfx-sync-engine
cd /opt/icvfx-sync-engine

echo "===> [3/4] Ready for project containers..."
if [ -f "docker-compose.prod.yml" ]; then
    docker compose -f docker-compose.prod.yml up -d --build
fi

echo "===> [4/4] GCP VM Bootstrap completed!"
