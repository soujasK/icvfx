# Fix IAM permissions for Cloud Build and deploy to Cloud Run
$ErrorActionPreference = "Stop"

$gcloudCmd = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$token = (& $gcloudCmd auth application-default print-access-token).Trim()
$env:CLOUDSDK_AUTH_ACCESS_TOKEN = $token

$ProjectId = "project-b97ea65d-c159-4b52-98d"
$ComputeSA = "414463866226-compute@developer.gserviceaccount.com"
$CloudBuildSA = "414463866226@cloudbuild.gserviceaccount.com"

Write-Host "===> Granting storage and build permissions to service accounts..." -ForegroundColor Yellow

# Grant storage.admin to compute service account so it can read sources
& $gcloudCmd projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$ComputeSA" `
    --role="roles/storage.admin" `
    --condition=None `
    --quiet

# Grant artifactregistry.writer
& $gcloudCmd projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$ComputeSA" `
    --role="roles/artifactregistry.writer" `
    --condition=None `
    --quiet

Write-Host "[+] Permissions updated successfully!" -ForegroundColor Green
