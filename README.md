# Video Chapter Maker

An AI-powered application that processes video presentations to automatically generate chapters, extract slides, and create subtitles using OpenAI's GPT-4o for transcription and GPT-5 for chapter generation.

## Features

- **Automatic Video Transcription**: Uses OpenAI GPT-4o-transcribe for accurate transcription
- **Smart Chapter Generation**: Uses GPT-5 (gpt-5-2025-08-07) to create meaningful chapters
- **Presentation Slide Extraction**: Extracts slides from PowerPoint or PDF presentations
- **Q&A Detection**: Automatically identifies Q&A sections and applies appropriate images
- **Subtitle Generation**: Creates .srt subtitle files
- **Batch Processing**: Process multiple videos simultaneously
- **Web Interface**: Elegant UI built with React and Tailwind CSS
- **CLI Tool**: Optional command-line interface for local batch processing
- **Direct Cloud Upload**: Uses GCS signed URLs for efficient large file uploads

## Project Structure

```
chaptermaker/
├── backend/           # FastAPI backend service
├── frontend/          # React frontend application  
├── cli/              # Command-line interface tool
├── .github/          # GitHub Actions CI/CD workflows
└── docker-compose.yml
```

## Prerequisites

- Google Cloud Platform account
- OpenAI API key with access to GPT-4o and GPT-5
- Python 3.11+
- Node.js 18+
- Docker (for containerized deployment)

## GCP Setup Instructions

### 1. Create a GCP Project

```bash
# Install Google Cloud SDK if not already installed
# https://cloud.google.com/sdk/docs/install

# Login to GCP
gcloud auth login

# Use existing project
gcloud config set project ai-mvp-452812
```

### 2. Enable Required APIs

```bash
# Enable necessary APIs
gcloud services enable compute.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry-googleapis.com
gcloud services enable cloudtasks.googleapis.com
gcloud services enable storage-component.googleapis.com
```

### 3. Create Service Account

```bash
# Create service account for the application
gcloud iam service-accounts create chaptermaker-service \
    --display-name="Chapter Maker Service Account"

# Grant necessary permissions
gcloud projects add-iam-policy-binding ai-mvp-452812 \
    --member="serviceAccount:chaptermaker-service@ai-mvp-452812.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding ai-mvp-452812 \
    --member="serviceAccount:chaptermaker-service@ai-mvp-452812.iam.gserviceaccount.com" \
    --role="roles/cloudtasks.enqueuer"

gcloud projects add-iam-policy-binding ai-mvp-452812 \
    --member="serviceAccount:chaptermaker-service@ai-mvp-452812.iam.gserviceaccount.com" \
    --role="roles/run.invoker"

# Create and download service account key
gcloud iam service-accounts keys create service-account-key.json \
    --iam-account=chaptermaker-service@ai-mvp-452812.iam.gserviceaccount.com
```

### 4. Create GCS Buckets

```bash
# Create bucket for video uploads and outputs
gsutil mb -p ai-mvp-452812 -c STANDARD -l us-central1 gs://chaptermaker-uploads-ai-mvp-452812/
gsutil mb -p ai-mvp-452812 -c STANDARD -l us-central1 gs://chaptermaker-outputs-ai-mvp-452812/

# Set bucket permissions
gsutil iam ch serviceAccount:chaptermaker-service@ai-mvp-452812.iam.gserviceaccount.com:objectAdmin gs://chaptermaker-uploads-ai-mvp-452812
gsutil iam ch serviceAccount:chaptermaker-service@ai-mvp-452812.iam.gserviceaccount.com:objectAdmin gs://chaptermaker-outputs-ai-mvp-452812
```

### 5. Create Artifact Registry

```bash
# Create repository for Docker images
gcloud artifacts repositories create chaptermaker-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="Docker repository for Chapter Maker"
```

## Environment Variables

Create a `.env` file in the project root:

```env
# OpenAI
OPENAI_API_KEY=your-openai-api-key

# Google Cloud
GCP_PROJECT_ID=ai-mvp-452812
GCS_UPLOAD_BUCKET=chaptermaker-uploads-ai-mvp-452812
GCS_OUTPUT_BUCKET=chaptermaker-outputs-ai-mvp-452812
GOOGLE_APPLICATION_CREDENTIALS=service-account-key.json

# Application
APP_ENV=development
API_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
```

## Local Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Docker Development

```bash
# Build and run with docker-compose
docker-compose up --build
```

## Deployment

The project includes GitHub Actions workflows for automatic deployment to Cloud Run.

### Prerequisites

1. **Grant Secret Access**: The Cloud Run service needs access to your OpenAI API key secret:
   ```bash
   # Get the compute service account email
   PROJECT_NUMBER=$(gcloud projects describe ai-mvp-452812 --format="value(projectNumber)")
   SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
   
   # Grant secret accessor role
   gcloud secrets add-iam-policy-binding OPENAI_API_KEY \
       --member="serviceAccount:${SERVICE_ACCOUNT}" \
       --role="roles/secretmanager.secretAccessor"
   ```

2. **Add GitHub Secrets**: Add the following secret to your GitHub repository:
   - `GCP_SERVICE_ACCOUNT_KEY` (base64 encoded service account JSON)

3. **Push to Deploy**:
   ```bash
   git add .
   git commit -m "Deploy to Cloud Run"
   git push origin main
   ```

## Usage

### Web Interface

1. Access the web interface at your Cloud Run URL
2. Upload video files and corresponding presentations
3. Monitor processing progress
4. Download generated chapters, slides, and subtitles

### CLI Tool

```bash
# Process a single video
python cli/chaptermaker-cli.py process --video video.mp4 --presentation slides.pptx

# Batch process multiple videos
python cli/chaptermaker-cli.py batch --input-dir ./videos --output-dir ./outputs
```

## Output Format

For each processed video, the following files are generated:

- `importChapters.csv` - Chapter timestamps and descriptions
- `slides/01.jpg, 02.jpg...` - Extracted presentation slides
- `slides/qa.jpg` - Q&A image for Q&A sections
- `subtitles.srt` - Video subtitles

## License

MIT License
