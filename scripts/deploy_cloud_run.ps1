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
    $AuthRequired = "true"
    $DefaultStorage = "file"
    $CollectionPrefix = "dev_"
} else {
    $Target = "prod"
    $ServiceName = "dienstplan-app"
    $AuthRequired = "true"
    $DefaultStorage = "firestore"
    $CollectionPrefix = ""
}

$ImageName = "${Region}-docker.pkg.dev/${ProjectId}/${Repository}/${ServiceName}:${ImageTag}"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Deploying Dienstplan App to GCP Cloud Run" -ForegroundColor Cyan
Write-Host " Target Mode:   $Target"
Write-Host " Auth Enforced: $AuthRequired"
Write-Host " Storage Mode:  $DefaultStorage"
Write-Host " Project:       $ProjectId"
Write-Host " Region:        $Region"
Write-Host " Service:       $ServiceName"
Write-Host " Image:         $ImageName"
Write-Host "==========================================================" -ForegroundColor Cyan

$StorageBackend = if ($env:STORAGE_BACKEND) { $env:STORAGE_BACKEND } else { $DefaultStorage }
$EnvVars = @(
    "STORAGE_BACKEND=$StorageBackend",
    "AUTH_REQUIRED=$AuthRequired",
    "GOOGLE_CLOUD_PROJECT=$ProjectId",
    "GCP_PROJECT=$ProjectId"
)

if ($CollectionPrefix -ne "") {
    $EnvVars += "FIRESTORE_COLLECTION_PREFIX=$CollectionPrefix"
}
if ($env:FIRESTORE_DATABASE) {
    $EnvVars += "FIRESTORE_DATABASE=$($env:FIRESTORE_DATABASE)"
}

$SessionSecret = if ($env:SESSION_SECRET) { $env:SESSION_SECRET } else { [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N") }
$EnvVars += "SESSION_SECRET=$SessionSecret"
$EffectivePassword = if ($AppPassword -ne "") { $AppPassword } elseif ($env:APP_PASSWORD) { $env:APP_PASSWORD } else { "" }
if ($EffectivePassword -ne "") {
    $hasher = [System.Security.Cryptography.HashAlgorithm]::Create('SHA256')
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($EffectivePassword)
    $hash = [BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace("-", "").ToLower()
    $EnvVars += "PASSWORD_HASH=$hash"
} elseif ($env:PASSWORD_HASH) {
    $EnvVars += "PASSWORD_HASH=$($env:PASSWORD_HASH)"
} elseif ($AuthRequired -eq "true") {
    Write-Error "ERROR: AUTH_REQUIRED is 'true' but neither AppPassword parameter nor PASSWORD_HASH/APP_PASSWORD environment variable is set."
    exit 1
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
    "--min-instances", "1",
    "--max-instances", "1",
    "--set-env-vars", $EnvVarsCsv,
    "--allow-unauthenticated"
)

& gcloud @DeployArgs

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " Deployment Complete!" -ForegroundColor Green
& gcloud run services describe $ServiceName --platform managed --region $Region --project $ProjectId --format 'value(status.url)'
Write-Host "==========================================================" -ForegroundColor Green
