#!/bin/bash
# ==============================================================================
# 1-Command GCP Compute Engine VM Deployer
# Usage: ./deploy/deploy_to_gcp.sh <GCP_PROJECT_ID> [ZONE]
# Example: ./deploy/deploy_to_gcp.sh my-first-project-12345 asia-south1-a
# ==============================================================================

set -e

PROJECT_ID="$1"
ZONE="${2:-asia-south1-a}"
INSTANCE_NAME="icvfx-engine-vm"

if [ -z "$PROJECT_ID" ]; then
    echo "Usage: $0 <GCP_PROJECT_ID> [ZONE]"
    echo "Example: $0 my-first-project-12345 asia-south1-a"
    exit 1
fi

echo "===> [1/4] Setting GCP project to: $PROJECT_ID (Zone: $ZONE)..."
gcloud config set project "$PROJECT_ID"

echo "===> [2/4] Creating Firewall Rule for ICVFX Stage Ports..."
gcloud compute firewall-rules create allow-icvfx-ports \
  --allow=tcp:5173,tcp:3000,tcp:9090,tcp:8080,udp:5005 \
  --target-tags=icvfx-ports \
  --description="Allow ICVFX Dashboard, Grafana, and UDP Tracking Ingest" || true

echo "===> [3/4] Creating e2-standard-4 VM Instance (Billed against your ₹28,000 INR credits)..."
gcloud compute instances create "$INSTANCE_NAME" \
  --zone="$ZONE" \
  --machine-type="e2-standard-4" \
  --image-family="ubuntu-2204-lts" \
  --image-project="ubuntu-os-cloud" \
  --boot-disk-size="30GB" \
  --tags="http-server,https-server,icvfx-ports" \
  --metadata-from-file=startup-script=deploy/gcp_startup_script.sh

echo "===> [4/4] Getting Public IP of your new GCP VM..."
PUBLIC_IP=$(gcloud compute instances describe "$INSTANCE_NAME" --zone="$ZONE" --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo ""
echo "================================================================="
echo "  GCP COMPUTE ENGINE VM IS LIVE!"
echo "================================================================="
echo "Public IP: $PUBLIC_IP"
echo ""
echo "To sync your code and launch containers:"
echo "  gcloud compute scp --recurse . $INSTANCE_NAME:/opt/icvfx-sync-engine --zone=$ZONE"
echo "  gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command=\"cd /opt/icvfx-sync-engine && docker compose -f docker-compose.prod.yml up -d --build\""
echo ""
echo "Access URLs:"
echo "  - Mission Control UI: http://$PUBLIC_IP:5173"
echo "  - Grafana Portal:     http://$PUBLIC_IP:3000"
echo "  - Prometheus API:     http://$PUBLIC_IP:9090"
echo "================================================================="
