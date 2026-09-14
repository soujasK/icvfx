$gcloudCmd = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$token = (& $gcloudCmd auth application-default print-access-token).Trim()
$env:CLOUDSDK_AUTH_ACCESS_TOKEN = $token

& $gcloudCmd logging read "resource.type=cloud_run_revision AND resource.labels.service_name=icvfx-sync-engine" --project="project-b97ea65d-c159-4b52-98d" --limit=60 --format="value(textPayload)"
