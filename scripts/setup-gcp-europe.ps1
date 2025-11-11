# GCP Setup Script for Windows (Europe Region)
# Run this script to set up Google Cloud resources for ChapterMaker

$PROJECT_ID = "ai-mvp-452812"
$REGION = "europe-west1"
$SERVICE_ACCOUNT = "chaptermaker-service@$PROJECT_ID.iam.gserviceaccount.com"

Write-Host "Setting up GCP resources for ChapterMaker in Europe..." -ForegroundColor Green

# Authenticate and set project
Write-Host "`n1. Authenticating to GCP..." -ForegroundColor Yellow
gcloud auth login
gcloud config set project $PROJECT_ID

# Enable required APIs
Write-Host "`n2. Enabling required APIs..." -ForegroundColor Yellow
gcloud services enable artifactregistry.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudtasks.googleapis.com
gcloud services enable secretmanager.googleapis.com

# Create Artifact Registry repository in Europe
Write-Host "`n3. Creating Artifact Registry repository in Europe..." -ForegroundColor Yellow
gcloud artifacts repositories create chaptermaker-repo `
    --repository-format=docker `
    --location=$REGION `
    --description="Docker repository for ChapterMaker"

# Create GCS buckets in Europe
Write-Host "`n4. Creating GCS buckets in Europe..." -ForegroundColor Yellow
gsutil mb -p $PROJECT_ID -l $REGION -c STANDARD gs://chaptermaker-uploads-$PROJECT_ID
gsutil mb -p $PROJECT_ID -l $REGION -c STANDARD gs://chaptermaker-outputs-$PROJECT_ID

# Set CORS on buckets
Write-Host "`n5. Setting CORS configuration..." -ForegroundColor Yellow
$corsConfig = '[{"origin": ["*"], "method": ["GET", "HEAD", "PUT", "POST", "DELETE"], "responseHeader": ["Content-Type"], "maxAgeSeconds": 3600}]'
$corsConfig | Out-File -FilePath cors-config.json -Encoding ascii
gsutil cors set cors-config.json gs://chaptermaker-uploads-$PROJECT_ID
gsutil cors set cors-config.json gs://chaptermaker-outputs-$PROJECT_ID
Remove-Item cors-config.json

# Create Cloud Tasks queue in Europe
Write-Host "`n6. Creating Cloud Tasks queue in Europe..." -ForegroundColor Yellow
gcloud tasks queues create video-processing --location=$REGION

# Grant permissions
Write-Host "`n7. Granting permissions..." -ForegroundColor Yellow
gcloud artifacts repositories add-iam-policy-binding chaptermaker-repo `
    --location=$REGION `
    --member="serviceAccount:$SERVICE_ACCOUNT" `
    --role="roles/artifactregistry.writer"

gcloud iam service-accounts add-iam-policy-binding `
    695406125250-compute@developer.gserviceaccount.com `
    --member="serviceAccount:$SERVICE_ACCOUNT" `
    --role="roles/iam.serviceAccountUser" `
    --project=$PROJECT_ID

# Grant Secret Manager access
$COMPUTE_SA = (gcloud projects describe $PROJECT_ID --format="value(projectNumber)")-replace "`r`n", ""
$COMPUTE_SA = "$COMPUTE_SA-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member="serviceAccount:$COMPUTE_SA" `
    --role="roles/secretmanager.secretAccessor"

Write-Host "`n✅ GCP setup complete!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Add OPENAI_API_KEY to Secret Manager"
Write-Host "2. Add GCP_SERVICE_ACCOUNT_KEY to GitHub secrets"
Write-Host "3. Push to main branch to trigger deployment"

