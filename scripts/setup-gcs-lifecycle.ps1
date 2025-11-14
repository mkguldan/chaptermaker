# PowerShell script to set up GCS lifecycle policies for automatic deletion after 24 hours
# Run this once to configure the buckets

$ErrorActionPreference = "Stop"

# Get project ID
$PROJECT_ID = if ($env:GCP_PROJECT_ID) { $env:GCP_PROJECT_ID } else { "ai-mvp-452812" }
$REGION = "europe-west1"

Write-Host "🗑️  Setting up GCS lifecycle policies for automatic cleanup..." -ForegroundColor Cyan
Write-Host "Project: $PROJECT_ID"
Write-Host "Region: $REGION"
Write-Host ""

# Bucket names
$UPLOAD_BUCKET = "chaptermaker-uploads-$PROJECT_ID"
$OUTPUT_BUCKET = "chaptermaker-outputs-$PROJECT_ID"

# Create lifecycle configuration JSON
$lifecycleConfig = @"
{
  "lifecycle": {
    "rule": [
      {
        "action": {
          "type": "Delete"
        },
        "condition": {
          "age": 1,
          "matchesPrefix": ["uploads/", "outputs/", "job-tracking/"]
        }
      }
    ]
  }
}
"@

$tempFile = [System.IO.Path]::GetTempFileName()
$lifecycleConfig | Out-File -FilePath $tempFile -Encoding UTF8

try {
    Write-Host "📦 Configuring lifecycle policy for upload bucket: $UPLOAD_BUCKET" -ForegroundColor Yellow
    try {
        gsutil lifecycle set $tempFile "gs://$UPLOAD_BUCKET/"
        Write-Host "✓ Upload bucket configured" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  Warning: Could not set lifecycle on upload bucket. It may not exist yet." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "📦 Configuring lifecycle policy for output bucket: $OUTPUT_BUCKET" -ForegroundColor Yellow
    try {
        gsutil lifecycle set $tempFile "gs://$OUTPUT_BUCKET/"
        Write-Host "✓ Output bucket configured" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  Warning: Could not set lifecycle on output bucket. It may not exist yet." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "✅ Lifecycle policies configured successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📋 Policy Summary:" -ForegroundColor Cyan
    Write-Host "  - Files older than 1 day (24 hours) will be automatically deleted"
    Write-Host "  - Applies to: uploads/, outputs/, job-tracking/ prefixes"
    Write-Host "  - Deletion happens once per day (not exactly at 24h, but within 24-48h)"
    Write-Host ""
    Write-Host "🔍 To verify the configuration, run:" -ForegroundColor Cyan
    Write-Host "  gsutil lifecycle get gs://$UPLOAD_BUCKET/"
    Write-Host "  gsutil lifecycle get gs://$OUTPUT_BUCKET/"
} finally {
    # Clean up temp file
    Remove-Item -Path $tempFile -ErrorAction SilentlyContinue
}

