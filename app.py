from __future__ import annotations

import streamlit as st
import plotly.express as px

from utils import (
    activity_summary,
    calculate_kpis,
    format_count_pct,
    prepare_attendance_data,
    read_excel_all_sheets,
)

st.set_page_config(page_title="GLOW KPI Dashboard", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    .main .block-container { padding-top: 2rem; }
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 18px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        min-height: 108px;
    }
    .kpi-label { color: #64748b; font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
    .kpi-value { color: #0f172a; font-size: 1.75rem; font-weight: 800; margin-top: 6px; }
    .note-box {
        background: #fff7ed;
        border: 1px solid #fed7aa;
        color: #7c2d12;
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📊 GLOW KPI Dashboard")
st.caption("Upload attendance Excel files and generate centre KPI summaries.")

st.markdown(
    """
    <div class="note-box">
    <b>Inactive rule used here:</b> seniors with <b>2 or fewer attended records</b> are counted as inactive. Seniors with <b>3 or more attended records</b> are not inactive.
    </div>
    """,
    unsafe_allow_html=True,
)

uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx", "xls"])

if not uploaded_file:
    st.info("Upload your attendance Excel file to begin.")
    st.stop()

try:
    raw_df = read_excel_all_sheets(uploaded_file)
    df = prepare_attendance_data(raw_df)
except Exception as exc:
    st.error(f"Could not read the file: {exc}")
    st.stop()

if df.empty:
    st.warning("No usable member rows were found in the uploaded file.")
    st.stop()

centres = sorted([c for c in df["centre"].dropna().unique() if str(c).strip()])
selected_centre = st.sidebar.selectbox("Centre", ["All Centres"] + centres)

if selected_centre != "All Centres":
    df = df[df["centre"] == selected_centre].copy()

if "date" in df.columns and df["date"].notna().any():
    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        df = df[(df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)].copy()

kpis, attended, members = calculate_kpis(df)
activities = activity_summary(attended)

st.subheader("Mandatory KPIs")
cols = st.columns(5)
metrics = [
    ("Programmes", kpis["Programmes"]),
    ("Attendances", kpis["Attendances"]),
    ("Unique Members", kpis["Unique Members"]),
    ("IB", format_count_pct(kpis["IB Count"], kpis["IB %"])),
    ("OB", format_count_pct(kpis["OB Count"], kpis["OB %"])),
]
for col, (label, value) in zip(cols, metrics):
    col.markdown(f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>', unsafe_allow_html=True)

cols = st.columns(4)
metrics = [
    ("Male", format_count_pct(kpis["Male Count"], kpis["Male %"])),
    ("Inactive", format_count_pct(kpis["Inactive Count"], kpis["Inactive %"])),
    ("New IB", "Add source column if needed"),
    ("New OB", "Add source column if needed"),
]
for col, (label, value) in zip(cols, metrics):
    col.markdown(f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-value" style="font-size:1.25rem">{value}</div></div>', unsafe_allow_html=True)

st.divider()

left, right = st.columns(2)
with left:
    st.subheader("Top Activities by Attendance")
    if not activities.empty:
        fig = px.bar(activities.head(10), x="Activity", y="Attendances", text="Attendances")
        fig.update_layout(xaxis_tickangle=-35, height=420, margin=dict(l=10, r=10, t=20, b=90))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No activity data available.")

with right:
    st.subheader("Unique Members by Activity")
    if not activities.empty:
        fig = px.bar(activities.head(10), x="Activity", y="Unique Members", text="Unique Members")
        fig.update_layout(xaxis_tickangle=-35, height=420, margin=dict(l=10, r=10, t=20, b=90))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No activity data available.")

st.subheader("Activity Summary")
st.dataframe(activities, use_container_width=True, hide_index=True)

st.subheader("Member Summary")
member_display = members.rename(
    columns={
        "name": "Member",
        "total_records": "Total Records",
        "last_attendance": "Last Attendance",
        "gender": "Gender",
        "is_client": "Is Client",
        "aap": "Imported AAP Field",
        "inactive": "Inactive Based on Records <= 2",
    }
)
st.dataframe(member_display, use_container_width=True, hide_index=True)

st.download_button(
    "Download Member Summary CSV",
    data=member_display.to_csv(index=False).encode("utf-8-sig"),
    file_name="member_summary.csv",
    mime="text/csv",
)

st.download_button(
    "Download Activity Summary CSV",
    data=activities.to_csv(index=False).encode("utf-8-sig"),
    file_name="activity_summary.csv",
    mime="text/csv",
)
