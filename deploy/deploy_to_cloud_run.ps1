# ==============================================================================
# 1-Command Serverless Google Cloud Run Deployer (PowerShell)
# Deploys ICVFX Autonomous Stage Sync Engine & Dashboard to Google Cloud Run
# Scales to zero when idle (₹0.00 / hour cost when not in use)
# ==============================================================================

param(
    [string]$ProjectId = "project-b97ea65d-c159-4b52-98d",
    [string]$Region = "us-central1",
    [string]$ServiceName = "icvfx-sync-engine"
)

$ErrorActionPreference = "Stop"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  DEPLOYING SERVERLESS ICVFX ENGINE TO GOOGLE CLOUD RUN" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "[*] GCP Project:       $ProjectId"
Write-Host "[*] Cloud Region:      $Region"
Write-Host "[*] Service Name:      $ServiceName"
Write-Host "[*] Auto-Scaling:      min=0 (scale-to-zero), max=2"
Write-Host "[*] Idle Cost:         ₹0.00 / hour (Event-Driven Serverless)"
Write-Host "-----------------------------------------------------------------"

# Automatically attach ADC token for seamless auth
$gcloudCmd = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$token = (& $gcloudCmd auth application-default print-access-token).Trim()
$env:CLOUDSDK_AUTH_ACCESS_TOKEN = $token

# Step 1: Ensure frontend is built
Write-Host "===> [1/2] Verifying frontend production bundle..." -ForegroundColor Yellow
if (Test-Path "dashboard/dist") {
    Write-Host "[+] Frontend build found in dashboard/dist" -ForegroundColor Green
} else {
    Write-Host "[*] Building frontend..."
    Set-Location dashboard
    npm run build
    Set-Location ..
}

# Step 2: Deploy to Cloud Run
Write-Host "===> [2/2] Deploying container to Google Cloud Run (Building via Cloud Build)..." -ForegroundColor Yellow

$grafanaKey = if ($env:GRAFANA_CLOUD_API_KEY) { $env:GRAFANA_CLOUD_API_KEY } else { "YOUR_GRAFANA_CLOUD_API_KEY" }
$envVars = "GEMINI_BACKEND=vertex,GOOGLE_CLOUD_PROJECT=$ProjectId,GOOGLE_CLOUD_LOCATION=$Region,GEMINI_MODEL=gemini-2.5-flash,GRAFANA_CLOUD_REMOTE_WRITE_URL=https://prometheus-prod-43-prod-ap-south-1.grafana.net/api/prom/push,GRAFANA_CLOUD_USER=3572064,GRAFANA_CLOUD_API_KEY=$grafanaKey"

& $gcloudCmd run deploy "$ServiceName" `
  --project="$ProjectId" `
  --region="$Region" `
  --source="." `
  --min-instances=0 `
  --max-instances=2 `
  --memory="2Gi" `
  --cpu="2" `
  --allow-unauthenticated `
  --set-env-vars="$envVars" `
  --quiet

$url = (& $gcloudCmd run services describe "$ServiceName" --project="$ProjectId" --region="$Region" --format='value(status.url)').Trim()

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Green
Write-Host "  🎉 SERVERLESS DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Green
Write-Host "Live Public URL: $url" -ForegroundColor Cyan
Write-Host ""
Write-Host "Features Active:"
Write-Host "  • Serverless Event-Driven compute (scales down to 0 instances)"
Write-Host "  • Zero credit burn when idle (₹0.00/hour)"
Write-Host "  • Direct Vertex AI multimodal incident arbiter (Gemini 2.5 Flash)"
Write-Host "  • Live Grafana Cloud Telemetry Gateway (nimblespruce925)"
Write-Host "================================================================="
