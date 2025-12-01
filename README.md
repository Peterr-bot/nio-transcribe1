# Nio Transcribe

Catholic Media Viral Moment Extraction Tool

## Features

- Extract viral moments from YouTube videos using AI
- Generate editor cut sheets with detailed production notes
- Auto-clip videos using FFmpeg
- Download videos directly from YouTube
- Export to CSV, Markdown, PDF, and FFmpeg JSON formats

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export APIFY_TOKEN=your_token
export APIFY_ACTOR_ID=your_actor_id
export OPENAI_API_KEY=your_key
```

3. Run the app:
```bash
streamlit run src/app_streamlit.py
```

## Usage

1. Enter a YouTube URL or paste a transcript
2. Click "Generate Viral Clips" to extract moments
3. Download the video and run the auto-clipper to create clips

## Requirements

- Python 3.8+
- FFmpeg
- OpenAI API key
- Apify account
