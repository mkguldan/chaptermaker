# GCS Lifecycle Policy Setup

This directory contains scripts to configure automatic deletion of old files in Google Cloud Storage buckets.

## What It Does

Configures GCS lifecycle policies to automatically delete files after **24 hours** from:
- `uploads/` folder (user uploaded videos and presentations)
- `outputs/` folder (generated chapters, subtitles, transcripts, slides)
- `job-tracking/` folder (job status files)

## Why 24 Hours?

- **Cost savings**: Reduces GCS storage costs by automatically cleaning up old files
- **Data privacy**: User uploads and results are automatically removed
- **No manual cleanup**: GCS handles deletion automatically

## Important Notes

⚠️ **Deletion timing**: GCS lifecycle policies run once per day, so files may exist for 24-48 hours before deletion.

⚠️ **No recovery**: Once deleted, files cannot be recovered. Users should download their results promptly.

✅ **Recommended**: Add a notice in your frontend that files are available for 24 hours only.

## How to Run

### Option 1: PowerShell (Windows)

```powershell
cd "D:\Praca\IR\2025\AI MVP\Python projects\chaptermaker"
.\scripts\setup-gcs-lifecycle.ps1
```

### Option 2: Bash (Linux/Mac)

```bash
cd "/path/to/chaptermaker"
chmod +x scripts/setup-gcs-lifecycle.sh
./scripts/setup-gcs-lifecycle.sh
```

### Option 3: Using gcloud CLI directly

```bash
# Set project
gcloud config set project ai-mvp-452812

# Create lifecycle config file
cat > lifecycle.json << 'EOF'
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
EOF

# Apply to buckets
gsutil lifecycle set lifecycle.json gs://chaptermaker-uploads-ai-mvp-452812/
gsutil lifecycle set lifecycle.json gs://chaptermaker-outputs-ai-mvp-452812/
```

## Verify Configuration

Check if lifecycle policies are active:

```bash
# Check upload bucket
gsutil lifecycle get gs://chaptermaker-uploads-ai-mvp-452812/

# Check output bucket
gsutil lifecycle get gs://chaptermaker-outputs-ai-mvp-452812/
```

## Modify Retention Period

To change from 24 hours to a different period, edit the `"age"` value in the JSON:

- `"age": 1` = 1 day (24 hours)
- `"age": 2` = 2 days (48 hours)
- `"age": 7` = 7 days (1 week)

Then re-run the setup script.

## Remove Lifecycle Policy

To disable automatic deletion:

```bash
gsutil lifecycle set /dev/null gs://chaptermaker-uploads-ai-mvp-452812/
gsutil lifecycle set /dev/null gs://chaptermaker-outputs-ai-mvp-452812/
```

## Frontend Notice Example

Add this to your frontend to inform users:

```jsx
<div className="text-sm text-yellow-600 bg-yellow-50 p-3 rounded-md">
  ⏰ Files are available for download for 24 hours after processing completes.
</div>
```

