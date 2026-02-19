"""Data processing: aggregates Outlook calendar events into weekly staffing views."""

import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd

from outlook_client import OutlookClient


async def fetch_outlook_data(outlook_client, start_date, end_date):
    """Fetch calendar events for all configured users.

    Returns:
        events_by_user: Dict of email -> list of event dicts.
        hours_by_user: Dict of email -> {daily_hours, total_hours}.
    """
    events_by_user = await outlook_client.get_all_user_events(start_date, end_date)

    hours_by_user = {}
    for email, events in events_by_user.items():
        if isinstance(events, dict) and "error" in events:
            hours_by_user[email] = {"daily_hours": {}, "total_hours": 0, "error": events["error"]}
        else:
            hours_by_user[email] = outlook_client.calculate_booked_hours(events)

    return events_by_user, hours_by_user


def _get_week_mondays(start_date, end_date):
    """Generate a list of Monday dates covering start_date through end_date."""
    # Roll start back to its Monday
    current = start_date - timedelta(days=start_date.weekday())
    mondays = []
    while current < end_date:
        mondays.append(current)
        current += timedelta(weeks=1)
    return mondays


def _workdays_in_week(monday, start_date, end_date):
    """Count workdays (Mon-Fri) in a given week, clamped to the overall range."""
    count = 0
    for d in range(5):  # Mon-Fri
        day = monday + timedelta(days=d)
        if start_date <= day < end_date:
            count += 1
    return count


def build_weekly_hours(hours_by_user, start_date, end_date, hours_per_day=8):
    """Aggregate daily booked hours into weekly buckets per person.

    Returns a DataFrame with columns:
        week_of (Monday date), staff, email, booked_hrs, capacity_hrs,
        available_hrs, utilization_pct
    """
    mondays = _get_week_mondays(start_date, end_date)
    rows = []

    for email, data in hours_by_user.items():
        if data.get("error"):
            continue

        daily = data.get("daily_hours", {})
        name = email.split("@")[0].replace(".", " ").title()

        for monday in mondays:
            workdays = _workdays_in_week(monday, start_date, end_date)
            capacity = workdays * hours_per_day

            # Sum booked hours for Mon-Fri of this week
            booked = 0.0
            for d in range(5):
                day_str = (monday + timedelta(days=d)).strftime("%Y-%m-%d")
                booked += daily.get(day_str, 0)

            available = max(0, capacity - booked)
            util = (booked / capacity * 100) if capacity > 0 else 0

            rows.append({
                "week_of": monday.strftime("%Y-%m-%d"),
                "week_label": f"{monday.strftime('%b %d')}",
                "staff": name,
                "email": email,
                "booked_hrs": round(booked, 1),
                "capacity_hrs": capacity,
                "available_hrs": round(available, 1),
                "utilization_pct": round(util, 1),
            })

    return pd.DataFrame(rows)


def build_team_weekly_summary(weekly_df):
    """Aggregate individual weekly data into team-level weekly totals.

    Returns a DataFrame with one row per week: total booked, capacity,
    available, avg utilization.
    """
    if weekly_df.empty:
        return pd.DataFrame()

    grouped = weekly_df.groupby(["week_of", "week_label"], sort=True).agg(
        team_booked=("booked_hrs", "sum"),
        team_capacity=("capacity_hrs", "sum"),
        team_available=("available_hrs", "sum"),
        staff_count=("staff", "count"),
    ).reset_index()

    grouped["avg_utilization"] = (
        grouped["team_booked"] / grouped["team_capacity"] * 100
    ).round(1)

    return grouped


def build_weekly_heatmap_data(weekly_df):
    """Pivot weekly data into a staff x week matrix of utilization %.

    Returns (staff_names, week_labels, z_values) ready for a heatmap.
    """
    if weekly_df.empty:
        return [], [], []

    pivot = weekly_df.pivot_table(
        index="staff", columns="week_label", values="utilization_pct",
        aggfunc="first",
    )
    # Preserve chronological week order
    week_order = weekly_df.drop_duplicates("week_label")["week_label"].tolist()
    pivot = pivot.reindex(columns=week_order)

    return pivot.index.tolist(), pivot.columns.tolist(), pivot.values.tolist()


def build_overall_staff_summary(weekly_df):
    """Per-person summary across the full period.

    Returns a DataFrame with one row per person: total booked, capacity,
    avg utilization.
    """
    if weekly_df.empty:
        return pd.DataFrame()

    grouped = weekly_df.groupby(["staff", "email"]).agg(
        total_booked=("booked_hrs", "sum"),
        total_capacity=("capacity_hrs", "sum"),
        total_available=("available_hrs", "sum"),
        weeks=("week_of", "count"),
    ).reset_index()

    grouped["avg_utilization"] = (
        grouped["total_booked"] / grouped["total_capacity"] * 100
    ).round(1)

    return grouped.sort_values("avg_utilization", ascending=False)


def build_daily_availability(hours_by_user, start_date, end_date, hours_per_day=8):
    """Build a per-person, per-day availability table.

    Returns a DataFrame with columns:
        date, day_name, staff, email, booked_hrs, capacity_hrs, available_hrs, is_free
    Only includes weekdays (Mon-Fri).
    """
    rows = []
    current = start_date
    while current < end_date:
        if current.weekday() < 5:  # Mon-Fri
            for email, data in hours_by_user.items():
                if data.get("error"):
                    continue
                daily = data.get("daily_hours", {})
                name = email.split("@")[0].replace(".", " ").title()
                day_str = current.strftime("%Y-%m-%d")
                booked = daily.get(day_str, 0)
                available = max(0, hours_per_day - booked)
                rows.append({
                    "date": current,
                    "date_str": day_str,
                    "day_name": current.strftime("%A"),
                    "month": current.strftime("%B"),
                    "month_num": current.month,
                    "year": current.year,
                    "staff": name,
                    "email": email,
                    "booked_hrs": round(booked, 1),
                    "capacity_hrs": hours_per_day,
                    "available_hrs": round(available, 1),
                    "is_free": booked < 1,  # Less than 1 hour booked = essentially free
                })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def query_availability(daily_df, day_name=None, month_name=None, full_day=True,
                       min_available_hrs=None):
    """Filter daily availability to answer questions like
    'who has a full Thursday available in March'.

    Args:
        daily_df: DataFrame from build_daily_availability.
        day_name: e.g. "Thursday" (optional, None = any day).
        month_name: e.g. "March" (optional, None = any month).
        full_day: If True, only return days where is_free is True.
        min_available_hrs: Alternative to full_day — minimum free hours.

    Returns:
        Filtered DataFrame.
    """
    if daily_df.empty:
        return daily_df

    filtered = daily_df.copy()

    if day_name:
        filtered = filtered[filtered["day_name"].str.lower() == day_name.lower()]

    if month_name:
        filtered = filtered[filtered["month"].str.lower() == month_name.lower()]

    if min_available_hrs is not None:
        filtered = filtered[filtered["available_hrs"] >= min_available_hrs]
    elif full_day:
        filtered = filtered[filtered["is_free"]]

    return filtered.sort_values(["date", "staff"])


def parse_availability_query(query):
    """Parse a natural-language availability query into structured filters.

    Handles queries like:
        'who has a full Thursday available in March'
        'who is free on Fridays in April'
        'available Mondays March'

    Returns:
        dict with keys: day_name, month_name, full_day, min_hours
    """
    q = query.lower().strip()
    result = {"day_name": None, "month_name": None, "full_day": True, "min_hours": None}

    days = {
        "monday": "Monday", "tuesday": "Tuesday", "wednesday": "Wednesday",
        "thursday": "Thursday", "friday": "Friday",
        "mondays": "Monday", "tuesdays": "Tuesday", "wednesdays": "Wednesday",
        "thursdays": "Thursday", "fridays": "Friday",
    }
    for key, val in days.items():
        if key in q:
            result["day_name"] = val
            break

    months = {
        "january": "January", "february": "February", "march": "March",
        "april": "April", "may": "May", "june": "June",
        "july": "July", "august": "August", "september": "September",
        "october": "October", "november": "November", "december": "December",
    }
    for key, val in months.items():
        if key in q:
            result["month_name"] = val
            break

    # Check for "half day" or hour thresholds
    if "half" in q:
        result["full_day"] = False
        result["min_hours"] = 4
    elif "full" in q or "whole" in q or "entire" in q or "all day" in q:
        result["full_day"] = True
    else:
        # Default: show anyone with 4+ hours free
        result["full_day"] = False
        result["min_hours"] = 4

    return result


def load_calendar_data(outlook_client, start_date, end_date, hours_per_day=8):
    """Main entry point: fetch Outlook data and build all weekly views.

    Returns a dict with all processed data for the dashboard.
    """
    result = {
        "weekly": pd.DataFrame(),
        "team_weekly": pd.DataFrame(),
        "staff_summary": pd.DataFrame(),
        "heatmap": ([], [], []),
        "errors": [],
    }

    try:
        events_by_user, hours_by_user = asyncio.run(
            fetch_outlook_data(outlook_client, start_date, end_date)
        )
    except Exception as e:
        result["errors"].append(f"Outlook API error: {e}")
        return result

    # Check for per-user errors
    for email, data in hours_by_user.items():
        if data.get("error"):
            result["errors"].append(f"{email}: {data['error']}")

    weekly = build_weekly_hours(hours_by_user, start_date, end_date, hours_per_day)
    result["weekly"] = weekly
    result["team_weekly"] = build_team_weekly_summary(weekly)
    result["staff_summary"] = build_overall_staff_summary(weekly)
    result["heatmap"] = build_weekly_heatmap_data(weekly)
    result["daily"] = build_daily_availability(hours_by_user, start_date, end_date, hours_per_day)

    return result
