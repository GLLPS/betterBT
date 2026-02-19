# BetterBT — Team Calendar Dashboard

Connects to your team's Outlook calendars via Microsoft Graph and shows
how busy everyone is on a **weekly basis** over the next few months.

## Features

- **Team Overview**: stacked bar chart of booked vs. available hours per week, with a utilization % trend line
- **Who's Busy When**: color-coded heatmap (person x week) — green = free, red = slammed
- **Individual Staff**: per-person utilization bar, summary table, and weekly drill-down
- Configurable look-ahead (1–6 months) and work-hours-per-day

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

Edit `.env` with your Azure app registration details and team emails.

### 3. Run the dashboard

```bash
streamlit run app.py
```

## Outlook / Microsoft Graph Setup

1. Go to [Azure Portal](https://portal.azure.com) > Microsoft Entra ID > App registrations > **New registration**
2. Copy the **Application (client) ID** and **Directory (tenant) ID**
3. Under **Certificates & secrets**, create a new client secret
4. Under **API permissions**, add these **Application** permissions:
   - `Calendars.Read`
   - `Schedule.Read.All`
5. Click **Grant admin consent**
6. Fill in `.env`:
   - `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`
   - `OUTLOOK_USERS` — comma-separated list of staff email addresses to track

## Project Structure

```
app.py              — Streamlit dashboard (entry point)
outlook_client.py   — Microsoft Graph calendar client
data_processor.py   — Weekly aggregation and summaries
config.py           — Loads settings from .env
.env.example        — Template for environment variables
bigtime_client.py   — BigTime API client (on hold, for future use)
```
