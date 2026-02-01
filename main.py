#!/usr/bin/env python3

import os
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.status import Status

from coach import analyze_fitness, generate_training_plan
from garmin_client import GarminClient

console = Console()


def format_pace(min_per_km):
    min_per_mile = min_per_km * 1.60934
    mile_min = int(min_per_mile)
    mile_sec = int((min_per_mile - mile_min) * 60)
    km_min = int(min_per_km)
    km_sec = int((min_per_km - km_min) * 60)
    return f"{mile_min}:{mile_sec:02d}/mi [dim]({km_min}:{km_sec:02d}/km)[/dim]"


def main():
    load_dotenv()

    console.print()
    console.print(Panel.fit(
        "[bold]GARMIN PR PLAN[/bold]\n[dim]Powered by Gemini 3 Pro[/dim]",
        border_style="blue",
    ))
    console.print()

    required_vars = ["GEMINI_API_KEY", "GARMIN_EMAIL", "GARMIN_PASSWORD"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        console.print(f"[red]Error:[/red] Missing environment variables: {', '.join(missing)}")
        console.print("[dim]Copy .env.example to .env and fill in your credentials.[/dim]")
        sys.exit(1)

    garmin = GarminClient()
    try:
        garmin.authenticate(console)
    except Exception as e:
        console.print(f"\n[red]Error:[/red] Failed to connect to Garmin: {e}")
        sys.exit(1)

    with Status("[bold]Fetching activity history...", spinner="dots", console=console):
        activities = garmin.get_activities(days=90)

    fitness_data = analyze_fitness(activities)

    if fitness_data.get("has_data"):
        runs = fitness_data.get('total_runs', 0)
        avg_dist_km = fitness_data.get('avg_distance_km', 0)
        avg_dist_mi = avg_dist_km * 0.621371
        console.print(f"[green]●[/green] Found {runs} runs [dim](avg {avg_dist_mi:.1f} mi / {avg_dist_km:.1f} km)[/dim]")

        if "avg_pace_min_km" in fitness_data:
            pace_str = format_pace(fitness_data['avg_pace_min_km'])
            console.print(f"[green]●[/green] Current avg pace: [bold]{pace_str}[/bold]")
    else:
        console.print("[yellow]●[/yellow] No recent runs found [dim](will base plan on goals)[/dim]")

    console.print()
    console.print()

    console.print("[dim]Race distances: 5K, 10K, half marathon (13.1 mi), marathon (26.2 mi)[/dim]")
    distance = Prompt.ask("[bold]What distance is your race?[/bold]")
    if not distance:
        console.print("[red]Error:[/red] Race distance is required")
        sys.exit(1)

    console.print()

    console.print("[dim]Pace examples: 8:00/mi, 7:30/mi, 5:00/km[/dim]")
    goal_pace = Prompt.ask("[bold]What is your goal pace?[/bold]")
    if not goal_pace:
        console.print("[red]Error:[/red] Goal pace is required")
        sys.exit(1)

    console.print()

    race_date = Prompt.ask("[bold]When is your race?[/bold] [dim](YYYY-MM-DD)[/dim]")
    if not race_date:
        console.print("[red]Error:[/red] Race date is required")
        sys.exit(1)

    console.print()

    long_run_day = Prompt.ask("[bold]What day do you prefer for long runs?[/bold]", default="Saturday")

    console.print()
    console.print()

    with Status("[bold]Generating your personalized training plan...", spinner="dots", console=console):
        try:
            training_plan = generate_training_plan(fitness_data, distance, goal_pace, race_date, long_run_day)
        except Exception as e:
            console.print(f"\n[red]Error:[/red] Failed to generate plan: {e}")
            sys.exit(1)

    console.print(f"[green]●[/green] Generated {len(training_plan)} workouts")

    console.print()
    console.print("[bold]Uploading to Garmin Connect...[/bold]")
    console.print()

    created_count = garmin.push_all_workouts(training_plan, console)

    console.print()
    console.print()
    console.print(Panel.fit(
        f"[green bold]Success![/green bold]\n\n"
        f"[bold]{created_count}[/bold] workouts uploaded to Garmin Connect\n\n"
        f"[dim]Sync your watch to see your training plan[/dim]",
        border_style="green",
    ))
    console.print()


if __name__ == "__main__":
    main()
