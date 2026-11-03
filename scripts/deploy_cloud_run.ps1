# Deploy Dienstplan Generator to Google Cloud Run (Windows PowerShell)
param (
    [string]$ProjectId = "tierklinik-trillig",
    [string]$Region = "europe-west3",
    [string]$Repository = "dienstplan-repo",
    [string]$ServiceName = "dienstplan-app",
    [string]$ImageTag = "latest",
    [string]$AppPassword = ""
)

$ErrorActionPreference = "Stop"

$ImageName = "${Region}-docker.pkg.dev/${ProjectId}/${Repository}/${ServiceName}:${ImageTag}"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Deploying Dienstplan App to GCP Cloud Run" -ForegroundColor Cyan
Write-Host " Project:    $ProjectId"
Write-Host " Region:     $Region"
Write-Host " Service:    $ServiceName"
Write-Host " Image:      $ImageName"
Write-Host "==========================================================" -ForegroundColor Cyan

# Compute SHA256 if password provided
$EnvVarArg = @()
if ($AppPassword -ne "") {
    $hasher = [System.Security.Cryptography.HashAlgorithm]::Create('SHA256')
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($AppPassword)
    $hash = [BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace("-", "").ToLower()
    $EnvVarArg = @("--set-env-vars", "PASSWORD_HASH=$hash")
}

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
    "--memory", "2Gi",
    "--timeout", "300s",
    "--concurrency", "10",
    "--session-affinity",
    "--min-instances", "0",
    "--max-instances", "3",
    "--allow-unauthenticated"
) + $EnvVarArg

& gcloud @DeployArgs

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " Deployment Complete!" -ForegroundColor Green
& gcloud run services describe $ServiceName --platform managed --region $Region --project $ProjectId --format 'value(status.url)'
Write-Host "==========================================================" -ForegroundColor Green

