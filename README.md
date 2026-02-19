# BetterBT — Staffing Dashboard

Pulls active projects from BigTime, compares time budgets against Outlook
calendar availability, and displays a staffing dashboard.

## Features

- **Project Budgets**: View all active BigTime projects with budget hours, hours logged, and hours remaining
- **Staff Utilization**: See each team member's calendar utilization from Outlook
- **Daily Availability**: Heatmap showing available hours per person per day
- **Budget vs. Capacity**: Compare total project hours remaining against total staff availability

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials (see sections below).

### 3. Run the dashboard

```bash
streamlit run app.py
```

## BigTime Setup

You need either a **firm API token** (recommended) or user credentials.

### Firm API Token (permanent)
1. Log into BigTime as a system admin
2. Go to admin settings and create a firm access token
3. Set `BIGTIME_API_TOKEN` and `BIGTIME_FIRM_ID` in `.env`

### User Credentials (expires after 7 days)
1. Set `BIGTIME_USERNAME` and `BIGTIME_PASSWORD` in `.env`

## Outlook / Microsoft Graph Setup

1. Go to [Azure Portal](https://portal.azure.com) > App registrations > New registration
2. Copy the **Application (client) ID** and **Directory (tenant) ID**
3. Under Certificates & secrets, create a new client secret
4. Under API permissions, add these **Application** permissions:
   - `Calendars.Read`
   - `Schedule.Read.All`
5. Click **Grant admin consent**
6. Set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` in `.env`
7. Set `OUTLOOK_USERS` to a comma-separated list of staff email addresses

## Project Structure

```
app.py              — Streamlit dashboard (entry point)
bigtime_client.py   — BigTime REST API v2 client
outlook_client.py   — Microsoft Graph calendar client
data_processor.py   — Merges BigTime + Outlook data
config.py           — Loads settings from .env
.env.example        — Template for environment variables
```
