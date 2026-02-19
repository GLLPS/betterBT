"""BetterBT — Team Calendar Dashboard

Connects to Outlook calendars and shows how busy the team is
on a weekly basis over the coming months.

Run with: streamlit run app.py
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

from config import AzureConfig
from outlook_client import OutlookClient
from data_processor import load_calendar_data

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="BetterBT — Team Calendar",
    page_icon="📅",
    layout="wide",
)

st.title("BetterBT — Team Calendar")
st.caption("Weekly staffing view from Outlook calendars")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")

    months_ahead = st.slider("Months to look ahead", 1, 6, 3)
    hours_per_day = st.number_input("Work hours per day", 4, 12, 8)

    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(weeks=months_ahead * 4 + 1)

    st.divider()

    outlook_ok = all([AzureConfig.TENANT_ID, AzureConfig.CLIENT_ID, AzureConfig.CLIENT_SECRET])
    st.subheader("Connection")
    if outlook_ok:
        st.success("Outlook credentials configured")
    else:
        st.error("Outlook not configured")

    if AzureConfig.OUTLOOK_USERS:
        st.write(f"**{len(AzureConfig.OUTLOOK_USERS)} staff** tracked:")
        for u in AzureConfig.OUTLOOK_USERS:
            st.write(f"- {u}")
    else:
        st.warning("No staff emails in OUTLOOK_USERS")

    st.divider()
    refresh = st.button("Refresh Data", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if not outlook_ok:
    st.warning(
        "Outlook credentials not configured. "
        "Copy `.env.example` to `.env`, fill in your Azure app credentials "
        "and staff emails, then restart."
    )
    st.stop()

if not AzureConfig.OUTLOOK_USERS:
    st.warning(
        "No staff emails configured. Add a comma-separated list to "
        "`OUTLOOK_USERS` in your `.env` file."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner="Fetching calendars...")
def cached_load(_months, _hours_per_day):
    s = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    e = s + timedelta(weeks=_months * 4 + 1)
    client = OutlookClient()
    return load_calendar_data(client, s, e, _hours_per_day)


if refresh:
    st.cache_data.clear()

data = cached_load(months_ahead, hours_per_day)

for err in data["errors"]:
    st.error(err)

weekly_df = data["weekly"]
team_df = data["team_weekly"]
staff_df = data["staff_summary"]
staff_names, week_labels, heatmap_z = data["heatmap"]

if weekly_df.empty:
    st.info("No calendar data returned. Verify credentials and staff list.")
    st.stop()

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
num_weeks = len(team_df) if not team_df.empty else 0
avg_util = team_df["avg_utilization"].mean() if not team_df.empty else 0
total_booked = staff_df["total_booked"].sum() if not staff_df.empty else 0
total_avail = staff_df["total_available"].sum() if not staff_df.empty else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Staff", len(AzureConfig.OUTLOOK_USERS))
k2.metric("Weeks Shown", num_weeks)
k3.metric("Avg Team Utilization", f"{avg_util:.0f}%")
k4.metric("Total Available Hours", f"{total_avail:,.0f}")

st.divider()

# ---------------------------------------------------------------------------
# Main content: two tabs
# ---------------------------------------------------------------------------
tab_team, tab_people = st.tabs(["Team Overview", "Individual Staff"])

# ====== Tab 1: Team Overview ===============================================
with tab_team:

    # --- Team utilization trend line ---
    st.subheader("Team Utilization by Week")
    if not team_df.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=team_df["week_label"],
            y=team_df["team_booked"],
            name="Booked Hours",
            marker_color="#636EFA",
        ))
        fig.add_trace(go.Bar(
            x=team_df["week_label"],
            y=team_df["team_available"],
            name="Available Hours",
            marker_color="#2ecc71",
        ))
        fig.add_trace(go.Scatter(
            x=team_df["week_label"],
            y=team_df["avg_utilization"],
            name="Utilization %",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#e74c3c", width=2),
            marker=dict(size=6),
        ))
        fig.update_layout(
            barmode="stack",
            yaxis=dict(title="Hours"),
            yaxis2=dict(title="Utilization %", overlaying="y", side="right",
                        range=[0, 100], showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            height=400,
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- Heatmap: person x week ---
    st.subheader("Who's Busy When")
    if staff_names and week_labels:
        fig = go.Figure(data=go.Heatmap(
            z=heatmap_z,
            x=week_labels,
            y=staff_names,
            colorscale=[
                [0, "#2ecc71"],      # 0% = green (free)
                [0.5, "#f1c40f"],    # 50% = yellow
                [0.8, "#e67e22"],    # 80% = orange
                [1, "#e74c3c"],      # 100% = red (slammed)
            ],
            zmin=0,
            zmax=100,
            text=[[f"{v:.0f}%" for v in row] for row in heatmap_z],
            texttemplate="%{text}",
            colorbar_title="Util %",
            hovertemplate="<b>%{y}</b><br>Week of %{x}<br>Utilization: %{z:.0f}%<extra></extra>",
        ))
        fig.update_layout(
            height=max(300, len(staff_names) * 45 + 80),
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(side="top"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- Weekly detail table ---
    with st.expander("Weekly numbers"):
        if not team_df.empty:
            display = team_df[[
                "week_label", "team_booked", "team_capacity",
                "team_available", "staff_count", "avg_utilization",
            ]].copy()
            display.columns = [
                "Week Of", "Booked Hrs", "Capacity Hrs",
                "Available Hrs", "Staff", "Avg Util %",
            ]
            st.dataframe(display, use_container_width=True, hide_index=True)


# ====== Tab 2: Individual Staff ============================================
with tab_people:

    st.subheader("Staff Summary")

    if not staff_df.empty:
        # Overall bar chart
        sorted_staff = staff_df.sort_values("avg_utilization", ascending=True)
        fig = px.bar(
            sorted_staff,
            y="staff",
            x="avg_utilization",
            orientation="h",
            color="avg_utilization",
            color_continuous_scale=["#2ecc71", "#f1c40f", "#e74c3c"],
            range_color=[0, 100],
            labels={"avg_utilization": "Avg Utilization %", "staff": ""},
        )
        fig.add_vline(x=80, line_dash="dash", line_color="gray",
                       annotation_text="80% target")
        fig.update_layout(
            height=max(300, len(sorted_staff) * 40),
            margin=dict(l=0, r=0, t=30, b=0),
            coloraxis_colorbar_title="Util %",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Summary table
        display = staff_df[[
            "staff", "total_booked", "total_capacity",
            "total_available", "weeks", "avg_utilization",
        ]].copy()
        display.columns = [
            "Staff", "Booked Hrs", "Capacity Hrs",
            "Available Hrs", "Weeks", "Avg Util %",
        ]
        st.dataframe(display, use_container_width=True, hide_index=True)

    # Per-person weekly breakdown
    st.subheader("Weekly Breakdown by Person")

    if not weekly_df.empty:
        selected = st.selectbox(
            "Select staff member",
            options=sorted(weekly_df["staff"].unique()),
        )
        person_df = weekly_df[weekly_df["staff"] == selected]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=person_df["week_label"],
            y=person_df["booked_hrs"],
            name="Booked",
            marker_color="#636EFA",
        ))
        fig.add_trace(go.Bar(
            x=person_df["week_label"],
            y=person_df["available_hrs"],
            name="Available",
            marker_color="#2ecc71",
        ))
        fig.update_layout(
            barmode="stack",
            yaxis_title="Hours",
            height=350,
            margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander(f"{selected} — weekly detail"):
            detail = person_df[[
                "week_label", "booked_hrs", "capacity_hrs",
                "available_hrs", "utilization_pct",
            ]].copy()
            detail.columns = [
                "Week Of", "Booked Hrs", "Capacity Hrs",
                "Available Hrs", "Utilization %",
            ]
            st.dataframe(detail, use_container_width=True, hide_index=True)
