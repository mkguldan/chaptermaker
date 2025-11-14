#!/bin/bash

# Script to set up GCS lifecycle policies for automatic deletion after 24 hours
# Run this once to configure the buckets

set -e

# Get project ID from environment or parameter
PROJECT_ID=${GCP_PROJECT_ID:-"ai-mvp-452812"}
REGION="europe-west1"

echo "🗑️  Setting up GCS lifecycle policies for automatic cleanup..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"

# Bucket names
UPLOAD_BUCKET="chaptermaker-uploads-${PROJECT_ID}"
OUTPUT_BUCKET="chaptermaker-outputs-${PROJECT_ID}"

# Create lifecycle configuration JSON
cat > /tmp/lifecycle-24h.json << 'EOF'
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

echo ""
echo "📦 Configuring lifecycle policy for upload bucket: $UPLOAD_BUCKET"
gsutil lifecycle set /tmp/lifecycle-24h.json gs://${UPLOAD_BUCKET}/ || {
    echo "⚠️  Warning: Could not set lifecycle on upload bucket. It may not exist yet."
}

echo ""
echo "📦 Configuring lifecycle policy for output bucket: $OUTPUT_BUCKET"
gsutil lifecycle set /tmp/lifecycle-24h.json gs://${OUTPUT_BUCKET}/ || {
    echo "⚠️  Warning: Could not set lifecycle on output bucket. It may not exist yet."
}

# Clean up temp file
rm /tmp/lifecycle-24h.json

echo ""
echo "✅ Lifecycle policies configured successfully!"
echo ""
echo "📋 Policy Summary:"
echo "  - Files older than 1 day (24 hours) will be automatically deleted"
echo "  - Applies to: uploads/, outputs/, job-tracking/ prefixes"
echo "  - Deletion happens once per day (not exactly at 24h, but within 24-48h)"
echo ""
echo "🔍 To verify the configuration, run:"
echo "  gsutil lifecycle get gs://${UPLOAD_BUCKET}/"
echo "  gsutil lifecycle get gs://${OUTPUT_BUCKET}/"

