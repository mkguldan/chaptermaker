# Video Chapter Maker - GCP Setup Script for Windows
# This script automates the GCP setup process

$ErrorActionPreference = "Stop"

Write-Host "🎬 Video Chapter Maker - GCP Setup Script" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Configuration
$PROJECT_ID = "ai-mvp-452812"
$REGION = "us-central1"
$SERVICE_ACCOUNT_NAME = "chaptermaker-service"

Write-Host "`nUsing existing project: $PROJECT_ID" -ForegroundColor Green

# Check prerequisites
Write-Host "`nChecking prerequisites..." -ForegroundColor Yellow
try {
    $gcloudVersion = gcloud version --format=json | ConvertFrom-Json
    Write-Host "✓ Google Cloud SDK is installed" -ForegroundColor Green
} catch {
    Write-Host "Error: gcloud CLI is not installed." -ForegroundColor Red
    Write-Host "Please install Google Cloud SDK: https://cloud.google.com/sdk/docs/install" -ForegroundColor Yellow
    exit 1
}

# Check if user is logged in
$activeAccount = gcloud auth list --filter=status:ACTIVE --format="value(account)"
if (-not $activeAccount) {
    Write-Host "Please login to Google Cloud:" -ForegroundColor Yellow
    gcloud auth login
}

# Set current project
Write-Host "`nSetting current project to $PROJECT_ID..." -ForegroundColor Yellow
gcloud config set project $PROJECT_ID

# Enable billing reminder
Write-Host "`n⚠️  Please ensure billing is enabled for project $PROJECT_ID" -ForegroundColor Yellow
Write-Host "Visit: https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID" -ForegroundColor Yellow
Read-Host "Press Enter when billing is enabled"

# Enable required APIs
Write-Host "`nEnabling required APIs..." -ForegroundColor Yellow
$apis = @(
    "compute.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudtasks.googleapis.com",
    "storage-component.googleapis.com"
)

foreach ($api in $apis) {
    Write-Host "Enabling $api..." -ForegroundColor Gray
    gcloud services enable $api --quiet
}

# Create service account
Write-Host "`nCreating service account..." -ForegroundColor Yellow
$serviceAccountEmail = "$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

try {
    gcloud iam service-accounts describe $serviceAccountEmail | Out-Null
    Write-Host "✓ Service account already exists" -ForegroundColor Green
} catch {
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME `
        --display-name="Chapter Maker Service Account"
    Write-Host "✓ Service account created" -ForegroundColor Green
}

# Grant IAM roles
Write-Host "`nGranting IAM permissions..." -ForegroundColor Yellow
$roles = @(
    "roles/storage.admin",
    "roles/cloudtasks.enqueuer",
    "roles/run.invoker",
    "roles/artifactregistry.writer"
)

foreach ($role in $roles) {
    Write-Host "Granting $role..." -ForegroundColor Gray
    gcloud projects add-iam-policy-binding $PROJECT_ID `
        --member="serviceAccount:$serviceAccountEmail" `
        --role="$role" `
        --quiet | Out-Null
}

# Create Cloud Storage buckets
Write-Host "`nCreating Cloud Storage buckets..." -ForegroundColor Yellow
$buckets = @(
    "chaptermaker-uploads",
    "chaptermaker-outputs"
)

foreach ($bucket in $buckets) {
    $bucketName = "gs://$bucket-$PROJECT_ID"
    try {
        gsutil ls -b $bucketName | Out-Null
        Write-Host "✓ Bucket $bucket-$PROJECT_ID already exists" -ForegroundColor Green
    } catch {
        Write-Host "Creating bucket $bucket-$PROJECT_ID..." -ForegroundColor Gray
        gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION $bucketName
        
        # Set bucket permissions
        gsutil iam ch "serviceAccount:${serviceAccountEmail}:objectAdmin" $bucketName
        Write-Host "✓ Bucket created" -ForegroundColor Green
    }
}

# Create Artifact Registry repository
Write-Host "`nCreating Artifact Registry repository..." -ForegroundColor Yellow
try {
    gcloud artifacts repositories describe chaptermaker-repo --location=$REGION | Out-Null
    Write-Host "✓ Artifact Registry repository already exists" -ForegroundColor Green
} catch {
    gcloud artifacts repositories create chaptermaker-repo `
        --repository-format=docker `
        --location=$REGION `
        --description="Docker repository for Chapter Maker"
    Write-Host "✓ Repository created" -ForegroundColor Green
}

# Create Cloud Tasks queue
Write-Host "`nCreating Cloud Tasks queue..." -ForegroundColor Yellow
try {
    gcloud tasks queues describe video-processing --location=$REGION | Out-Null
    Write-Host "✓ Cloud Tasks queue already exists" -ForegroundColor Green
} catch {
    gcloud tasks queues create video-processing `
        --location=$REGION `
        --max-concurrent-dispatches=10 `
        --max-attempts=3
    Write-Host "✓ Queue created" -ForegroundColor Green
}

# Download service account key
Write-Host "`nCreating service account key..." -ForegroundColor Yellow
$keyFile = "service-account-key.json"
$keyPath = Join-Path (Get-Location) $keyFile

if (Test-Path $keyPath) {
    Write-Host "Service account key already exists. Skipping..." -ForegroundColor Yellow
} else {
    gcloud iam service-accounts keys create $keyFile `
        --iam-account=$serviceAccountEmail
    Write-Host "✓ Service account key saved to $keyFile" -ForegroundColor Green
}

# Create .env file
Write-Host "`nCreating .env file..." -ForegroundColor Yellow
$envPath = Join-Path (Get-Location) ".env"
$envExamplePath = Join-Path (Get-Location) ".env.example"

$envContent = @"
# OpenAI
OPENAI_API_KEY=your-openai-api-key

# Google Cloud
GCP_PROJECT_ID=$PROJECT_ID
GCP_REGION=$REGION
GCS_UPLOAD_BUCKET=chaptermaker-uploads-$PROJECT_ID
GCS_OUTPUT_BUCKET=chaptermaker-outputs-$PROJECT_ID
GOOGLE_APPLICATION_CREDENTIALS=service-account-key.json

# Cloud Run URLs (will be updated after deployment)
API_URL=https://chaptermaker-api-HASH-$REGION.run.app
FRONTEND_URL=https://chaptermaker-web-HASH-$REGION.run.app

# Cloud Tasks
CLOUD_TASKS_QUEUE=video-processing
CLOUD_TASKS_LOCATION=$REGION

# Application
APP_ENV=production
"@

if (Test-Path $envPath) {
    Write-Host ".env file already exists. Creating .env.example instead..." -ForegroundColor Yellow
    Set-Content -Path $envExamplePath -Value $envContent
} else {
    Set-Content -Path $envPath -Value $envContent
    Write-Host "✓ .env file created" -ForegroundColor Green
}

# Configure Docker authentication
Write-Host "`nConfiguring Docker authentication for Artifact Registry..." -ForegroundColor Yellow
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

# Summary
Write-Host "`n✅ GCP setup completed successfully!" -ForegroundColor Green
Write-Host "`nProject ID: $PROJECT_ID" -ForegroundColor Cyan
Write-Host "Region: $REGION" -ForegroundColor Cyan
Write-Host "Service Account: $serviceAccountEmail" -ForegroundColor Cyan

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. Update the OPENAI_API_KEY in .env"
Write-Host "2. Add the service account key to GitHub secrets (base64 encoded):"
Write-Host "   [Convert]::ToBase64String([IO.File]::ReadAllBytes('$keyFile'))"
Write-Host "3. Run 'docker-compose up' to start local development"
Write-Host "4. Push to GitHub to trigger automatic deployment"

Write-Host "`nHappy coding! 🚀" -ForegroundColor Green
