import sys
import json
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
import html as html_lib

APP_DIR = Path(__file__).resolve().parent
ANON_STORE_PATH = APP_DIR / "stored_dashboard_values.json"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import utils as utils_module
from utils import (
    read_uploaded_file,
    guess_attended,
    standardize_date,
    infer_recurring_activities,
    classify_programme_type,
    build_recommendations,
)

st.set_page_config(
    page_title="GLOW Programme KPI & Trends Dashboard",
    page_icon="📊",
    layout="wide",
)

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = ["#C45D2D", "#0D2B45", "#6F9CA3", "#D9B27D", "#55623B"]

st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(180deg, #F7F1E7 0%, #FFFDF8 45%, #F7F1E7 100%); }
    .main .block-container { padding-top: 1.5rem; padding-bottom: 3rem; }
    div[data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E9D6B3;
        border-radius: 18px;
        padding: 18px 18px;
        box-shadow: 0 6px 18px rgba(13, 43, 69, 0.08);
    }
    div[data-testid="stMetric"] label { color: #55623B !important; font-weight: 700 !important; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #0D2B45; font-weight: 800; }
    .hero-card {
        background: linear-gradient(135deg, #0D2B45 0%, #164766 60%, #6F9CA3 100%);
        color: white;
        padding: 28px 32px;
        border-radius: 24px;
        margin-bottom: 18px;
        box-shadow: 0 10px 30px rgba(13, 43, 69, 0.20);
    }
    .hero-card h1 { margin: 0; font-size: 2.2rem; line-height: 1.15; }
    .hero-card p { margin: 10px 0 0 0; color: #F3E8D2; font-size: 1rem; }
    .section-card {
        background: #FFFFFF;
        border: 1px solid #E9D6B3;
        border-radius: 20px;
        padding: 18px 20px;
        margin: 10px 0 18px 0;
        box-shadow: 0 5px 18px rgba(13, 43, 69, 0.07);
    }
    .small-note { color: #55623B; font-size: 0.92rem; }
    .success-pill {
        display: inline-block;
        padding: 7px 12px;
        border-radius: 999px;
        background: #E7F1ED;
        color: #0D2B45;
        border: 1px solid #BBD7D2;
        font-weight: 700;
        margin: 4px 4px 4px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero-card">
        <h1>📊 GLOW Programme KPI & Trends Dashboard</h1>
        <p>Upload attendance data, map the columns, and quickly understand attendance, recurring activity trends, male participation, and programme recommendations.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip().str.lower()
    return df


def detect_columns(df: pd.DataFrame) -> dict:
    cols = list(df.columns)

    def find_one(candidates):
        for cand in candidates:
            for col in cols:
                if col == cand:
                    return col
        for cand in candidates:
            for col in cols:
                if cand in col:
                    return col
        return None

    return {
        "activity": find_one(["activity", "activity name", "programme", "program", "program name", "event", "event name", "session"]),
        "member": find_one(["member", "member name", "name", "participant", "participant name", "client", "client name", "senior", "senior name"]),
        "gender": find_one(["gender", "sex"]),
        "age": find_one(["age"]),
        "attendance": find_one(["status", "attendance", "attendance status", "attended"]),
        "kpi": find_one(["has met kpi (cfs)", "kpi", "met kpi"]),
        "date": find_one(["date", "__sheet_date__", "activity date", "session date", "event date", "programme date", "program date", "start date"]),
        "ib_ob": find_one(["ib/ob", "ib_ob", "ib ob", "ibob", "inbound/outbound", "inbound outbound", "client type", "is client"]),
        "capacity": find_one(["capacity", "max capacity", "places", "seats", "limit"]),
    }


def clean_gender(value):
    if pd.isna(value):
        return "Unknown"
    text = str(value).strip().lower()
    if text in {"male", "m", "男", "男性"}:
        return "Male"
    if text in {"female", "f", "女", "女性"}:
        return "Female"
    return "Unknown"


def clean_ib_ob(value):
    if pd.isna(value):
        return "Unknown"
    text = str(value).strip().lower()
    if text in {"ib", "inbound", "i", "incoming", "yes", "y", "true", "1"}:
        return "IB"
    if text in {"ob", "outbound", "o", "outgoing", "no", "n", "false", "0"}:
        return "OB"
    return "Unknown"


def nice_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).replace("_", " ").title() for c in out.columns]
    return out


def get_default_index(options, value):
    try:
        return options.index(value)
    except ValueError:
        return 0


def _format_cell_for_table(value):
    """Format values for the in-app sortable HTML tables."""
    if pd.isna(value):
        return ""
    if isinstance(value, (float, np.floating)):
        if abs(float(value)) <= 1 and float(value) != 0:
            return f"{float(value):.1%}"
        return f"{float(value):,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    return str(value)


def sortable_html_table(df: pd.DataFrame, key: str, height: int = 520):
    """Render a browser-only sortable table so sorting does not rerun Streamlit."""
    table_id = f"sortable_{key}".replace("-", "_").replace(" ", "_")
    safe_df = df.copy().replace({np.nan: ""})
    headers = list(safe_df.columns)

    rows_html = []
    for _, row in safe_df.iterrows():
        cells = []
        for col in headers:
            raw = row[col]
            display = _format_cell_for_table(raw)
            raw_sort = str(raw).replace("%", "").replace(",", "").strip()
            cells.append(
                f'<td data-sort="{html_lib.escape(raw_sort)}">{html_lib.escape(display)}</td>'
            )
        rows_html.append("<tr>" + "".join(cells) + "</tr>")

    header_html = "".join(
        f'<th onclick="sortTable_{table_id}({i})"><span>{html_lib.escape(str(col))}</span><span class="sort-hint">↕</span></th>'
        for i, col in enumerate(headers)
    )

    html_code = f"""
    <style>
      .table-wrap {{
        max-height: {height}px;
        overflow: auto;
        border: 1px solid #E9D6B3;
        border-radius: 14px;
        background: white;
      }}
      #{table_id} {{ width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 14px; }}
      #{table_id} th {{
        position: sticky; top: 0; z-index: 2;
        background: #0D2B45; color: white;
        padding: 10px 12px; text-align: left; cursor: pointer; user-select: none;
        white-space: nowrap;
      }}
      #{table_id} th:hover {{ background: #164766; }}
      #{table_id} td {{ padding: 9px 12px; border-bottom: 1px solid #F0E4D2; color: #1f2937; }}
      #{table_id} tr:nth-child(even) td {{ background: #FFFDF8; }}
      #{table_id} tr:hover td {{ background: #F7F1E7; }}
      .sort-hint {{ opacity: 0.75; margin-left: 8px; font-size: 12px; }}
    </style>
    <div class="table-wrap">
      <table id="{table_id}">
        <thead><tr>{header_html}</tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </div>
    <script>
      const sortState_{table_id} = {{}};
      function cleanValue_{table_id}(txt) {{
        if (txt === null || txt === undefined) return "";
        return String(txt).replace(/,/g, '').replace('%', '').trim();
      }}
      function sortTable_{table_id}(colIndex) {{
        const table = document.getElementById('{table_id}');
        const tbody = table.tBodies[0];
        const rows = Array.from(tbody.rows);
        const asc = !sortState_{table_id}[colIndex];
        sortState_{table_id}[colIndex] = asc;
        rows.sort(function(a, b) {{
          let av = cleanValue_{table_id}(a.cells[colIndex].getAttribute('data-sort') || a.cells[colIndex].innerText);
          let bv = cleanValue_{table_id}(b.cells[colIndex].getAttribute('data-sort') || b.cells[colIndex].innerText);
          let an = parseFloat(av);
          let bn = parseFloat(bv);
          let bothNumeric = !isNaN(an) && !isNaN(bn) && av !== '' && bv !== '';
          if (bothNumeric) return asc ? an - bn : bn - an;
          return asc ? av.localeCompare(bv) : bv.localeCompare(av);
        }});
        rows.forEach(r => tbody.appendChild(r));
      }}
    </script>
    """
    components.html(html_code, height=min(height + 40, 800), scrolling=True)


def sortable_table(
    df: pd.DataFrame,
    title: str,
    key: str,
    default_sort: str | None = None,
    default_ascending: bool = False,
    help_text: str | None = None,
) -> pd.DataFrame:
    st.markdown(f"### {title}")
    if help_text:
        st.markdown(f"<div class='small-note'>{help_text}</div>", unsafe_allow_html=True)

    if df.empty:
        st.info("No data available for this table.")
        return df

    display_df = df.copy()
    columns = list(display_df.columns)
    default_sort = default_sort if default_sort in columns else columns[0]

    try:
        sorted_df = display_df.sort_values(by=default_sort, ascending=default_ascending, kind="mergesort")
    except Exception:
        sorted_df = display_df

    st.caption("Click any column header to sort ascending/descending. This sorts inside the table and will not reset the page.")
    sortable_html_table(sorted_df, key=key)
    st.download_button(
        f"Download {title} CSV",
        data=sorted_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{key}.csv",
        mime="text/csv",
        key=f"{key}_download",
    )
    return sorted_df

def bar_chart(df, x, y, title, color=None, key=None):
    if df.empty or x not in df.columns or y not in df.columns:
        return
    fig = px.bar(df, x=x, y=y, color=color, title=title, text_auto=True)
    fig.update_layout(
        title_font_size=20,
        title_font_color="#0D2B45",
        xaxis_title=None,
        yaxis_title=None,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=60, b=120),
        xaxis_tickangle=-35,
        showlegend=True if color else False,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig, use_container_width=True, key=key)


def make_json_safe(obj):
    if isinstance(obj, pd.DataFrame):
        return obj.replace({np.nan: None}).to_dict(orient="records")
    if isinstance(obj, pd.Series):
        return obj.replace({np.nan: None}).to_dict()
    if isinstance(obj, (pd.Timestamp,)):
        return None if pd.isna(obj) else obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if pd.isna(obj) else float(obj)
    if isinstance(obj, dict):
        return {str(k): make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_json_safe(v) for v in obj]
    return obj


def save_anonymized_snapshot(kpis, type_stats, gender_unique, activity_stats, rec_df):
    """Persist only aggregate dashboard values. Names/phone numbers are never written."""
    safe_activity_cols = [
        "activity", "programme_type", "total_attendances", "unique_seniors",
        "number_of_sessions", "avg_attendance_per_session", "returning_members",
        "retention_score", "male_attendances", "unique_male_attendances",
        "male_pct", "unique_male_pct", "ib_participants", "ob_participants",
        "sample_note",
    ]
    safe_activity_cols = [c for c in safe_activity_cols if c in activity_stats.columns]
    snapshot = {
        "saved_at": pd.Timestamp.now().isoformat(),
        "kpis": kpis,
        "programme_type_summary": make_json_safe(type_stats),
        "gender_summary": make_json_safe(gender_unique),
        "activity_summary": make_json_safe(activity_stats[safe_activity_cols]),
        "recommendations": make_json_safe(rec_df),
        "privacy_note": "Only aggregated KPI/chart values are stored. Names and phone numbers are not stored.",
    }
    ANON_STORE_PATH.write_text(json.dumps(make_json_safe(snapshot), ensure_ascii=False, indent=2), encoding="utf-8")


def load_anonymized_snapshot():
    if not ANON_STORE_PATH.exists():
        return None
    try:
        return json.loads(ANON_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def show_stored_snapshot(snapshot):
    st.markdown("## Stored KPI Overview")
    st.caption("Stored values are aggregate-only. No names or phone numbers are saved.")
    k = snapshot.get("kpis", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Attendances", f"{int(k.get('total_attendances', 0)):,}")
    c2.metric("Unique Seniors", f"{int(k.get('total_unique_seniors', 0)):,}")
    c3.metric("Activities", f"{int(k.get('total_activities', 0)):,}")
    c4.metric("Avg Attendance / Activity", f"{float(k.get('avg_attendance_per_activity', 0)):.1f}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Male Attendances", f"{int(k.get('male_attendances', 0)):,}")
    m2.metric("Unique Male Seniors", f"{int(k.get('male_unique_members', 0)):,}")
    m3.metric("Male Attendance %", f"{float(k.get('male_attendance_pct', 0)):.1%}")
    m4.metric("Male Unique %", f"{float(k.get('male_unique_pct', 0)):.1%}")
    activity_saved = pd.DataFrame(snapshot.get("activity_summary", []))
    if not activity_saved.empty:
        sortable_table(nice_columns(activity_saved), "Stored Activity Summary", "stored_activity", default_sort="Total Attendances", default_ascending=False)


with st.sidebar:
    st.markdown("## Dashboard Controls")
    st.markdown("Upload your attendance file, choose programme type, then generate the dashboard.")
    activity_type_filter = st.selectbox("Programme Type", ["All", "One-Time", "Recurring"])
    st.divider()
    st.caption(f"Loaded utils from: {utils_module.__file__}")

uploaded = st.file_uploader("Upload Excel or CSV file", type=["xlsx", "xls", "csv"], accept_multiple_files=False)

if not uploaded:
    stored_snapshot = load_anonymized_snapshot()
    if stored_snapshot:
        show_stored_snapshot(stored_snapshot)
        st.stop()

    st.markdown(
        """
        <div class="section-card">
        <h3>How to use</h3>
        <span class="success-pill">1. Upload Excel/CSV</span>
        <span class="success-pill">2. Confirm column mapping</span>
        <span class="success-pill">3. Generate dashboard</span>
        <span class="success-pill">4. Sort tables and download CSV</span>
        <p class="small-note">The dashboard reads every real attendance sheet and removes duplicate rows. After generation, only aggregated KPI/chart values are stored in the app; names and phone numbers are not stored.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

with st.spinner("Reading uploaded file..."):
    df_all, sheet_names = read_uploaded_file(uploaded)

if df_all.empty:
    st.error("The uploaded file appears to be empty.")
    st.stop()

st.success(f"Read {len(sheet_names)} sheet(s): {', '.join(sheet_names[:6])}")
df_preview = normalize_columns(df_all)
detected = detect_columns(df_preview)
cols = df_preview.columns.tolist()

with st.expander("Column Mapping", expanded=True):
    st.markdown("Confirm these mappings before generating the dashboard.")
    left, right = st.columns(2)
    with left:
        col_activity = st.selectbox("Activity name column", [None] + cols, index=cols.index(detected["activity"]) + 1 if detected["activity"] in cols else 0)
        col_member = st.selectbox("Member name column", [None] + cols, index=cols.index(detected["member"]) + 1 if detected["member"] in cols else 0)
        col_gender = st.selectbox("Gender column", [None] + cols, index=cols.index(detected["gender"]) + 1 if detected["gender"] in cols else 0)
        col_date = st.selectbox("Date column", [None] + cols, index=cols.index(detected["date"]) + 1 if detected["date"] in cols else 0)
    with right:
        col_status = st.selectbox("Attendance status column", [None] + cols, index=cols.index(detected["attendance"]) + 1 if detected["attendance"] in cols else 0)
        col_age = st.selectbox("Age column", [None] + cols, index=cols.index(detected["age"]) + 1 if detected["age"] in cols else 0)
        col_ib_ob = st.selectbox("IB/OB or client type column", [None] + cols, index=cols.index(detected["ib_ob"]) + 1 if detected["ib_ob"] in cols else 0)
        col_capacity = st.selectbox("Capacity column", [None] + cols, index=cols.index(detected["capacity"]) + 1 if detected["capacity"] in cols else 0)

    with st.expander("Detected raw columns"):
        st.write(cols)

manual_recurring = []
activity_source_col = col_activity or detected.get("activity")
if activity_source_col and activity_source_col in df_preview.columns:
    unique_activities = sorted(df_preview[activity_source_col].dropna().astype(str).unique())
    auto_recurring = infer_recurring_activities(df_preview, activity_col=activity_source_col, date_col=col_date or detected.get("date"))
    manual_recurring = st.multiselect(
        "Optional: manually mark recurring activities",
        options=unique_activities,
        default=[a for a in auto_recurring if a in unique_activities],
    )

current_file_id = f"{uploaded.name}-{getattr(uploaded, 'size', 0)}"
if st.session_state.get("dashboard_file_id") != current_file_id:
    st.session_state["dashboard_ready"] = False
    st.session_state["dashboard_file_id"] = current_file_id

if st.button("Clean Data & Generate Dashboard", type="primary", use_container_width=True):
    st.session_state["dashboard_ready"] = True

if not st.session_state.get("dashboard_ready", False):
    st.stop()

# Clean and map data
original = normalize_columns(df_all)
final_map = {
    "activity": col_activity or detected.get("activity"),
    "member": col_member or detected.get("member"),
    "gender": col_gender or detected.get("gender"),
    "age": col_age or detected.get("age"),
    "attendance": col_status or detected.get("attendance"),
    "date": col_date or detected.get("date"),
    "ib_ob": col_ib_ob or detected.get("ib_ob"),
    "capacity": col_capacity or detected.get("capacity"),
}

missing = [name for name in ["activity", "member"] if not final_map.get(name)]
if missing:
    st.error(f"Missing required columns: {', '.join(missing)}. Please map them before continuing.")
    st.stop()

rename_map = {source: target for target, source in final_map.items() if source}
df = original.rename(columns=rename_map)
df = df.dropna(subset=["activity", "member"])
df["activity"] = df["activity"].astype(str).str.strip()
df["member"] = df["member"].astype(str).str.strip()

if "date" in df.columns:
    df["date"] = df["date"].apply(standardize_date)

if "attendance" in df.columns:
    df["attended"] = df["attendance"].apply(guess_attended)
else:
    df["attended"] = True

programme_series = classify_programme_type(df, activity_col="activity", date_col="date" if "date" in df.columns else None)
df["programme_type"] = programme_series
if manual_recurring:
    df["programme_type"] = df["activity"].apply(lambda x: "Recurring" if x in manual_recurring else df.loc[df["activity"] == x, "programme_type"].iloc[0])

df_att = df[df["attended"] == True].copy()
if "gender" in df_att.columns:
    df_att["gender_clean"] = df_att["gender"].apply(clean_gender)
else:
    df_att["gender_clean"] = "Unknown"

if "ib_ob" in df_att.columns:
    df_att["ib_ob_clean"] = df_att["ib_ob"].apply(clean_ib_ob)
else:
    df_att["ib_ob_clean"] = "Unknown"

if "capacity" in df_att.columns:
    df_att["capacity"] = pd.to_numeric(df_att["capacity"], errors="coerce")

if activity_type_filter != "All":
    df_att = df_att[df_att["programme_type"] == activity_type_filter].copy()

if df_att.empty:
    st.warning("No attended records found for the selected filters.")
    st.stop()

# KPI Overview
total_attendances = len(df_att)
total_unique_seniors = df_att["member"].nunique()
total_activities = df_att["activity"].nunique()
avg_attendance_per_activity = total_attendances / total_activities if total_activities else 0
male_attendances = int((df_att["gender_clean"] == "Male").sum())
male_unique_members = int(df_att[df_att["gender_clean"] == "Male"]["member"].nunique())
male_attendance_pct = male_attendances / total_attendances if total_attendances else 0
male_unique_pct = male_unique_members / total_unique_seniors if total_unique_seniors else 0
kpis = {
    "total_attendances": total_attendances,
    "total_unique_seniors": total_unique_seniors,
    "total_activities": total_activities,
    "avg_attendance_per_activity": avg_attendance_per_activity,
    "male_attendances": male_attendances,
    "male_unique_members": male_unique_members,
    "male_attendance_pct": male_attendance_pct,
    "male_unique_pct": male_unique_pct,
}

st.markdown("## KPI Overview")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Attendances", f"{total_attendances:,}")
k2.metric("Unique Seniors", f"{total_unique_seniors:,}")
k3.metric("Activities", f"{total_activities:,}")
k4.metric("Avg Attendance / Activity", f"{avg_attendance_per_activity:.1f}")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Male Attendances", f"{male_attendances:,}")
m2.metric("Unique Male Seniors", f"{male_unique_members:,}")
m3.metric("Male Attendance %", f"{male_attendance_pct:.1%}")
m4.metric("Male Unique %", f"{male_unique_pct:.1%}")

st.markdown("## Quick Visual Summary")
vc1, vc2 = st.columns(2)
with vc1:
    type_stats = df_att.groupby("programme_type").agg(total_attendances=("member", "count"), unique_programmes=("activity", pd.Series.nunique)).reset_index()
    fig_type = px.bar(type_stats, x="programme_type", y="total_attendances", color="programme_type", title="Attendances by Programme Type", text_auto=True)
    fig_type.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_type, use_container_width=True)
with vc2:
    gender_unique = df_att.groupby("gender_clean")["member"].nunique().reset_index(name="unique_seniors")
    fig_gender = px.pie(gender_unique, names="gender_clean", values="unique_seniors", title="Unique Seniors by Gender", hole=0.45)
    fig_gender.update_layout(paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_gender, use_container_width=True)

# Activity stats
activity_stats = (
    df_att.groupby(["activity", "programme_type"])
    .agg(total_attendances=("member", "count"), unique_seniors=("member", pd.Series.nunique))
    .reset_index()
)
activity_stats["retention_score"] = activity_stats["total_attendances"] / activity_stats["unique_seniors"].replace(0, np.nan)

repeat_counts = df_att.groupby(["activity", "member"]).size().reset_index(name="cnt")
returning = repeat_counts[repeat_counts["cnt"] > 1].groupby("activity")["member"].nunique().reset_index(name="returning_members")
activity_stats = activity_stats.merge(returning, on="activity", how="left").fillna({"returning_members": 0})

male_activity = (
    df_att[df_att["gender_clean"] == "Male"]
    .groupby("activity")
    .agg(male_attendances=("member", "count"), unique_male_attendances=("member", pd.Series.nunique))
    .reset_index()
)
activity_stats = activity_stats.merge(male_activity, on="activity", how="left")
activity_stats[["male_attendances", "unique_male_attendances"]] = activity_stats[["male_attendances", "unique_male_attendances"]].fillna(0).astype(int)
activity_stats["male_pct"] = activity_stats["male_attendances"] / activity_stats["total_attendances"].replace(0, np.nan)
activity_stats["unique_male_pct"] = activity_stats["unique_male_attendances"] / activity_stats["unique_seniors"].replace(0, np.nan)
activity_stats["sample_note"] = np.where(activity_stats["unique_seniors"] < 10, "Small sample", "")

if "date" in df_att.columns:
    session_counts = df_att.groupby("activity")["date"].nunique().reset_index(name="number_of_sessions")
    activity_stats = activity_stats.merge(session_counts, on="activity", how="left")
else:
    activity_stats["number_of_sessions"] = 1
activity_stats["number_of_sessions"] = activity_stats["number_of_sessions"].replace(0, 1).fillna(1)
activity_stats["avg_attendance_per_session"] = activity_stats["total_attendances"] / activity_stats["number_of_sessions"]

ib_activity = df_att[df_att["ib_ob_clean"] == "IB"].groupby("activity").agg(ib_participants=("member", "count")).reset_index()
ob_activity = df_att[df_att["ib_ob_clean"] == "OB"].groupby("activity").agg(ob_participants=("member", "count")).reset_index()
activity_stats = activity_stats.merge(ib_activity, on="activity", how="left").merge(ob_activity, on="activity", how="left")
activity_stats[["ib_participants", "ob_participants"]] = activity_stats[["ib_participants", "ob_participants"]].fillna(0).astype(int)

if "capacity" in df_att.columns:
    capacity_summary = df_att.groupby("activity")["capacity"].first().reset_index(name="capacity")
    activity_stats = activity_stats.merge(capacity_summary, on="activity", how="left")
    activity_stats["attendance_rate"] = activity_stats["total_attendances"] / activity_stats["capacity"].replace(0, np.nan)
else:
    activity_stats["capacity"] = np.nan
    activity_stats["attendance_rate"] = np.nan

st.markdown("## Activity Insights")
summary_cols = [
    "activity", "programme_type", "total_attendances", "unique_seniors", "number_of_sessions",
    "avg_attendance_per_session", "returning_members", "retention_score", "male_attendances",
    "unique_male_attendances", "male_pct", "unique_male_pct", "sample_note"
]
activity_summary_sorted = sortable_table(
    nice_columns(activity_stats[summary_cols]),
    "Activity Summary",
    "activity_summary",
    default_sort="Total Attendances",
    default_ascending=False,
    help_text="Use the controls to sort alphabetically, ascending, or descending by any column.",
)
bar_chart(activity_summary_sorted.head(20), "Activity", "Total Attendances", "Top Activities by Total Attendance", color="Programme Type", key="activity_summary_chart")

one_time = activity_stats[activity_stats["programme_type"] == "One-Time"].copy()
if not one_time.empty:
    one_time_display = nice_columns(one_time[["activity", "total_attendances", "unique_seniors", "male_attendances", "unique_male_attendances", "male_pct", "ib_participants", "ob_participants", "attendance_rate"]])
    one_time_sorted = sortable_table(one_time_display, "One-Time Programmes", "one_time", default_sort="Total Attendances", default_ascending=False)
    bar_chart(one_time_sorted.head(20), "Activity", "Total Attendances", "One-Time Programmes by Attendance", key="one_time_chart")
else:
    st.info("No one-time programmes found for this filter.")

recurring = activity_stats[activity_stats["programme_type"] == "Recurring"].copy()
if not recurring.empty:
    recurring_display = nice_columns(recurring[["activity", "total_attendances", "number_of_sessions", "avg_attendance_per_session", "returning_members", "retention_score", "unique_seniors"]])
    recurring_sorted = sortable_table(recurring_display, "Recurring Programmes", "recurring", default_sort="Avg Attendance Per Session", default_ascending=False)
    bar_chart(recurring_sorted.head(20), "Activity", "Avg Attendance Per Session", "Recurring Programmes by Average Attendance per Session", key="recurring_chart")
else:
    st.info("No recurring programmes found for this filter.")

st.markdown("## Male Participation Analysis")
male_display = activity_stats[["activity", "programme_type", "male_attendances", "unique_male_attendances", "male_pct", "unique_male_pct", "total_attendances", "unique_seniors", "sample_note"]].copy()
male_sorted = sortable_table(
    nice_columns(male_display),
    "Male Attendances and Unique Male Attendances by Activity",
    "male_activity",
    default_sort="Male Attendances",
    default_ascending=False,
    help_text="Male Attendances counts all male attendance rows. Unique Male Attendances counts distinct male seniors per activity.",
)
chart_left, chart_right = st.columns(2)
with chart_left:
    bar_chart(male_sorted.head(20), "Activity", "Male Attendances", "Male Attendances by Activity", color="Programme Type", key="male_att_chart")
with chart_right:
    male_unique_sorted = male_sorted.sort_values("Unique Male Attendances", ascending=False)
    bar_chart(male_unique_sorted.head(20), "Activity", "Unique Male Attendances", "Unique Male Attendances by Activity", color="Programme Type", key="male_unique_chart")

st.markdown("## Programme Recommendations")
rec_df = build_recommendations(activity_stats)
rec_sorted = sortable_table(
    nice_columns(rec_df),
    "Recommendations",
    "recommendations",
    default_sort="Activity",
    default_ascending=True,
    help_text="Recommendations are based on attendance, reach, retention, and male participation patterns.",
)
save_anonymized_snapshot(kpis, type_stats, gender_unique, activity_stats, rec_df)
st.caption("Saved aggregate KPI/chart values in the app. Names and phone numbers were not saved.")

if "date" in df_att.columns and not df_att.empty and pd.notna(df_att["date"].max()):
    last_date = df_att["date"].max()
    cutoff = last_date - timedelta(days=180)
    recent = df_att[df_att["date"] >= cutoff]
    inactive = sorted(set(df_att["member"].unique()) - set(recent["member"].unique()))
    inactive_df = pd.DataFrame({"member": inactive})
    st.markdown("## Inactive Seniors")
    st.write(f"Based on the latest attendance date in the file, {last_date.date()}, there are {len(inactive)} seniors with no attendance in the last 180 days.")
    sortable_table(nice_columns(inactive_df), "Inactive Seniors List", "inactive", default_sort="Member", default_ascending=True)

st.markdown("## Export Full Activity Summary")
st.download_button(
    "Download full activity summary CSV",
    data=activity_stats.to_csv(index=False).encode("utf-8-sig"),
    file_name="full_activity_summary.csv",
    mime="text/csv",
    use_container_width=True,
)
