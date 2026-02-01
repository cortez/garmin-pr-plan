import json
import os
from datetime import datetime

import google.generativeai as genai


def analyze_fitness(activities):
    if not activities:
        return {"has_data": False, "message": "No running activities found"}

    metrics = {
        "has_data": True,
        "total_runs": len(activities),
        "avg_distance_km": sum(a["distance_km"] for a in activities) / len(activities),
        "total_distance_km": sum(a["distance_km"] for a in activities),
    }

    paces = [a["avg_pace_min_km"] for a in activities if a["avg_pace_min_km"]]
    if paces:
        metrics["avg_pace_min_km"] = sum(paces) / len(paces)

    hrs = [a["avg_hr"] for a in activities if a["avg_hr"]]
    if hrs:
        metrics["avg_hr"] = sum(hrs) / len(hrs)

    metrics["recent_runs"] = activities[:10]
    return metrics


def generate_training_plan(fitness_data, distance, goal_pace, race_date, long_run_day="Saturday"):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY must be set in .env file")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3-pro-preview")

    today = datetime.now().date()
    race_date_obj = datetime.strptime(race_date, "%Y-%m-%d").date()
    weeks_until_race = (race_date_obj - today).days // 7

    fitness_summary = json.dumps(fitness_data, indent=2, default=str)

    prompt = f"""You are an elite running coach creating a training plan for an experienced, competitive runner.

ATHLETE DATA:
{fitness_summary}

RACE GOAL:
- Distance: {distance}
- Goal Pace: {goal_pace}
- Race Date: {race_date}
- Weeks until race: {weeks_until_race}
- Today: {today}

SCHEDULE PREFERENCES:
- Long runs should be on {long_run_day}
- Space out hard workouts with easy days between them

TRAINING PHILOSOPHY:
Create a periodized plan following Daniels/Pfitzinger/Hudson methodologies. Include:
- Easy/recovery runs (60-90 sec/mi slower than goal pace)
- Long runs with progression
- Tempo runs at lactate threshold
- VO2max intervals (5K pace, 3-5 min efforts)
- Speed work (200m-800m repeats)
- Race-specific workouts
- Proper taper in final 10-14 days

CRITICAL FORMATTING RULES:
1. Use ROUND distances: 4 mi, 5 mi, 6 mi, 8 mi, 10 mi, 12 mi, etc.
2. Specify PACES as "M:SS/mi" format (e.g., "7:30/mi", "6:15/mi")
3. Race day = ONE step only, the race at goal pace. NO warmup/cooldown.
4. Each step is ONE interval. For repeats, create separate steps:
   - "800m Repeat 1", "Recovery 1", "800m Repeat 2", "Recovery 2", etc.
   - NEVER use "4x800m" or "6x400m" notation in duration field
5. Duration formats allowed:
   - Distance: "800m", "1 mi", "2 mi", "400m"
   - Time: "10:00", "5:00", "3:00" (MM:SS format only)
   - NEVER use "1 min" or "3 min" - use "1:00" or "3:00" instead
6. Recovery between intervals: use "90 sec" as "1:30" or distance like "400m"

PACE ZONES (based on goal pace {goal_pace}):
- Easy: 60-90 sec/mi slower
- Tempo: 15-20 sec/mi slower
- VO2max: 20-30 sec/mi faster
- Speed: 45-60 sec/mi faster

OUTPUT FORMAT - Return ONLY valid JSON array:
[
  {{
    "date": "YYYY-MM-DD",
    "name": "Week X - Workout Type",
    "description": "Brief description",
    "steps": [
      {{"name": "Warm Up", "duration": "2 mi", "target": "8:30/mi", "intensity": "warmup"}},
      {{"name": "Tempo", "duration": "4 mi", "target": "6:45/mi", "intensity": "active"}},
      {{"name": "Cool Down", "duration": "1 mi", "target": "8:30/mi", "intensity": "cooldown"}}
    ]
  }}
]

For intervals (EACH repeat is a separate step):
{{"name": "800m Repeat 1", "duration": "800m", "target": "3:00/mi", "intensity": "active"}},
{{"name": "Recovery 1", "duration": "400m", "target": "jog", "intensity": "rest"}},
{{"name": "800m Repeat 2", "duration": "800m", "target": "3:00/mi", "intensity": "active"}},
{{"name": "Recovery 2", "duration": "400m", "target": "jog", "intensity": "rest"}}

Race day (single step only):
{{
  "date": "{race_date}",
  "name": "Race Day",
  "description": "Execute your race plan at {goal_pace}",
  "steps": [{{"name": "{distance}", "duration": "13.1 mi", "target": "{goal_pace}", "intensity": "active"}}]
}}

Generate 4-5 quality workouts per week.
Return ONLY the JSON array."""

    response = model.generate_content(prompt)
    response_text = response.text.strip()

    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError:
        raise ValueError("Failed to parse training plan from Gemini")
