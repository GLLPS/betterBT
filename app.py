"""BetterBT — Staffing Dashboard

Pulls active projects from BigTime, compares time budgets against
Outlook calendar availability, and displays a staffing dashboard.

Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from config import BigTimeConfig, AzureConfig
from bigtime_client import BigTimeClient
from outlook_client import OutlookClient
from data_processor import load_all_data

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="BetterBT — Staffing Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("BetterBT — Staffing Dashboard")
st.caption("BigTime project budgets vs. Outlook calendar availability")

# ---------------------------------------------------------------------------
# Sidebar — configuration & refresh
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")

    weeks_ahead = st.slider("Weeks to look ahead", 1, 8, 2)
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(weeks=weeks_ahead)

    hours_per_day = st.number_input("Work hours per day", 4, 12, 8)

    st.divider()

    # Connection status indicators
    bt_ok = bool(BigTimeConfig.API_TOKEN and BigTimeConfig.FIRM_ID) or bool(
        BigTimeConfig.USERNAME and BigTimeConfig.PASSWORD
    )
    outlook_ok = all([AzureConfig.TENANT_ID, AzureConfig.CLIENT_ID, AzureConfig.CLIENT_SECRET])

    st.subheader("Connections")
    st.write(f"BigTime: {'Connected' if bt_ok else 'Not configured'}")
    st.write(f"Outlook: {'Connected' if outlook_ok else 'Not configured'}")

    if AzureConfig.OUTLOOK_USERS:
        st.write(f"Tracking {len(AzureConfig.OUTLOOK_USERS)} staff")
    else:
        st.write("No staff emails configured")

    st.divider()
    refresh = st.button("Refresh Data", use_container_width=True)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner="Loading data from BigTime & Outlook...")
def cached_load(weeks, _hours_per_day):
    """Load all data, cached for 5 minutes."""
    bt_client = None
    outlook_client = None

    if bt_ok:
        bt_client = BigTimeClient()
        bt_client.authenticate()

    if outlook_ok and AzureConfig.OUTLOOK_USERS:
        outlook_client = OutlookClient()

    s = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    e = s + timedelta(weeks=weeks)

    return load_all_data(bt_client, outlook_client, s, e)


if refresh:
    st.cache_data.clear()

if not bt_ok and not outlook_ok:
    st.warning(
        "No API credentials configured. Copy `.env.example` to `.env` and fill in your credentials, "
        "then restart the app. See the README for setup instructions."
    )
    st.stop()

with st.spinner("Loading data..."):
    data = cached_load(weeks_ahead, hours_per_day)

if data["errors"]:
    for err in data["errors"]:
        st.error(err)

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
projects_df = data["projects"]
staffing_df = data["staffing"]
capacity = data["capacity_summary"]

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Active Projects", len(projects_df) if not projects_df.empty else "—")
with col2:
    st.metric(
        "Total Budget Hours Remaining",
        f"{capacity.get('total_project_hours_remaining', '—'):,}" if capacity else "—",
    )
with col3:
    st.metric(
        "Staff Available Hours",
        f"{capacity.get('total_staff_available_hours', '—'):,}" if capacity else "—",
    )
with col4:
    gap = capacity.get("capacity_gap")
    if gap is not None:
        st.metric(
            "Capacity Gap",
            f"{abs(gap):,.1f} hrs",
            delta=f"{'Under' if gap >= 0 else 'Over'} capacity",
            delta_color="normal" if gap >= 0 else "inverse",
        )
    else:
        st.metric("Capacity Gap", "—")

st.divider()

# ---------------------------------------------------------------------------
# Tab layout
# ---------------------------------------------------------------------------
tab_projects, tab_staff, tab_daily, tab_compare = st.tabs([
    "Project Budgets", "Staff Utilization", "Daily Availability", "Budget vs. Capacity",
])

# ---------------------------------------------------------------------------
# Tab 1: Project Budgets
# ---------------------------------------------------------------------------
with tab_projects:
    if projects_df.empty:
        st.info("No BigTime project data available. Check your BigTime credentials.")
    else:
        st.subheader("Active Projects — Budget Overview")

        # Budget bar chart
        chart_df = projects_df.sort_values("budget_hours", ascending=True).tail(20)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=chart_df["project_name"],
            x=chart_df["hours_logged"],
            name="Hours Logged",
            orientation="h",
            marker_color="#636EFA",
        ))
        fig.add_trace(go.Bar(
            y=chart_df["project_name"],
            x=chart_df["hours_remaining"],
            name="Hours Remaining",
            orientation="h",
            marker_color="#EF553B",
        ))
        fig.update_layout(
            barmode="stack",
            height=max(400, len(chart_df) * 30),
            margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            xaxis_title="Hours",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Project table
        st.subheader("Project Details")
        display_df = projects_df[[
            "project_name", "project_code", "budget_hours",
            "hours_logged", "hours_remaining", "task_count",
        ]].copy()
        display_df.columns = [
            "Project", "Code", "Budget Hrs", "Logged Hrs", "Remaining Hrs", "Tasks",
        ]
        st.dataframe(
            display_df.sort_values("Remaining Hrs", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

# ---------------------------------------------------------------------------
# Tab 2: Staff Utilization
# ---------------------------------------------------------------------------
with tab_staff:
    if staffing_df.empty:
        st.info("No Outlook calendar data available. Check your Azure/Outlook credentials.")
    else:
        st.subheader(f"Staff Utilization — Next {weeks_ahead} Week(s)")

        # Utilization bar chart
        fig = px.bar(
            staffing_df.sort_values("utilization_pct", ascending=True),
            y="staff",
            x="utilization_pct",
            orientation="h",
            color="utilization_pct",
            color_continuous_scale=["#2ecc71", "#f1c40f", "#e74c3c"],
            range_color=[0, 100],
            labels={"utilization_pct": "Utilization %", "staff": ""},
        )
        fig.update_layout(
            height=max(300, len(staffing_df) * 40),
            margin=dict(l=0, r=0, t=30, b=0),
            coloraxis_colorbar_title="Utilization %",
        )
        fig.add_vline(x=80, line_dash="dash", line_color="gray", annotation_text="80% target")
        st.plotly_chart(fig, use_container_width=True)

        # Staffing table
        st.subheader("Staff Details")
        display_staff = staffing_df[[
            "staff", "booked_hours", "available_hours", "capacity_hours", "utilization_pct",
        ]].copy()
        display_staff.columns = [
            "Staff", "Booked Hrs", "Available Hrs", "Capacity Hrs", "Utilization %",
        ]
        st.dataframe(display_staff, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tab 3: Daily Availability
# ---------------------------------------------------------------------------
with tab_daily:
    daily_df = data["daily_availability"]
    if daily_df.empty:
        st.info("No daily availability data. Check Outlook credentials and staff list.")
    else:
        st.subheader("Daily Available Hours by Staff Member")

        # Heatmap
        date_col = daily_df["date"]
        staff_cols = [c for c in daily_df.columns if c != "date"]
        heatmap_data = daily_df[staff_cols].values.T

        fig = go.Figure(data=go.Heatmap(
            z=heatmap_data,
            x=date_col,
            y=staff_cols,
            colorscale=[[0, "#e74c3c"], [0.5, "#f1c40f"], [1, "#2ecc71"]],
            zmin=0,
            zmax=hours_per_day,
            text=heatmap_data,
            texttemplate="%{text:.1f}",
            colorbar_title="Avail Hrs",
        ))
        fig.update_layout(
            height=max(300, len(staff_cols) * 50),
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis_title="Date",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Raw table
        with st.expander("Raw daily data"):
            st.dataframe(daily_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tab 4: Budget vs. Capacity Comparison
# ---------------------------------------------------------------------------
with tab_compare:
    if projects_df.empty or staffing_df.empty:
        st.info(
            "Need both BigTime and Outlook data for comparison. "
            "Configure both connections in your .env file."
        )
    else:
        st.subheader("Project Budget Hours vs. Staff Capacity")

        # Summary gauges
        c1, c2 = st.columns(2)
        with c1:
            total_remaining = capacity["total_project_hours_remaining"]
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=total_remaining,
                title={"text": "Hours of Work Remaining"},
                gauge={
                    "axis": {"range": [0, max(total_remaining * 1.5, 100)]},
                    "bar": {"color": "#636EFA"},
                },
            ))
            fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=0))
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            total_avail = capacity["total_staff_available_hours"]
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=total_avail,
                title={"text": "Staff Available Hours"},
                gauge={
                    "axis": {"range": [0, max(total_avail * 1.5, 100)]},
                    "bar": {"color": "#2ecc71"},
                },
            ))
            fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=0))
            st.plotly_chart(fig, use_container_width=True)

        # Gap analysis
        gap = capacity["capacity_gap"]
        if gap >= 0:
            st.success(
                f"You have **{gap:,.1f} hours** of spare capacity across "
                f"{capacity['staff_count']} staff for "
                f"{capacity['project_count']} active projects."
            )
        else:
            st.error(
                f"You are **{abs(gap):,.1f} hours over capacity** across "
                f"{capacity['staff_count']} staff for "
                f"{capacity['project_count']} active projects. "
                "Consider reassigning work or extending timelines."
            )

        # Projects ranked by urgency (least remaining hours first)
        st.subheader("Projects by Urgency (least remaining hours)")
        urgent_df = projects_df.nsmallest(10, "hours_remaining")[[
            "project_name", "budget_hours", "hours_logged", "hours_remaining",
        ]].copy()
        urgent_df.columns = ["Project", "Budget Hrs", "Logged Hrs", "Remaining Hrs"]
        st.dataframe(urgent_df, use_container_width=True, hide_index=True)
