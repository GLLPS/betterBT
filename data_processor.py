"""Data processing layer: merges BigTime project/budget data with Outlook calendar data."""

import asyncio
from datetime import datetime, timedelta
import pandas as pd

from bigtime_client import BigTimeClient
from outlook_client import OutlookClient


def fetch_bigtime_data(bt_client):
    """Fetch and structure all BigTime project + budget data.

    Returns a DataFrame with one row per project.
    """
    summaries = bt_client.get_all_project_summaries()

    rows = []
    for proj in summaries:
        rows.append({
            "project_id": proj["ProjectSid"],
            "project_name": proj["ProjectName"],
            "project_code": proj["ProjectCode"],
            "start_date": proj["StartDate"],
            "end_date": proj["EndDate"],
            "budget_hours": proj["BudgetHours"],
            "hours_logged": proj["HoursLogged"],
            "hours_remaining": proj["HoursRemaining"],
            "task_count": len(proj["Tasks"]),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        for col in ["start_date", "end_date"]:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


async def fetch_outlook_data(outlook_client, start_date=None, end_date=None):
    """Fetch and structure Outlook calendar data for all configured users.

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


def build_staffing_summary(hours_by_user, num_workdays=10, hours_per_day=8):
    """Build a staffing summary from Outlook calendar data.

    Args:
        hours_by_user: Dict from fetch_outlook_data.
        num_workdays: Number of workdays in the period.
        hours_per_day: Work hours per day.

    Returns:
        DataFrame with columns: staff, booked_hours, available_hours, utilization_pct.
    """
    total_capacity = num_workdays * hours_per_day
    rows = []

    for email, data in hours_by_user.items():
        booked = data.get("total_hours", 0)
        available = max(0, total_capacity - booked)
        utilization = (booked / total_capacity * 100) if total_capacity > 0 else 0

        rows.append({
            "staff": email.split("@")[0].replace(".", " ").title(),
            "email": email,
            "booked_hours": round(booked, 1),
            "available_hours": round(available, 1),
            "capacity_hours": total_capacity,
            "utilization_pct": round(utilization, 1),
            "error": data.get("error"),
        })

    return pd.DataFrame(rows)


def build_project_vs_capacity(project_df, staffing_df):
    """Compare project hours remaining against available staff capacity.

    Returns a summary dict.
    """
    total_budget_remaining = project_df["hours_remaining"].sum() if not project_df.empty else 0
    total_available = staffing_df["available_hours"].sum() if not staffing_df.empty else 0
    staff_count = len(staffing_df) if not staffing_df.empty else 0

    gap = total_available - total_budget_remaining

    return {
        "total_project_hours_remaining": round(total_budget_remaining, 1),
        "total_staff_available_hours": round(total_available, 1),
        "capacity_gap": round(gap, 1),
        "gap_status": "Over capacity" if gap < 0 else "Under capacity",
        "staff_count": staff_count,
        "project_count": len(project_df) if not project_df.empty else 0,
    }


def get_daily_availability(hours_by_user, start_date=None, num_days=10, hours_per_day=8):
    """Build a daily availability table across all staff.

    Returns a DataFrame with dates as rows, staff as columns,
    values = available hours that day.
    """
    if start_date is None:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    dates = []
    current = start_date
    for _ in range(num_days):
        if current.weekday() < 5:  # Monday-Friday
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
        # Keep going until we have enough workdays
        while current.weekday() >= 5:
            current += timedelta(days=1)

    rows = []
    for date_str in dates:
        row = {"date": date_str}
        for email, data in hours_by_user.items():
            name = email.split("@")[0].replace(".", " ").title()
            booked = data.get("daily_hours", {}).get(date_str, 0)
            row[name] = round(max(0, hours_per_day - booked), 1)
        rows.append(row)

    return pd.DataFrame(rows)


def load_all_data(bt_client=None, outlook_client=None, start_date=None, end_date=None):
    """Main entry point: load all data from both sources.

    Returns a dict with all processed data ready for the dashboard.
    """
    result = {
        "projects": pd.DataFrame(),
        "staffing": pd.DataFrame(),
        "daily_availability": pd.DataFrame(),
        "capacity_summary": {},
        "hours_by_user": {},
        "events_by_user": {},
        "errors": [],
    }

    # BigTime data
    if bt_client:
        try:
            result["projects"] = fetch_bigtime_data(bt_client)
        except Exception as e:
            result["errors"].append(f"BigTime error: {e}")

    # Outlook data
    if outlook_client:
        try:
            events_by_user, hours_by_user = asyncio.run(
                fetch_outlook_data(outlook_client, start_date, end_date)
            )
            result["events_by_user"] = events_by_user
            result["hours_by_user"] = hours_by_user
            result["staffing"] = build_staffing_summary(hours_by_user)
            result["daily_availability"] = get_daily_availability(hours_by_user, start_date)
        except Exception as e:
            result["errors"].append(f"Outlook error: {e}")

    # Cross-source comparison
    if not result["projects"].empty and not result["staffing"].empty:
        result["capacity_summary"] = build_project_vs_capacity(
            result["projects"], result["staffing"]
        )

    return result
