#!/bin/bash
# ==============================================================================
# 1-Command Serverless Google Cloud Run Deployer
# Deploys ICVFX Autonomous Stage Sync Engine & Dashboard to Google Cloud Run
# Scales to zero when idle (₹0.00 / hour cost when not in use)
# ==============================================================================

set -e

PROJECT_ID="${1:-project-b97ea65d-c159-4b52-98d}"
REGION="${2:-us-central1}"
SERVICE_NAME="icvfx-sync-engine"

echo "================================================================="
echo "  DEPLOYING SERVERLESS ICVFX ENGINE TO GOOGLE CLOUD RUN"
echo "================================================================="
echo "[*] GCP Project:       $PROJECT_ID"
echo "[*] Cloud Region:      $REGION"
echo "[*] Service Name:      $SERVICE_NAME"
echo "[*] Auto-Scaling:      min=0 (scale-to-zero), max=2"
echo "[*] Idle Cost:         ₹0.00 / hour (Event-Driven Serverless)"
echo "-----------------------------------------------------------------"

echo "===> [1/2] Building frontend production bundle..."
if [ -d "dashboard" ]; then
  (cd dashboard && npm run build)
fi

echo "===> [2/2] Deploying container to Google Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source="." \
  --min-instances=0 \
  --max-instances=2 \
  --memory="2Gi" \
  --cpu="2" \
  --allow-unauthenticated \
  --set-env-vars="GEMINI_BACKEND=vertex,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION,GEMINI_MODEL=gemini-2.5-flash,GRAFANA_CLOUD_REMOTE_WRITE_URL=https://prometheus-prod-43-prod-ap-south-1.grafana.net/api/prom/push,GRAFANA_CLOUD_USER=3572064,GRAFANA_CLOUD_API_KEY=${GRAFANA_CLOUD_API_KEY:-YOUR_GRAFANA_CLOUD_API_KEY}"

URL=$(gcloud run services describe "$SERVICE_NAME" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')

echo ""
echo "================================================================="
echo "  🎉 SERVERLESS DEPLOYMENT SUCCESSFUL!"
echo "================================================================="
echo "Live Public URL: $URL"
echo ""
echo "Features Active:"
echo "  • Serverless Event-Driven compute (scales down to 0 instances)"
echo "  • Zero credit burn when idle (₹0.00/hour)"
echo "  • Direct Vertex AI multimodal incident arbiter (Gemini 2.5 Flash)"
echo "  • Live Grafana Cloud Telemetry Gateway (nimblespruce925)"
echo "================================================================="
