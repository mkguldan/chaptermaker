# Video Chapter Maker CLI

Command-line interface for batch processing videos with the Video Chapter Maker system.

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export OPENAI_API_KEY="your-openai-api-key"
export GCP_PROJECT_ID="ai-mvp-452812"
export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account-key.json"
```

3. Make the script executable:
```bash
chmod +x chaptermaker-cli.py
```

## Usage

### Process Single Video

```bash
python chaptermaker-cli.py process \
  --video path/to/video.mp4 \
  --presentation path/to/slides.pptx \
  --output ./output
```

### Batch Process Videos

Process all videos in a directory (looks for matching presentations with same name):

```bash
python chaptermaker-cli.py batch \
  --input ./videos \
  --output ./output \
  --pattern "*.mp4"
```

### List Jobs

```bash
python chaptermaker-cli.py list --status completed
```

## Configuration File

You can use a JSON configuration file instead of environment variables:

```json
{
  "openai_api_key": "your-key",
  "gcp_project_id": "ai-mvp-452812",
  "service_account_key": "path/to/key.json"
}
```

Use with `--config` flag:
```bash
python chaptermaker-cli.py process --config config.json ...
```

## File Naming Convention

For batch processing, videos and presentations must have matching names:
- `presentation1.mp4` → `presentation1.pptx` (or `.pdf`)
- `lecture_01.mp4` → `lecture_01.pdf`

## Output Structure

Results are saved in the output directory with the following structure:
```
output/
└── job_12345/
    ├── importChapters.csv
    ├── subtitles.srt
    ├── transcript.txt
    └── slides/
        ├── 01.jpg
        ├── 02.jpg
        └── qa.jpg
```

## Examples

### Process Multiple Specific Files

```bash
# Process first video
python chaptermaker-cli.py process \
  --video lecture1.mp4 \
  --presentation lecture1.pptx \
  --output ./results

# Process second video  
python chaptermaker-cli.py process \
  --video lecture2.mp4 \
  --presentation lecture2.pdf \
  --output ./results
```

### Batch Process with Custom Pattern

```bash
# Process only webinar videos
python chaptermaker-cli.py batch \
  --input ./recordings \
  --output ./processed \
  --pattern "webinar_*.mp4"
```

## Notes

- The CLI uploads files to Google Cloud Storage before processing
- Large video files may take several minutes to upload and process
- Ensure you have sufficient GCS quota and permissions
- Results are automatically downloaded after processing completes
