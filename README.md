# Video Chapter Maker

An AI-powered application that processes video presentations to automatically generate chapters, extract slides, and create subtitles using OpenAI's Whisper API (`whisper-1`) for transcription and GPT-5 for chapter generation.

## Features

- **Audio & Video Support**: Upload audio files (MP3, WAV, M4A, etc.) or videos - audio files are faster!
- **Automatic Transcription**: Uses the OpenAI Whisper API (model `whisper-1`, segment timestamps); long audio is split into 10-minute chunks
- **Smart Chapter Generation**: Uses GPT-5 (gpt-5-2025-08-07) to create meaningful chapters
- **Presentation Slide Extraction**: Extracts slides from PowerPoint or PDF presentations
- **Q&A Detection**: Automatically identifies Q&A sections and applies appropriate images
- **Subtitle Generation**: Creates .srt subtitle files
- **Batch Processing**: Process multiple files simultaneously
- **Web Interface**: Elegant UI built with React and Tailwind CSS
- **CLI Tool**: Optional command-line interface for local batch processing
- **Direct Cloud Upload**: Uses GCS signed URLs for efficient file uploads
- **Job API for Inframe**: `POST /api/v1/jobs` on gs:// URIs, executed reliably through Cloud Tasks (see below)

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
- OpenAI API key with access to `whisper-1` and GPT-5
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

# Job API: leave CLOUD_TASKS_QUEUE empty locally to run jobs inline
CLOUD_TASKS_QUEUE=
CLOUD_TASKS_LOCATION=europe-west1

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

1. **Runtime service account and IAM**: The service runs as `chaptermaker-runner@ai-mvp-452812.iam.gserviceaccount.com`
   and is private (`--no-allow-unauthenticated`). Create the account and grant its roles with the commands in
   [Runtime service account and IAM](#runtime-service-account-and-iam) before the first deploy that uses it.

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

## Job API (used by Inframe)

Inframe calls this service server-to-server to chapter event videos. The
service is private: callers authenticate with a Google ID token for the
service URL (Cloud Run IAM, `roles/run.invoker`). There is no app-level auth.

### `POST /api/v1/jobs` -> `202`

```json
{ "video_uri": "gs://bucket/path.mp4", "presentation_uri": "gs://bucket/deck.pdf", "title": "Keynote", "language": "en" }
```

- `video_uri` (required) and `presentation_uri` (optional, `.pdf`/`.pptx`/`.ppt`) must be
  `gs://bucket/object` URIs. They are read with the service account (no signed URLs), so the
  runtime service account needs read access to the bucket. Objects are checked at submit time:
  invalid URIs, missing or unreadable objects, and buckets outside `ALLOWED_INPUT_BUCKETS` return `422`.
- `title` (optional) is passed to GPT-5 as context. `language` (optional, ISO-639-1 such as `en`, `da`;
  `en-GB` is reduced to `en`) is passed to Whisper; `null` lets Whisper detect it.
- Response: `{ "job_id": "job_<32 hex>", "status": "queued" }`. `503` if the task could not be queued.

### `GET /api/v1/jobs/{job_id}`

```json
{ "job_id": "...", "status": "queued|processing|completed|failed", "progress": 0, "message": "Transcribing audio (3/12 chunks)", "error": null, "created_at": "2026-10-12T10:00:00Z", "updated_at": "..." }
```

Jobs created by the web UI keep their original response shape on this endpoint.

### `GET /api/v1/jobs/{job_id}/result`

`404` for unknown jobs, `409` until the job is `completed`. Then:

```json
{
  "chapters": [{ "start_seconds": 0, "title": "Opening", "description": null, "slide_uri": "gs://chaptermaker-outputs-ai-mvp-452812/outputs/<job>/slides/01.jpg" }],
  "srt_uri": "gs://chaptermaker-outputs-ai-mvp-452812/outputs/<job>/subtitles.srt",
  "transcript": [{ "start": 1.0, "end": 4.2, "text": "Good morning" }],
  "slides": ["gs://.../slides/01.jpg", "gs://.../slides/02.jpg"],
  "qa_slide_uri": "gs://.../slides/qa.jpg",
  "duration_seconds": 1834.5
}
```

Outputs stay in Chaptermaker's output bucket under `outputs/<job_id>/`; Inframe copies what it needs.
Q&A chapters point at `qa_slide_uri`. Without a presentation, `slides` is empty and `slide_uri` is `null`.

## How jobs execute (Cloud Tasks)

The web UI's `/videos/process` still uses FastAPI `BackgroundTasks`. API jobs do not, because on
Cloud Run the CPU is throttled after the response is sent and the instance can be stopped mid-job.

1. `POST /api/v1/jobs` writes the job record (`gs://<output bucket>/job-tracking/<job_id>.json`,
   `"kind": "api"`) and creates a Cloud Tasks HTTP task named `<job hex>-0` that calls
   `POST /internal/run/<job_id>` on this service, with an OIDC token for `TASKS_SERVICE_ACCOUNT`
   and the service URL as the audience.
2. The task request does the work itself, so Cloud Run keeps the CPU allocated. Steps, each
   checkpointed in the job record or in `work/<job_id>/` in the output bucket:
   one ffmpeg pass that extracts mono 16 kHz audio and splits it into 10-minute chunks
   (files over `STREAM_INPUT_THRESHOLD_MB` are streamed into ffmpeg over HTTPS instead of copied to `/tmp`,
   which is memory on Cloud Run) -> Whisper per chunk, 4 in parallel, each chunk saved as it finishes
   -> slide rendering -> GPT-5 chapters, SRT and result.
3. Time limits: Cloud Run allows up to 3600 s per request, but Cloud Tasks allows at most
   **30 minutes per HTTP dispatch** (`dispatch_deadline` range is 15 s to 30 min). A task stops starting new work after
   `TASK_SOFT_BUDGET_SECONDS` (600 s), creates a continuation task (`<job hex>-1`, `-2`, ...) and returns `200`.
   The longest single unit (audio extraction, or one GPT-5 call with client retries) fits in the remaining 20 minutes.
4. Idempotency and retries:
   - The worker holds a lease on the job record (CAS on the GCS object generation) and renews it every 40 s.
     A duplicate delivery waits: if the holder is still heartbeating it returns `200` and does nothing; if the
     holder died, the lease expires (120 s) and the retry takes over from the last checkpoint.
   - A delivery for a completed/failed job, or an older task sequence number, is a `200` no-op.
   - Bad input (missing object, no audio track, unsupported deck) fails the job immediately with `200`.
   - Other errors return `500` so the queue retries. On attempt `TASK_MAX_ATTEMPTS` (3) the job is marked
     `failed` and `200` is returned. If every attempt was killed (e.g. out of memory), the next delivery or the next
     status read (no heartbeat for `JOB_STALE_SECONDS`) marks it failed.
   - Continuation tasks have deterministic names, so a retried hand-off cannot create two of them.
5. Without `CLOUD_TASKS_QUEUE` (local development) the job runs inline in the API process.

`/internal/run` rejects requests without the `X-CloudTasks-QueueName` header for the configured queue
when Cloud Tasks is enabled. IAM already limits who can reach the service.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CLOUD_TASKS_QUEUE` | empty (inline) | Queue name, e.g. `video-processing` |
| `CLOUD_TASKS_LOCATION` | `europe-west1` | Queue region |
| `SERVICE_URL` | derived from the request `Host` | Task target and OIDC audience |
| `TASKS_SERVICE_ACCOUNT` | metadata server (runtime SA) | SA for the task's OIDC token |
| `TASK_MAX_ATTEMPTS` | `3` | Keep equal to the queue's `maxAttempts` |
| `TASK_DISPATCH_DEADLINE_SECONDS` | `1800` | Clamped to Cloud Tasks' 30 min maximum |
| `TASK_SOFT_BUDGET_SECONDS` | `600` | Work started per task before handing off |
| `JOB_LEASE_SECONDS` / `JOB_STALE_SECONDS` | `120` / `3600` | Worker lease; stale-job cutoff |
| `TRANSCRIBE_CHUNK_SECONDS` / `TRANSCRIBE_PARALLELISM` | `600` / `4` | Whisper chunking |
| `STREAM_INPUT_THRESHOLD_MB` | `512` | Larger inputs are streamed into ffmpeg |
| `ALLOWED_INPUT_BUCKETS` | empty (any) | `;`-separated bucket allowlist for the job API |

### Runtime service account and IAM

Cloud Run runs as a dedicated service account, `chaptermaker-runner@ai-mvp-452812.iam.gserviceaccount.com`
(the workflow uses it unless the repository variable `RUNTIME_SERVICE_ACCOUNT` says otherwise). It needs:

- `roles/storage.objectViewer` on Inframe's bucket `ai-mvp-452812-inframe-photos`
- `roles/storage.objectAdmin` on `chaptermaker-uploads-ai-mvp-452812` and `chaptermaker-outputs-ai-mvp-452812`
- `roles/cloudtasks.enqueuer` on the `video-processing` queue
- `roles/iam.serviceAccountUser` on itself, so Cloud Tasks may mint OIDC tokens as it
- `roles/iam.serviceAccountTokenCreator` on itself, for the web UI's signed upload/download URLs
- `roles/run.invoker` on the service, because Cloud Tasks calls `/internal/run` with its token
- `roles/secretmanager.secretAccessor` on the `OPENAI_API_KEY` secret

Inframe's service account `ai-voice-agent-sa@ai-mvp-452812.iam.gserviceaccount.com` needs `roles/run.invoker`
on the service. The deployer (`chaptermaker-service@`, used by GitHub Actions) needs `roles/iam.serviceAccountUser`
on the runtime SA.

Commands (run once by the project owner, before merging the change that switches the runtime SA):

```bash
PROJECT=ai-mvp-452812
REGION=europe-west1
RUNNER=chaptermaker-runner@$PROJECT.iam.gserviceaccount.com

gcloud iam service-accounts create chaptermaker-runner --project=$PROJECT \
  --display-name="Chaptermaker Cloud Run runtime"

gcloud storage buckets add-iam-policy-binding gs://ai-mvp-452812-inframe-photos \
  --member=serviceAccount:$RUNNER --role=roles/storage.objectViewer
gcloud storage buckets add-iam-policy-binding gs://chaptermaker-uploads-$PROJECT \
  --member=serviceAccount:$RUNNER --role=roles/storage.objectAdmin
gcloud storage buckets add-iam-policy-binding gs://chaptermaker-outputs-$PROJECT \
  --member=serviceAccount:$RUNNER --role=roles/storage.objectAdmin

gcloud tasks queues add-iam-policy-binding video-processing --location=$REGION --project=$PROJECT \
  --member=serviceAccount:$RUNNER --role=roles/cloudtasks.enqueuer

gcloud iam service-accounts add-iam-policy-binding $RUNNER --project=$PROJECT \
  --member=serviceAccount:$RUNNER --role=roles/iam.serviceAccountUser
gcloud iam service-accounts add-iam-policy-binding $RUNNER --project=$PROJECT \
  --member=serviceAccount:$RUNNER --role=roles/iam.serviceAccountTokenCreator
gcloud iam service-accounts add-iam-policy-binding $RUNNER --project=$PROJECT \
  --member=serviceAccount:chaptermaker-service@$PROJECT.iam.gserviceaccount.com \
  --role=roles/iam.serviceAccountUser

gcloud secrets add-iam-policy-binding OPENAI_API_KEY --project=$PROJECT \
  --member=serviceAccount:$RUNNER --role=roles/secretmanager.secretAccessor

gcloud run services add-iam-policy-binding chaptermaker --region=$REGION --project=$PROJECT \
  --member=serviceAccount:$RUNNER --role=roles/run.invoker
gcloud run services add-iam-policy-binding chaptermaker --region=$REGION --project=$PROJECT \
  --member=serviceAccount:ai-voice-agent-sa@$PROJECT.iam.gserviceaccount.com --role=roles/run.invoker

# Queue: few attempts, bounded backoff (it was created with maxAttempts 100, maxBackoff 3600s).
gcloud tasks queues update video-processing --location=$REGION --project=$PROJECT \
  --max-attempts=3 --min-backoff=30s --max-backoff=300s --max-doublings=3 \
  --max-concurrent-dispatches=8 --max-dispatches-per-second=5
```

Keep `TASK_MAX_ATTEMPTS` equal to the queue's `--max-attempts`, and keep `--max-backoff` well below
`JOB_STALE_SECONDS`.

The runtime SA has no project-level `storage.buckets.list`, so `/api/v1/health/ready` reports GCS as
unhealthy; `/health` is the liveness check. With the service private, open the web UI through
`gcloud run services proxy chaptermaker --region europe-west1`.

### Calling it from another service

```bash
URL=$(gcloud run services describe chaptermaker --region europe-west1 --format 'value(status.url)')
TOKEN=$(gcloud auth print-identity-token)   # from a service: fetch an ID token with audience=$URL
curl -X POST "$URL/api/v1/jobs" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"video_uri":"gs://ai-mvp-452812-inframe-photos/events/x/talk.mp4","presentation_uri":null,"title":null,"language":null}'
```

## Tests

```bash
cd backend
pip install -r requirements.txt
OPENAI_API_KEY=test python -m pytest -q
```

The tests use in-memory fakes for GCS, Cloud Tasks, ffmpeg and OpenAI. CI runs them before every deploy.

## License

MIT License
