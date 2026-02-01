import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import garth
from garth import sso
from garminconnect import Garmin
from rich.console import Console
from rich.status import Status

TOKEN_DIR = Path.home() / ".garmin-pr-plan"


class GarminClient:

    def __init__(self):
        self.client = None

    def authenticate(self, console: Console):
        email = os.getenv("GARMIN_EMAIL")
        password = os.getenv("GARMIN_PASSWORD")

        if not email or not password:
            raise ValueError("GARMIN_EMAIL and GARMIN_PASSWORD must be set in .env file")

        TOKEN_DIR.mkdir(exist_ok=True)
        token_file = TOKEN_DIR / "tokens"

        with Status("[bold]Connecting to Garmin...", spinner="dots", console=console):
            try:
                garth.resume(str(token_file))
                self.client = Garmin()
                self.client.garth = garth.client
                self.client.display_name
                console.print("[green]●[/green] Connected to Garmin Connect")
                return
            except Exception:
                pass

        def mfa_prompt():
            console.print()
            console.print("[yellow]●[/yellow] MFA code required [dim](check your authenticator app)[/dim]")
            while True:
                code = input("  Enter 6-digit code: ")
                digits = ''.join(c for c in code if c.isdigit())
                if len(digits) == 6:
                    console.print(f"  [green]●●●●●●[/green] [dim]Verifying...[/dim]")
                    return digits
                console.print(f"  [red]Invalid:[/red] Enter exactly 6 digits [dim](got {len(digits)})[/dim]")

        console.print("[dim]Logging in to Garmin...[/dim]")
        oauth1, oauth2 = sso.login(email, password, prompt_mfa=mfa_prompt)
        garth.client.oauth1_token = oauth1
        garth.client.oauth2_token = oauth2
        garth.save(str(token_file))

        self.client = Garmin()
        self.client.garth = garth.client
        console.print("[green]●[/green] Connected to Garmin Connect")

    def get_activities(self, days=90):
        if not self.client:
            raise RuntimeError("Not authenticated")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        activities = self.client.get_activities_by_date(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )

        running_activities = []
        for activity in activities:
            activity_type = activity.get("activityType", {}).get("typeKey", "")
            if "running" in activity_type.lower() or "run" in activity_type.lower():
                running_activities.append({
                    "date": activity.get("startTimeLocal", ""),
                    "distance_km": activity.get("distance", 0) / 1000,
                    "duration_min": activity.get("duration", 0) / 60,
                    "avg_hr": activity.get("averageHR"),
                    "avg_pace_min_km": (activity.get("duration", 0) / 60) / (activity.get("distance", 1) / 1000) if activity.get("distance", 0) > 0 else None,
                    "calories": activity.get("calories"),
                })

        return running_activities

    def _build_workout_steps(self, steps):
        garmin_steps = []

        for i, step in enumerate(steps):
            step_type = self._get_step_type(step.get("intensity", "active"))
            duration_type, duration_value = self._parse_duration(step.get("duration", "10:00"))
            target_type, target_value = self._parse_target(step.get("target", "Open"))

            garmin_step = {
                "type": "ExecutableStepDTO",
                "stepId": None,
                "stepOrder": i + 1,
                "childStepId": None,
                "description": None,
                "stepType": {
                    "stepTypeId": step_type["id"],
                    "stepTypeKey": step_type["key"],
                },
                "endCondition": {
                    "conditionTypeId": duration_type["id"],
                    "conditionTypeKey": duration_type["key"],
                },
                "endConditionValue": duration_value,
                "targetType": {
                    "workoutTargetTypeId": target_type["id"],
                    "workoutTargetTypeKey": target_type["key"],
                },
                "targetValueOne": target_value.get("low"),
                "targetValueTwo": target_value.get("high"),
            }
            garmin_steps.append(garmin_step)

        return garmin_steps

    def _get_step_type(self, intensity):
        types = {
            "warmup": {"id": 1, "key": "warmup"},
            "cooldown": {"id": 2, "key": "cooldown"},
            "rest": {"id": 4, "key": "recovery"},
            "active": {"id": 3, "key": "interval"},
        }
        return types.get(intensity, types["active"])

    def _parse_duration(self, duration):
        duration = str(duration).strip().lower()

        dist_match = re.match(r'^([\d.]+)\s*(m|km|mi|mile|miles)$', duration)
        if dist_match:
            value = float(dist_match.group(1))
            unit = dist_match.group(2)

            if unit == 'm':
                meters = value
            elif unit == 'km':
                meters = value * 1000
            elif unit in ('mi', 'mile', 'miles'):
                meters = value * 1609.34
            else:
                meters = value

            return ({"id": 3, "key": "distance"}, meters)

        time_match = re.match(r'^([\d.]+)\s*(min|mins|minute|minutes|sec|secs|second|seconds|s)$', duration)
        if time_match:
            value = float(time_match.group(1))
            unit = time_match.group(2)

            if unit in ('sec', 'secs', 'second', 'seconds', 's'):
                total_seconds = value
            else:
                total_seconds = value * 60

            return ({"id": 2, "key": "time"}, int(total_seconds))

        if ':' in duration:
            parts = duration.split(':')
            if len(parts) == 2:
                minutes, seconds = int(parts[0]), int(parts[1])
            else:
                minutes, seconds = int(parts[0]), 0
            total_seconds = minutes * 60 + seconds
            return ({"id": 2, "key": "time"}, total_seconds)

        try:
            total_seconds = int(float(duration)) * 60
            return ({"id": 2, "key": "time"}, total_seconds)
        except ValueError:
            return ({"id": 2, "key": "time"}, 600)

    def _parse_target(self, target):
        if not target or target.lower() in ("open", "jog", "easy"):
            return ({"id": 1, "key": "no.target"}, {"low": None, "high": None})

        pace_match = re.match(r'^(\d+):(\d+)(?:/?(mi|km))?$', target.strip())
        if pace_match:
            minutes = int(pace_match.group(1))
            seconds = int(pace_match.group(2))
            unit = pace_match.group(3)

            total_seconds = minutes * 60 + seconds

            if unit == 'km' or (unit is None and minutes < 10):
                meters_per_second = 1000 / total_seconds
            else:
                meters_per_second = 1609.34 / total_seconds

            pace_low = meters_per_second * 1.05
            pace_high = meters_per_second * 0.95

            return ({"id": 6, "key": "pace.zone"}, {"low": pace_low, "high": pace_high})

        if "zone" in target.lower():
            zone_match = re.search(r'(\d)', target)
            if zone_match:
                zone_num = int(zone_match.group(1))
                return ({"id": 4, "key": "heart.rate.zone"}, {"low": zone_num, "high": zone_num})

        return ({"id": 1, "key": "no.target"}, {"low": None, "high": None})

    def create_workout(self, workout_data):
        if not self.client:
            raise RuntimeError("Not authenticated")

        steps = self._build_workout_steps(workout_data.get("steps", []))

        workout = {
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutName": workout_data.get("name", "Training Run"),
            "description": workout_data.get("description", ""),
            "workoutSegments": [{
                "segmentOrder": 1,
                "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
                "workoutSteps": steps,
            }],
        }

        result = self.client.upload_workout(workout)
        return result.get("workoutId")

    def schedule_workout(self, workout_id, date):
        if not self.client:
            raise RuntimeError("Not authenticated")

        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d").date()

        self.client.garth.connectapi(
            f"/workout-service/schedule/{workout_id}",
            method="POST",
            json={"date": date.isoformat()},
        )

    def push_all_workouts(self, training_plan, console: Console = None):
        if not self.client:
            raise RuntimeError("Not authenticated")

        total = len(training_plan)
        created_count = 0
        failed = []

        for i, workout in enumerate(training_plan):
            name = workout.get('name', 'Unknown')
            if console:
                console.print(f"  [dim]({i+1}/{total})[/dim] {name}...", end=" ")

            success = False
            for attempt in range(3):
                try:
                    workout_id = self.create_workout(workout)
                    if workout_id and workout.get("date"):
                        self.schedule_workout(workout_id, workout["date"])
                    created_count += 1
                    success = True
                    if console:
                        console.print("[green]✓[/green]")
                    break
                except Exception as e:
                    if attempt == 2:
                        failed.append((name, str(e)))
                        if console:
                            console.print("[red]✗[/red]")

        if failed and console:
            console.print()
            console.print(f"[yellow]●[/yellow] {len(failed)} workouts failed after retries:")
            for name, err in failed[:3]:
                console.print(f"  [dim]{name}: {err}[/dim]")
            if len(failed) > 3:
                console.print(f"  [dim]...and {len(failed) - 3} more[/dim]")

        return created_count
