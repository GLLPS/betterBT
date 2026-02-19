"""Microsoft Graph client for fetching Outlook calendar data."""

from datetime import datetime, timedelta
from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.users.item.calendar_view.calendar_view_request_builder import (
    CalendarViewRequestBuilder,
)
from msgraph.generated.users.item.calendar.get_schedule.get_schedule_post_request_body import (
    GetSchedulePostRequestBody,
)
from msgraph.generated.models.date_time_time_zone import DateTimeTimeZone
from config import AzureConfig


class OutlookClient:
    """Client for Microsoft Graph calendar APIs."""

    def __init__(self):
        if not all([AzureConfig.TENANT_ID, AzureConfig.CLIENT_ID, AzureConfig.CLIENT_SECRET]):
            raise ValueError(
                "Missing Azure credentials. "
                "Set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET in .env"
            )

        credential = ClientSecretCredential(
            tenant_id=AzureConfig.TENANT_ID,
            client_id=AzureConfig.CLIENT_ID,
            client_secret=AzureConfig.CLIENT_SECRET,
        )
        self.client = GraphServiceClient(
            credentials=credential,
            scopes=["https://graph.microsoft.com/.default"],
        )
        self.users = AzureConfig.OUTLOOK_USERS

    async def get_calendar_events(self, user_email, start_date=None, end_date=None):
        """Fetch calendar events for a user within a date range.

        Args:
            user_email: The user's email address.
            start_date: Start of range (datetime). Defaults to today.
            end_date: End of range (datetime). Defaults to 2 weeks from today.

        Returns:
            List of event dicts with subject, start, end, is_all_day.
        """
        if start_date is None:
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if end_date is None:
            end_date = start_date + timedelta(days=14)

        query_params = CalendarViewRequestBuilder.CalendarViewRequestBuilderGetQueryParameters(
            start_date_time=start_date.strftime("%Y-%m-%dT%H:%M:%S"),
            end_date_time=end_date.strftime("%Y-%m-%dT%H:%M:%S"),
            orderby=["start/dateTime"],
            select=["subject", "start", "end", "isAllDay", "showAs", "categories"],
            top=500,
        )
        config = CalendarViewRequestBuilder.CalendarViewRequestBuilderGetRequestConfiguration(
            query_parameters=query_params,
        )
        config.headers.add("Prefer", 'outlook.timezone="Eastern Standard Time"')

        result = await self.client.users.by_user_id(user_email).calendar_view.get(
            request_configuration=config,
        )

        events = []
        if result and result.value:
            for event in result.value:
                start_dt = event.start.date_time if event.start else None
                end_dt = event.end.date_time if event.end else None
                events.append({
                    "subject": event.subject or "(No subject)",
                    "start": start_dt,
                    "end": end_dt,
                    "is_all_day": event.is_all_day or False,
                    "show_as": event.show_as.value if event.show_as else "busy",
                    "categories": [c for c in (event.categories or [])],
                })
        return events

    async def get_user_schedule(self, user_emails=None, start_date=None, end_date=None,
                                interval_minutes=60):
        """Get free/busy schedule for multiple users.

        Args:
            user_emails: List of emails. Defaults to configured OUTLOOK_USERS.
            start_date: Start datetime. Defaults to today.
            end_date: End datetime. Defaults to 2 weeks from today.
            interval_minutes: Slot size in minutes (default 60).

        Returns:
            Dict mapping email -> list of schedule slots.
        """
        if user_emails is None:
            user_emails = self.users
        if start_date is None:
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if end_date is None:
            end_date = start_date + timedelta(days=14)

        request_body = GetSchedulePostRequestBody()
        request_body.schedules = user_emails

        start_tz = DateTimeTimeZone()
        start_tz.date_time = start_date.strftime("%Y-%m-%dT%H:%M:%S")
        start_tz.time_zone = "Eastern Standard Time"
        request_body.start_time = start_tz

        end_tz = DateTimeTimeZone()
        end_tz.date_time = end_date.strftime("%Y-%m-%dT%H:%M:%S")
        end_tz.time_zone = "Eastern Standard Time"
        request_body.end_time = end_tz

        request_body.availability_view_interval = interval_minutes

        # Use the first configured user as the caller
        caller = user_emails[0] if user_emails else self.users[0]
        result = await self.client.users.by_user_id(caller).calendar.get_schedule.post(
            request_body,
        )

        schedules = {}
        if result and result.value:
            for schedule_info in result.value:
                email = schedule_info.schedule_id or ""
                availability = schedule_info.availability_view or ""
                items = []
                for item in (schedule_info.schedule_items or []):
                    items.append({
                        "status": item.status.value if item.status else "unknown",
                        "subject": getattr(item, "subject", None) or "",
                        "start": item.start.date_time if item.start else None,
                        "end": item.end.date_time if item.end else None,
                    })
                schedules[email] = {
                    "availability_view": availability,
                    "items": items,
                }
        return schedules

    async def get_all_user_events(self, start_date=None, end_date=None):
        """Fetch calendar events for all configured users.

        Returns:
            Dict mapping email -> list of event dicts.
        """
        all_events = {}
        for user_email in self.users:
            try:
                events = await self.get_calendar_events(user_email, start_date, end_date)
                all_events[user_email] = events
            except Exception as e:
                all_events[user_email] = {"error": str(e)}
        return all_events

    def calculate_booked_hours(self, events, work_day_start=8, work_day_end=17):
        """Calculate total booked hours from a list of calendar events.

        Counts only events during work hours (default 8am-5pm).
        Skips free/tentative events.

        Args:
            events: List of event dicts from get_calendar_events.
            work_day_start: Work day start hour (default 8).
            work_day_end: Work day end hour (default 17).

        Returns:
            Dict with daily_hours (date -> hours) and total_hours.
        """
        daily_hours = {}

        for event in events:
            if isinstance(event, dict) and "error" in event:
                continue

            show_as = event.get("show_as", "busy")
            if show_as in ("free", "tentative"):
                continue

            try:
                start = datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(event["end"].replace("Z", "+00:00"))
            except (ValueError, TypeError, KeyError):
                continue

            if event.get("is_all_day"):
                date_key = start.strftime("%Y-%m-%d")
                daily_hours[date_key] = daily_hours.get(date_key, 0) + (work_day_end - work_day_start)
                continue

            # Clamp to work hours
            effective_start = max(start.hour + start.minute / 60, work_day_start)
            effective_end = min(end.hour + end.minute / 60, work_day_end)
            duration = max(0, effective_end - effective_start)

            if duration > 0:
                date_key = start.strftime("%Y-%m-%d")
                daily_hours[date_key] = daily_hours.get(date_key, 0) + duration

        total = sum(daily_hours.values())
        return {"daily_hours": daily_hours, "total_hours": total}
