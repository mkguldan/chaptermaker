# Video Chapter Maker - Quick Start Guide

## Prerequisites

- Google Cloud Platform account
- OpenAI API key (with access to GPT-4o and GPT-5)
- Git
- Docker & Docker Compose (for local development)
- Python 3.11+ (for CLI tool)
- Node.js 18+ (for frontend development)

## 1. Initial Setup (5 minutes)

### Clone the repository
```bash
git clone https://github.com/mkguldan/chaptermaker.git
cd chaptermaker
```

### Set up GCP (Windows PowerShell)
```powershell
# Run the setup script
.\scripts\setup-gcp.ps1
```

### Configure environment
```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your OpenAI API key
# OPENAI_API_KEY=sk-your-actual-key-here
```

## 2. Local Development (2 minutes)

### Start with Docker Compose
```bash
# Build and start all services
docker-compose up --build

# Access the application
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/api/docs
```

## 3. Process Your First Video

### Option A: Web Interface

1. Open http://localhost:3000 in your browser
2. Drag and drop a video file (.mp4, .avi, etc.)
3. Drag and drop the corresponding presentation (.pptx or .pdf)
4. Click "Add to Queue"
5. Click "Process All"
6. Monitor progress in the "Processing Jobs" tab
7. Download results when complete

### Option B: CLI Tool

```bash
# Navigate to CLI directory
cd cli

# Install dependencies
pip install -r requirements.txt

# Process a single video
python chaptermaker-cli.py process \
  --video samples/presentation.mp4 \
  --presentation samples/presentation.pptx \
  --output ./output

# Batch process videos
python chaptermaker-cli.py batch \
  --input ./videos \
  --output ./output
```

## 4. Deploy to Production (10 minutes)

### Push to GitHub
```bash
git add .
git commit -m "Initial deployment"
git push origin main
```

### Set GitHub Secrets
Go to GitHub repository settings → Secrets and add:
- `GCP_SERVICE_ACCOUNT_KEY`: Base64 encoded service account JSON
- `OPENAI_API_KEY`: Your OpenAI API key

### Deploy
The GitHub Actions workflow will automatically deploy to Cloud Run when you push to the main branch.

## 5. Production URLs

After deployment completes, your services will be available at:
- Frontend: `https://chaptermaker-web-XXXXX-us-central1.run.app`
- API: `https://chaptermaker-api-XXXXX-us-central1.run.app`
- API Docs: `https://chaptermaker-api-XXXXX-us-central1.run.app/api/docs`

## Troubleshooting

### Common Issues

1. **LibreOffice not found warning**
   - Install LibreOffice for better PowerPoint conversion
   - Without it, basic slide extraction is used

2. **GCS authentication errors**
   - Ensure `service-account-key.json` exists
   - Check that the service account has proper permissions

3. **OpenAI API errors**
   - Verify your API key has access to GPT-4o and GPT-5
   - Check your OpenAI account has sufficient credits

### Getting Help

- Check the API documentation at `/api/docs`
- Review logs in Docker: `docker-compose logs -f backend`
- For GCP issues, check Cloud Run logs in the console

## Next Steps

- Read the full README.md for detailed documentation
- Customize the chapter generation prompts in the backend
- Set up monitoring and alerts in GCP
- Configure custom domains for your services

## Sample Files

Need sample files to test? The `importChapters.csv` and `qa.jpg` in the project root show the expected output format.

Happy processing! 🎬
