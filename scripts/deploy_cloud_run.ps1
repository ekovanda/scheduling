# Deploy Dienstplan Generator to Google Cloud Run (Windows PowerShell)
param (
    [switch]$Dev,
    [switch]$Prod,
    [string]$ProjectId = "tierklinik-trillig",
    [string]$Region = "europe-west3",
    [string]$Repository = "dienstplan-repo",
    [string]$ImageTag = "latest",
    [string]$AppPassword = ""
)

$ErrorActionPreference = "Stop"

if ($Dev) {
    $Target = "dev"
    $ServiceName = "dienstplan-dev"
    $AppTarget = "fastapi"
} else {
    $Target = "prod"
    $ServiceName = "dienstplan-app"
    $AppTarget = "streamlit"
}

$ImageName = "${Region}-docker.pkg.dev/${ProjectId}/${Repository}/${ServiceName}:${ImageTag}"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Deploying Dienstplan App to GCP Cloud Run" -ForegroundColor Cyan
Write-Host " Target Mode: $Target (APP_TARGET=$AppTarget)"
Write-Host " Project:     $ProjectId"
Write-Host " Region:      $Region"
Write-Host " Service:     $ServiceName"
Write-Host " Image:       $ImageName"
Write-Host "==========================================================" -ForegroundColor Cyan

$StorageBackend = if ($env:STORAGE_BACKEND) { $env:STORAGE_BACKEND } else { "firestore" }
$EnvVars = @("APP_TARGET=$AppTarget", "STORAGE_BACKEND=$StorageBackend")
if ($AppPassword -ne "") {
    $hasher = [System.Security.Cryptography.HashAlgorithm]::Create('SHA256')
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($AppPassword)
    $hash = [BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace("-", "").ToLower()
    $EnvVars += "PASSWORD_HASH=$hash"
}
$EnvVarsCsv = $EnvVars -join ","

Write-Host "Submitting build to Google Cloud Build (native linux/amd64)..."
gcloud builds submit --tag $ImageName --project $ProjectId .

Write-Host "Deploying to Cloud Run..."
$DeployArgs = @(
    "run", "deploy", $ServiceName,
    "--image", $ImageName,
    "--platform", "managed",
    "--region", $Region,
    "--project", $ProjectId,
    "--cpu", "2",
    "--memory", "4Gi",
    "--no-cpu-throttling",
    "--timeout", "900s",
    "--concurrency", "2",
    "--session-affinity",
    "--min-instances", "0",
    "--max-instances", "3",
    "--set-env-vars", $EnvVarsCsv,
    "--allow-unauthenticated"
)

& gcloud @DeployArgs

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " Deployment Complete!" -ForegroundColor Green
& gcloud run services describe $ServiceName --platform managed --region $Region --project $ProjectId --format 'value(status.url)'
Write-Host "==========================================================" -ForegroundColor Green
