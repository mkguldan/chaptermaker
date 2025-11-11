# Deployment Checklist for Video Chapter Maker

## ✅ Completed
- [x] Code pushed to GitHub: https://github.com/mkguldan/chaptermaker
- [x] CI/CD workflow configured to use GCP Secret Manager
- [x] Project configured for ai-mvp-452812

## 🔧 Required Actions

### 1. Grant Secret Access to Cloud Run (REQUIRED)

The Cloud Run service needs permission to access your OpenAI API key from Secret Manager:

```bash
# Authenticate with gcloud
gcloud auth login

# Set project
gcloud config set project ai-mvp-452812

# Get the compute service account
PROJECT_NUMBER=$(gcloud projects describe ai-mvp-452812 --format="value(projectNumber)")
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Grant secret access
gcloud secrets add-iam-policy-binding OPENAI_API_KEY \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor"
```

### 2. Add GitHub Secret (REQUIRED)

Go to your GitHub repository settings:
https://github.com/mkguldan/chaptermaker/settings/secrets/actions

Add this secret:
- **Name**: `GCP_SERVICE_ACCOUNT_KEY`
- **Value**: Base64 encoded service account JSON

To get the value:
```bash
# If you have service-account-key.json
cat service-account-key.json | base64 -w 0

# On Windows PowerShell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("service-account-key.json"))
```

### 3. Ensure GCP Resources Exist

Run the setup script if you haven't already:
```powershell
.\scripts\setup-gcp.ps1
```

This creates:
- GCS buckets for uploads and outputs
- Artifact Registry repository
- Cloud Tasks queue
- Service account with proper permissions

### 4. Trigger Deployment

The deployment should have automatically started when you pushed to GitHub.

Check the status:
https://github.com/mkguldan/chaptermaker/actions

If it didn't start or failed, you can manually trigger it:
1. Go to Actions tab
2. Select "Deploy to Cloud Run" workflow
3. Click "Run workflow"

## 📊 Monitoring Deployment

### GitHub Actions
- URL: https://github.com/mkguldan/chaptermaker/actions
- Watch for successful completion of all jobs

### Expected Deployment Steps
1. ✅ Deploy Backend (5-10 minutes)
   - Build Docker image
   - Push to Artifact Registry
   - Deploy to Cloud Run
   
2. ✅ Deploy Frontend (3-5 minutes)
   - Build Docker image with backend URL
   - Push to Artifact Registry
   - Deploy to Cloud Run
   
3. ✅ Setup Cloud Storage (1 minute)
   - Upload qa.jpg
   - Set CORS policies

### After Deployment

Your services will be available at:
- **Frontend**: https://chaptermaker-web-{hash}-us-central1.run.app
- **Backend API**: https://chaptermaker-api-{hash}-us-central1.run.app
- **API Docs**: https://chaptermaker-api-{hash}-us-central1.run.app/api/docs

The exact URLs will be shown in the GitHub Actions summary.

## 🔍 Troubleshooting

### If Deployment Fails

1. **Check GitHub Actions logs**:
   https://github.com/mkguldan/chaptermaker/actions

2. **Common issues**:
   - Missing `GCP_SERVICE_ACCOUNT_KEY` secret
   - Service account doesn't have proper permissions
   - Buckets or Artifact Registry not created
   - Secret Manager permission not granted

3. **Cloud Run logs**:
   ```bash
   # Backend logs
   gcloud run services logs read chaptermaker-api \
       --region us-central1 \
       --limit 50
   
   # Frontend logs
   gcloud run services logs read chaptermaker-web \
       --region us-central1 \
       --limit 50
   ```

### If Secret Access Fails

Verify the secret exists:
```bash
gcloud secrets describe OPENAI_API_KEY
```

Check IAM permissions:
```bash
gcloud secrets get-iam-policy OPENAI_API_KEY
```

## 🚀 Next Steps After Successful Deployment

1. **Test the application**:
   - Visit the frontend URL
   - Upload a test video and presentation
   - Monitor processing in the Jobs tab

2. **Set up custom domain** (optional):
   - Map your domain to the Cloud Run services
   - Update CORS settings if needed

3. **Configure monitoring**:
   - Set up Cloud Monitoring alerts
   - Configure error reporting
   - Set up budget alerts

4. **Scale settings**:
   - Adjust max instances based on usage
   - Configure concurrency limits
   - Set up auto-scaling policies

## 📝 Important Notes

- The OPENAI_API_KEY is stored securely in GCP Secret Manager (projects/695406125250/secrets/OPENAI_API_KEY)
- Cloud Run will automatically retrieve it during deployment
- No secrets are stored in GitHub
- The service account needs both Cloud Run and Secret Manager access

## 🆘 Need Help?

Check the logs in order:
1. GitHub Actions (deployment issues)
2. Cloud Run logs (runtime issues)
3. Backend /health endpoint (service health)
4. Backend /api/docs (API documentation)

For GCP-specific issues:
- Cloud Console: https://console.cloud.google.com
- Project: ai-mvp-452812
- Region: us-central1
