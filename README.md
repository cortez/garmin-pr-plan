# Garmin PR Plan

Training plan generator that creates personalized running workouts and syncs them directly to Garmin Connect. Powered by Gemini 3 Pro.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your credentials:

- `GEMINI_API_KEY` - Get from [Google AI Studio](https://aistudio.google.com/apikey)
- `GARMIN_EMAIL` - Your Garmin Connect email
- `GARMIN_PASSWORD` - Your Garmin Connect password

## Usage

```bash
source venv/bin/activate
python main.py
```

The CLI will prompt for:

- Race distance (5K, 10K, half marathon, marathon, etc.)
- Goal pace
- Race date
- Preferred long run day

## Features

- Pulls your running history from Garmin Connect
- Generates periodized training plans using Gemini AI
- Creates structured workouts with pace targets
- Schedules workouts on your Garmin calendar
- Syncs to your watch automatically

## Requirements

- Python 3.10+
- Garmin Connect account
- Google AI API key
