# PowerShell script to set up GCS lifecycle policies for automatic deletion after 24 hours

$PROJECT_ID = if ($env:GCP_PROJECT_ID) { $env:GCP_PROJECT_ID } else { "ai-mvp-452812" }
$UPLOAD_BUCKET = "chaptermaker-uploads-$PROJECT_ID"
$OUTPUT_BUCKET = "chaptermaker-outputs-$PROJECT_ID"

Write-Host "Setting up GCS lifecycle policies for automatic cleanup..." -ForegroundColor Cyan
Write-Host "Project: $PROJECT_ID"
Write-Host ""

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
# Use UTF8 without BOM for gsutil compatibility
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($tempFile, $lifecycleConfig, $utf8NoBom)

Write-Host "Configuring upload bucket: $UPLOAD_BUCKET" -ForegroundColor Yellow
gsutil lifecycle set $tempFile "gs://$UPLOAD_BUCKET/"
if ($LASTEXITCODE -eq 0) {
    Write-Host "Upload bucket configured" -ForegroundColor Green
} else {
    Write-Host "Warning: Could not configure upload bucket" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Configuring output bucket: $OUTPUT_BUCKET" -ForegroundColor Yellow
gsutil lifecycle set $tempFile "gs://$OUTPUT_BUCKET/"
if ($LASTEXITCODE -eq 0) {
    Write-Host "Output bucket configured" -ForegroundColor Green
} else {
    Write-Host "Warning: Could not configure output bucket" -ForegroundColor Yellow
}

# Clean up
Remove-Item -Path $tempFile -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Lifecycle policies configured!" -ForegroundColor Green
Write-Host "Files will be automatically deleted after 24 hours"
Write-Host ""
Write-Host "To verify:" -ForegroundColor Cyan
Write-Host "  gsutil lifecycle get gs://$UPLOAD_BUCKET/"
Write-Host "  gsutil lifecycle get gs://$OUTPUT_BUCKET/"
