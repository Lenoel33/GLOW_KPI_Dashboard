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
SNAPSHOT_SCHEMA_VERSION = 3
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
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 24px;
        margin: 14px 0 24px 0;
    }
    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E9D6B3;
        border-radius: 18px;
        padding: 24px 28px;
        min-height: 140px;
        box-shadow: 0 6px 18px rgba(13, 43, 69, 0.08);
        display: flex;
        flex-direction: column;
        justify-content: center;
        overflow: visible;
    }
    .kpi-label {
        color: #55623B;
        font-weight: 700;
        font-size: 1.02rem;
        line-height: 1.2;
        margin-bottom: 14px;
        white-space: normal;
    }
    .kpi-value {
        color: #0D2B45;
        font-weight: 800;
        font-size: clamp(2rem, 2.7vw, 3rem);
        line-height: 1.08;
        white-space: normal;
        overflow-wrap: normal;
        word-break: keep-all;
    }
    .kpi-value.long {
        font-size: clamp(1.65rem, 2.2vw, 2.55rem);
    }
    @media (max-width: 1100px) {
        .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 640px) {
        .kpi-grid { grid-template-columns: 1fr; gap: 14px; }
        .kpi-card { min-height: 120px; padding: 20px 22px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

def render_kpi_cards(cards):
    """Render KPI cards without Streamlit metric truncation/cut-off."""
    html_cards = []
    for label, value in cards:
        safe_label = html_lib.escape(str(label))
        safe_value = html_lib.escape(str(value))
        long_class = " long" if len(str(value)) >= 10 else ""
        html_cards.append(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{safe_label}</div>'
            f'<div class="kpi-value{long_class}">{safe_value}</div>'
            f'</div>'
        )
    st.markdown('<div class="kpi-grid">' + ''.join(html_cards) + '</div>', unsafe_allow_html=True)

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
        "aap": find_one([
            "aap participated count this year",
            "aap participated this year",
            "aap participated",
            "aap count",
            "aap",
            "activities participated this year",
            "programmes participated this year",
        ]),
    }


def read_general_uploaded_file(uploaded_file):
    """Read a normal CSV/Excel file where headers are already in the first row.

    This is used for programme-level files from other centres, such as exports with
    Centre, End Date, Event Domain, Is AAP?, Name of Event, Programmes, Start Date,
    Status, Target Attendees, and Total Sessions.
    """
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        df["__source_sheet__"] = uploaded_file.name
        return df
    sheets = pd.read_excel(uploaded_file, sheet_name=None, engine="openpyxl")
    frames = []
    for sheet_name, df in sheets.items():
        if df is None or df.empty:
            continue
        temp = df.copy().dropna(how="all")
        if temp.empty:
            continue
        temp["__source_sheet__"] = sheet_name
        frames.append(temp)
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def detect_programme_columns(df: pd.DataFrame) -> dict:
    """Detect programme-level columns used by other centre exports."""
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
        "centre": find_one(["centre", "center"]),
        "event_name": find_one(["name of event", "event name", "programme name", "program name", "activity name", "event"]),
        "programmes": find_one(["programmes", "programs", "programme", "program"]),
        "start_date": find_one(["start date", "programme start date", "event start date"]),
        "end_date": find_one(["end date", "programme end date", "event end date"]),
        "event_domain": find_one(["event domain", "domain", "programme domain", "program domain"]),
        "is_aap": find_one(["is aap?", "is aap", "aap?", "aap"]),
        "status": find_one(["status", "event status", "programme status"]),
        "target_attendees": find_one(["target attendees", "target attendee", "target", "capacity", "expected attendees"]),
        "total_sessions": find_one(["total sessions", "sessions", "no. of sessions", "number of sessions"]),
    }


def clean_programme_data(df_raw: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """Convert programme-level files into one standard structure."""
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()
    raw = normalize_columns(df_raw)
    rename = {source: target for target, source in mapping.items() if source and source in raw.columns}
    out = raw.rename(columns=rename).copy()

    # If no event name is mapped, fall back to Programmes where available.
    if "event_name" not in out.columns and "programmes" in out.columns:
        out["event_name"] = out["programmes"]
    if "event_name" not in out.columns:
        return pd.DataFrame()

    out["event_name"] = out["event_name"].astype(str).str.strip()
    out = out[out["event_name"].notna() & (out["event_name"].astype(str).str.strip() != "")].copy()

    if "centre" not in out.columns:
        out["centre"] = "Unknown Centre"
    if "total_sessions" in out.columns:
        out["total_sessions"] = pd.to_numeric(out["total_sessions"], errors="coerce").fillna(1)
    else:
        out["total_sessions"] = 1
    if "target_attendees" in out.columns:
        out["target_attendees"] = pd.to_numeric(out["target_attendees"], errors="coerce")
    else:
        out["target_attendees"] = np.nan
    for date_col in ["start_date", "end_date"]:
        if date_col in out.columns:
            out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    if "is_aap" in out.columns:
        out["is_aap_clean"] = out["is_aap"].apply(lambda x: "AAP" if str(x).strip().lower() in {"yes", "y", "true", "1", "aap"} else "Non-AAP")
    else:
        out["is_aap_clean"] = "Unknown"
    if "status" in out.columns:
        out["status_clean"] = out["status"].astype(str).str.strip()
    else:
        out["status_clean"] = "Unknown"
    return out


def make_programme_kpis(prog_df: pd.DataFrame) -> dict:
    if prog_df is None or prog_df.empty:
        return {}
    total_programmes = int(prog_df["event_name"].nunique())
    total_sessions = int(pd.to_numeric(prog_df.get("total_sessions", 1), errors="coerce").fillna(0).sum())
    target_attendees = pd.to_numeric(prog_df.get("target_attendees", pd.Series(dtype=float)), errors="coerce").sum()
    aap_programmes = int(prog_df.loc[prog_df.get("is_aap_clean", "") == "AAP", "event_name"].nunique()) if "is_aap_clean" in prog_df.columns else 0
    non_aap_programmes = int(prog_df.loc[prog_df.get("is_aap_clean", "") == "Non-AAP", "event_name"].nunique()) if "is_aap_clean" in prog_df.columns else 0
    domains = int(prog_df["event_domain"].nunique()) if "event_domain" in prog_df.columns else 0
    return {
        "total_programmes": total_programmes,
        "total_sessions": total_sessions,
        "target_attendees": int(target_attendees) if pd.notna(target_attendees) else 0,
        "avg_sessions_per_programme": total_sessions / total_programmes if total_programmes else 0,
        "aap_programmes": aap_programmes,
        "non_aap_programmes": non_aap_programmes,
        "event_domains": domains,
    }


def render_programme_dashboard(prog_df: pd.DataFrame, title_prefix="Programme-Level KPIs"):
    """Show KPIs that can be calculated without member-level attendance data."""
    if prog_df is None or prog_df.empty:
        return
    k = make_programme_kpis(prog_df)
    st.markdown(f"## {title_prefix}")
    st.caption("These KPIs come from programme-level files. Member KPIs such as Attendances, Unique Members, IB/OB, Male, New IB/OB, and Inactive ≤2 AAP require an attendance/member-level file or a Summary sheet.")
    render_kpi_cards([
        ("Programmes", f"{k.get('total_programmes', 0):,}"),
        ("Total Sessions", f"{k.get('total_sessions', 0):,}"),
        ("Target Attendees", f"{k.get('target_attendees', 0):,}"),
        ("Avg Sessions / Programme", f"{k.get('avg_sessions_per_programme', 0):.1f}"),
        ("AAP Programmes", f"{k.get('aap_programmes', 0):,}"),
        ("Non-AAP Programmes", f"{k.get('non_aap_programmes', 0):,}"),
        ("Event Domains", f"{k.get('event_domains', 0):,}"),
    ])
    summary_cols = [c for c in ["centre", "event_name", "event_domain", "is_aap_clean", "status_clean", "start_date", "end_date", "target_attendees", "total_sessions"] if c in prog_df.columns]
    if summary_cols:
        display = prog_df[summary_cols].copy()
        display = display.drop_duplicates()
        sortable_table(nice_columns(display), "Programme File Summary", "programme_file_summary", default_sort="Event Name", default_ascending=True)
    if "event_domain" in prog_df.columns:
        domain_stats = prog_df.groupby("event_domain", dropna=False).agg(programmes=("event_name", pd.Series.nunique), total_sessions=("total_sessions", "sum")).reset_index()
        bar_chart(nice_columns(domain_stats), "Event Domain", "Programmes", "Programmes by Event Domain", key="programme_domain_chart")


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
      #{table_id} {{ width: max-content; min-width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 14px; }}
      #{table_id} th {{
        position: sticky; top: 0; z-index: 2;
        background: #0D2B45; color: white;
        padding: 10px 12px; text-align: left; cursor: pointer; user-select: none;
        white-space: nowrap;
      }}
      #{table_id} th:hover {{ background: #164766; }}
      #{table_id} td {{ padding: 9px 12px; border-bottom: 1px solid #F0E4D2; color: #1f2937; white-space: nowrap; vertical-align: middle; }}
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
    height: int = 520,
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




def infer_centre_name(file_name: str) -> str:
    """Guess the centre name from the uploaded workbook name."""
    name = str(file_name).lower()
    if "bukit" in name or "(bb" in name or " bb" in name or "glow (bb" in name:
        if "seen" in name:
            return "SEEN Bukit Batok"
        return "GLOW Bukit Batok"
    if "seen" in name and "nanyang" in name:
        return "SEEN Nanyang"
    if "glow" in name and "nanyang" in name:
        return "GLOW Nanyang"
    stem = Path(str(file_name)).stem.replace("_", " ").replace("-", " ").strip()
    return stem or "Centre"


def combine_summary_kpis(summary_items: dict) -> dict:
    """Combine centre-level Summary KPIs for the All Centres view."""
    valid_items = {centre: item for centre, item in summary_items.items() if item}
    if not valid_items:
        return {}
    numeric_keys = [
        "programmes", "attendances", "unique_members", "ib_count", "ob_count",
        "male_count", "inactive_count", "new_ib", "new_ob",
    ]
    combined = {k: 0 for k in numeric_keys}
    for item in valid_items.values():
        for k in numeric_keys:
            combined[k] += int(item.get(k, 0) or 0)
    unique_members = combined.get("unique_members", 0)
    programmes = combined.get("programmes", 0)
    attendances = combined.get("attendances", 0)
    combined.update({
        "source": "Summary",
        "source_detail": "Combined Summary OVERALL TOTAL rows from selected centre files",
        "ib_pct": combined["ib_count"] / unique_members if unique_members else 0,
        "ob_pct": combined["ob_count"] / unique_members if unique_members else 0,
        "male_pct": combined["male_count"] / unique_members if unique_members else 0,
        "inactive_pct": combined["inactive_count"] / unique_members if unique_members else 0,
        "avg_attendance_per_programme": attendances / programmes if programmes else 0,
    })
    return combined


def make_centre_kpi_table(summary_items: dict) -> pd.DataFrame:
    rows = []
    for centre, k in summary_items.items():
        if not k:
            continue
        rows.append({
            "Centre": centre,
            "Programmes": int(k.get("programmes", 0) or 0),
            "Attendances": int(k.get("attendances", 0) or 0),
            "Unique Members": int(k.get("unique_members", 0) or 0),
            "IB (%)": f"{int(k.get('ib_count', 0) or 0):,} ({float(k.get('ib_pct', 0) or 0):.1%})",
            "OB (%)": f"{int(k.get('ob_count', 0) or 0):,} ({float(k.get('ob_pct', 0) or 0):.1%})",
            "Male (%)": f"{int(k.get('male_count', 0) or 0):,} ({float(k.get('male_pct', 0) or 0):.1%})",
            "Inactive (<=2AAP) (%)": f"{int(k.get('inactive_count', 0) or 0):,} ({float(k.get('inactive_pct', 0) or 0):.1%})",
            "New IB": int(k.get("new_ib", 0) or 0),
            "New OB": int(k.get("new_ob", 0) or 0),
        })
    return pd.DataFrame(rows)

def load_anonymized_snapshot():
    if not ANON_STORE_PATH.exists():
        return None
    try:
        snapshot = json.loads(ANON_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Ignore older stored values from previous app versions. Those values may
    # have been calculated from raw attendance/programme rows instead of the
    # approved Summary sheet, which caused wrong KPI cards such as 95 programmes
    # and 1 attendance. New snapshots are saved only after this version runs.
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        return None
    return snapshot


def show_stored_snapshot(snapshot):
    st.markdown("## Stored KPI Overview")
    st.caption("Stored values are aggregate-only. No names or phone numbers are saved.")
    k = snapshot.get("kpis", {})
    render_kpi_cards([
        ("Programmes", f"{int(k.get('total_activities', 0)):,}"),
        ("Attendances", f"{int(k.get('total_attendances', 0)):,}"),
        ("Unique Members", f"{int(k.get('total_unique_seniors', 0)):,}"),
        ("Avg Attendance / Programme", f"{float(k.get('avg_attendance_per_activity', 0)):.1f}"),
        ("IB", f"{int(k.get('ib_count', 0)):,} ({float(k.get('ib_pct', 0)):.1%})"),
        ("OB", f"{int(k.get('ob_count', 0)):,} ({float(k.get('ob_pct', 0)):.1%})"),
        ("Male", f"{int(k.get('male_attendances', 0)):,} ({float(k.get('male_attendance_pct', 0)):.1%})"),
        ("Inactive (<=2AAP)", f"{int(k.get('inactive_count', 0)):,} ({float(k.get('inactive_pct', 0)):.1%})"),
        ("New IB", f"{int(k.get('new_ib', 0)):,}"),
        ("New OB", f"{int(k.get('new_ob', 0)):,}"),
        ("Unique Male Seniors", f"{int(k.get('male_unique_members', 0)):,}"),
        ("Male Unique %", f"{float(k.get('male_unique_pct', 0)):.1%}"),
    ])
    activity_saved = pd.DataFrame(snapshot.get("activity_summary", []))
    if not activity_saved.empty:
        sortable_table(nice_columns(activity_saved), "Stored Activity Summary", "stored_activity", default_sort="Total Attendances", default_ascending=False)


with st.sidebar:
    st.markdown("## Dashboard Controls")
    st.markdown("Upload your attendance file, choose programme type, then generate the dashboard.")

    if "upload_reset_counter" not in st.session_state:
        st.session_state["upload_reset_counter"] = 0

    if st.button("🧹 Clear uploaded data", use_container_width=True, help="Clears the current upload widgets so your next workbook will not mix with the previous one."):
        st.session_state["upload_reset_counter"] += 1
        st.session_state["dashboard_ready"] = False
        st.session_state.pop("dashboard_file_id", None)
        st.rerun()

    activity_type_filter = st.selectbox("Programme Type", ["All", "One-Time", "Recurring"])
    st.divider()
    st.caption(f"Loaded utils from: {utils_module.__file__}")

upload_reset_counter = st.session_state.get("upload_reset_counter", 0)

attendance_uploaded = st.file_uploader(
    "Upload attendance / KPI Summary file(s)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
    key=f"attendance_files_{upload_reset_counter}",
    help="Use this for GLOW Bukit Batok style workbooks with Summary sheet and/or member attendance rows.",
)

programme_uploaded = st.file_uploader(
    "Upload programme-level file(s) for other centres",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
    key=f"programme_files_{upload_reset_counter}",
    help="Use this for files with Centre, Name of Event, Start Date, End Date, Event Domain, Is AAP?, Status, Target Attendees, and Total Sessions.",
)

if not attendance_uploaded and not programme_uploaded:
    stored_snapshot = load_anonymized_snapshot()
    if stored_snapshot:
        show_stored_snapshot(stored_snapshot)
        st.stop()

    st.markdown(
        """
        <div class="section-card">
        <h3>How to use</h3>
        <span class="success-pill">1. Upload attendance/KPI Summary files where available</span>
        <span class="success-pill">2. Upload programme-level files for other centres</span>
        <span class="success-pill">3. Map columns once in the app</span>
        <span class="success-pill">4. Generate dashboard</span>
        <p class="small-note">Attendance files calculate member KPIs. Programme files calculate programme/session/domain KPIs. The app will clearly show when a KPI cannot be calculated because member-level data is missing.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

with st.sidebar:
    st.markdown("## Centre Setup")
    attendance_centre_names = []
    for i, file in enumerate(attendance_uploaded or []):
        default_name = infer_centre_name(file.name)
        attendance_centre_names.append(
            st.text_input(
                f"Attendance/Summary centre for {file.name}",
                value=default_name,
                key=f"attendance_centre_name_{i}_{file.name}",
            ).strip() or default_name
        )

    programme_centre_names = []
    for i, file in enumerate(programme_uploaded or []):
        default_name = infer_centre_name(file.name)
        programme_centre_names.append(
            st.text_input(
                f"Programme file centre for {file.name}",
                value=default_name,
                key=f"programme_centre_name_{i}_{file.name}",
            ).strip() or default_name
        )

centre_frames = {}
centre_summary_kpis = {}
centre_summary_tables = {}
sheet_names_by_centre = {}
programme_frames_raw = {}

with st.spinner("Reading uploaded file(s)..."):
    for file, centre_name in zip(attendance_uploaded or [], attendance_centre_names):
        df_one, sheet_names_one = read_uploaded_file(file)
        if not df_one.empty:
            df_one = df_one.copy()
            # Keep the selected/uploaded centre in a protected helper column.
            # Some workbooks may already contain a blank/duplicate Centre column,
            # so relying only on "centre" can leave the displayed Centre column empty.
            df_one["__uploaded_centre__"] = centre_name
            df_one["centre"] = centre_name
            centre_frames[centre_name] = df_one
        centre_summary_kpis[centre_name] = df_one.attrs.get("summary_kpis", {}) if hasattr(df_one, "attrs") else {}
        summary_one = df_one.attrs.get("summary_table", pd.DataFrame()) if hasattr(df_one, "attrs") else pd.DataFrame()
        if isinstance(summary_one, pd.DataFrame) and not summary_one.empty:
            summary_one = summary_one.copy()
            summary_one.insert(0, "Centre", centre_name)
        centre_summary_tables[centre_name] = summary_one
        sheet_names_by_centre[centre_name] = sheet_names_one

    for file, centre_name in zip(programme_uploaded or [], programme_centre_names):
        prog_raw = read_general_uploaded_file(file)
        if not prog_raw.empty:
            prog_raw = prog_raw.copy()
            # Keep the user-confirmed centre name even if the file has a Centre column.
            prog_raw["__uploaded_centre__"] = centre_name
            programme_frames_raw[centre_name] = prog_raw

all_centres = sorted(set(centre_frames.keys()) | set(programme_frames_raw.keys()))
if not all_centres:
    st.error("The uploaded file(s) appear to be empty or unreadable.")
    st.stop()

centre_options = ["All Centres"] + all_centres
selected_centre = st.sidebar.selectbox("View KPI for centre", centre_options, index=0)

if selected_centre == "All Centres":
    df_all = pd.concat(centre_frames.values(), ignore_index=True, sort=False) if centre_frames else pd.DataFrame()
    programme_raw_all = pd.concat(programme_frames_raw.values(), ignore_index=True, sort=False) if programme_frames_raw else pd.DataFrame()
    summary_kpis = combine_summary_kpis(centre_summary_kpis)
    summary_tables = [t for t in centre_summary_tables.values() if isinstance(t, pd.DataFrame) and not t.empty]
    summary_table = pd.concat(summary_tables, ignore_index=True, sort=False) if summary_tables else pd.DataFrame()
    sheet_names = [s for sheets in sheet_names_by_centre.values() for s in sheets]
else:
    df_all = centre_frames.get(selected_centre, pd.DataFrame()).copy()
    programme_raw_all = programme_frames_raw.get(selected_centre, pd.DataFrame()).copy()
    summary_kpis = centre_summary_kpis.get(selected_centre, {})
    summary_table = centre_summary_tables.get(selected_centre, pd.DataFrame())
    sheet_names = sheet_names_by_centre.get(selected_centre, [])

centre_kpi_table = make_centre_kpi_table(centre_summary_kpis)

st.success(f"Loaded {len(centre_frames)} attendance/Summary file(s) and {len(programme_frames_raw)} programme-level file(s). Viewing: {selected_centre}. Read {len(sheet_names)} attendance sheet(s).")

# Programme-level mapping. This lets other centre files with fields such as Centre,
# End Date, Event Domain, Is AAP?, Name of Event, Target Attendees, and Total Sessions
# contribute useful KPIs even when they do not contain member-level attendance data.
programme_clean = pd.DataFrame()
if not programme_raw_all.empty:
    prog_preview = normalize_columns(programme_raw_all)
    prog_detected = detect_programme_columns(prog_preview)
    prog_cols = prog_preview.columns.tolist()
    with st.expander("Programme File Mapping", expanded=True):
        st.markdown("Map these columns for SEEN Bukit Batok, SEEN Nanyang, GLOW Nanyang, or other programme-level files.")
        p_left, p_right = st.columns(2)
        with p_left:
            p_centre = st.selectbox("Centre column", [None] + prog_cols, index=prog_cols.index(prog_detected["centre"]) + 1 if prog_detected["centre"] in prog_cols else 0)
            p_event = st.selectbox("Name of Event column", [None] + prog_cols, index=prog_cols.index(prog_detected["event_name"]) + 1 if prog_detected["event_name"] in prog_cols else 0)
            p_domain = st.selectbox("Event Domain column", [None] + prog_cols, index=prog_cols.index(prog_detected["event_domain"]) + 1 if prog_detected["event_domain"] in prog_cols else 0)
            p_is_aap = st.selectbox("Is AAP? column", [None] + prog_cols, index=prog_cols.index(prog_detected["is_aap"]) + 1 if prog_detected["is_aap"] in prog_cols else 0)
        with p_right:
            p_start = st.selectbox("Start Date column", [None] + prog_cols, index=prog_cols.index(prog_detected["start_date"]) + 1 if prog_detected["start_date"] in prog_cols else 0)
            p_end = st.selectbox("End Date column", [None] + prog_cols, index=prog_cols.index(prog_detected["end_date"]) + 1 if prog_detected["end_date"] in prog_cols else 0)
            p_status = st.selectbox("Status column", [None] + prog_cols, index=prog_cols.index(prog_detected["status"]) + 1 if prog_detected["status"] in prog_cols else 0)
            p_target = st.selectbox("Target Attendees column", [None] + prog_cols, index=prog_cols.index(prog_detected["target_attendees"]) + 1 if prog_detected["target_attendees"] in prog_cols else 0)
            p_sessions = st.selectbox("Total Sessions column", [None] + prog_cols, index=prog_cols.index(prog_detected["total_sessions"]) + 1 if prog_detected["total_sessions"] in prog_cols else 0)
        programme_mapping = {
            "centre": p_centre or "__uploaded_centre__",
            "event_name": p_event,
            "event_domain": p_domain,
            "is_aap": p_is_aap,
            "start_date": p_start,
            "end_date": p_end,
            "status": p_status,
            "target_attendees": p_target,
            "total_sessions": p_sessions,
        }
        with st.expander("Detected programme raw columns"):
            st.write(prog_cols)
    programme_clean = clean_programme_data(programme_raw_all, programme_mapping)

# If the user only uploaded programme-level files, show what can be calculated and stop
# before the attendance/member-level sections that require names and attendance status.
if df_all.empty:
    render_programme_dashboard(programme_clean, "Programme-Level KPI Overview")
    mandatory = pd.DataFrame([{
        "Programmes": make_programme_kpis(programme_clean).get("total_programmes", 0),
        "Attendances": "Needs attendance/member file or Summary sheet",
        "Unique Members": "Needs attendance/member file or Summary sheet",
        "IB (%)": "Needs attendance/member file or Summary sheet",
        "OB (%)": "Needs attendance/member file or Summary sheet",
        "Male (%)": "Needs attendance/member file or Summary sheet",
        "Inactive (<=2AAP) (%)": "Needs attendance/member file or Summary sheet",
        "New IB": "Needs attendance/member file or Summary sheet",
        "New OB": "Needs attendance/member file or Summary sheet",
    }])
    sortable_table(mandatory, "Mandatory KPI Availability", "mandatory_kpi_availability")
    st.stop()


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
        col_aap = st.selectbox("AAP count column for inactive seniors", [None] + cols, index=cols.index(detected["aap"]) + 1 if detected["aap"] in cols else 0)

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

current_file_id = (
    "|".join(
        [f"attendance:{f.name}-{getattr(f, 'size', 0)}" for f in (attendance_uploaded or [])]
        + [f"programme:{f.name}-{getattr(f, 'size', 0)}" for f in (programme_uploaded or [])]
    )
    + f"|view={selected_centre}"
)
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
    "aap": col_aap or detected.get("aap"),
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

if "aap" in df_att.columns:
    df_att["aap"] = pd.to_numeric(df_att["aap"], errors="coerce")

if activity_type_filter != "All":
    df_att = df_att[df_att["programme_type"] == activity_type_filter].copy()

if df_att.empty:
    st.warning("No attended records found for the selected filters.")
    st.stop()

# KPI Overview
raw_total_attendances = len(df_att)
raw_total_unique_seniors = df_att["member"].nunique()
raw_total_activities = df_att["activity"].nunique()
raw_avg_attendance_per_activity = raw_total_attendances / raw_total_activities if raw_total_activities else 0
raw_male_attendances = int((df_att["gender_clean"] == "Male").sum())
raw_male_unique_members = int(df_att[df_att["gender_clean"] == "Male"]["member"].nunique())
raw_male_attendance_pct = raw_male_attendances / raw_total_attendances if raw_total_attendances else 0
raw_male_unique_pct = raw_male_unique_members / raw_total_unique_seniors if raw_total_unique_seniors else 0

# KPI Overview must always use the workbook Summary sheet when available.
# Programme-type filters only affect charts and drill-down tables below.
use_summary_kpis = bool(summary_kpis)
if use_summary_kpis:
    total_attendances = int(summary_kpis.get("attendances", 0))
    total_unique_seniors = int(summary_kpis.get("unique_members", raw_total_unique_seniors))
    total_activities = int(summary_kpis.get("programmes", raw_total_activities))
    avg_attendance_per_activity = float(summary_kpis.get("avg_attendance_per_programme", 0))
    # Summary columns IB (%), OB (%), Male (%), and Inactive (<=2AAP) (%) store count + percentage.
    # We display the count from Summary and calculate the percentage using Summary Unique Members.
    male_attendances = int(summary_kpis.get("male_count", raw_male_attendances))
    male_unique_members = int(summary_kpis.get("male_count", raw_male_unique_members))
    male_attendance_pct = float(summary_kpis.get("male_pct", 0))
    male_unique_pct = float(summary_kpis.get("male_pct", 0))
    ib_count = int(summary_kpis.get("ib_count", 0))
    ob_count = int(summary_kpis.get("ob_count", 0))
    inactive_count = int(summary_kpis.get("inactive_count", 0))
    new_ib = int(summary_kpis.get("new_ib", 0))
    new_ob = int(summary_kpis.get("new_ob", 0))
    ib_pct = float(summary_kpis.get("ib_pct", 0))
    ob_pct = float(summary_kpis.get("ob_pct", 0))
    inactive_pct = float(summary_kpis.get("inactive_pct", 0))
else:
    total_attendances = raw_total_attendances
    total_unique_seniors = raw_total_unique_seniors
    total_activities = raw_total_activities
    avg_attendance_per_activity = raw_avg_attendance_per_activity
    male_attendances = raw_male_attendances
    male_unique_members = raw_male_unique_members
    male_attendance_pct = raw_male_attendance_pct
    male_unique_pct = raw_male_unique_pct
    ib_count = int((df_att["ib_ob_clean"] == "IB").sum())
    ob_count = int((df_att["ib_ob_clean"] == "OB").sum())
    inactive_count = 0
    new_ib = 0
    new_ob = 0
    denominator = total_unique_seniors if total_unique_seniors else 0
    ib_pct = ib_count / denominator if denominator else 0
    ob_pct = ob_count / denominator if denominator else 0
    inactive_pct = 0

kpis = {
    "total_attendances": total_attendances,
    "total_unique_seniors": total_unique_seniors,
    "total_activities": total_activities,
    "avg_attendance_per_activity": avg_attendance_per_activity,
    "male_attendances": male_attendances,
    "male_unique_members": male_unique_members,
    "male_attendance_pct": male_attendance_pct,
    "male_unique_pct": male_unique_pct,
    "ib_count": ib_count,
    "ib_pct": ib_pct,
    "ob_count": ob_count,
    "ob_pct": ob_pct,
    "inactive_count": inactive_count,
    "inactive_pct": inactive_pct,
    "new_ib": new_ib,
    "new_ob": new_ob,
    "kpi_source": "Summary sheet" if use_summary_kpis else "Cleaned attendance rows",
}

st.markdown("## KPI Overview")
if use_summary_kpis:
    source_detail = summary_kpis.get("source_detail", "Summary sheet") if isinstance(summary_kpis, dict) else "Summary sheet"
    st.caption(f"KPI Overview is locked to the workbook Summary sheet ({source_detail}). It is not recalculated from raw rows.")
else:
    st.warning("No Summary sheet OVERALL TOTAL row was found for the selected centre. KPI cards are calculated from cleaned attendance rows only.")

render_kpi_cards([
    ("Programmes", f"{total_activities:,}"),
    ("Attendances", f"{total_attendances:,}"),
    ("Unique Members", f"{total_unique_seniors:,}"),
    ("Avg Attendance / Programme", f"{avg_attendance_per_activity:.1f}"),
    ("IB", f"{ib_count:,} ({ib_pct:.1%})"),
    ("OB", f"{ob_count:,} ({ob_pct:.1%})"),
    ("Male", f"{male_attendances:,} ({male_attendance_pct:.1%})"),
    ("Inactive (<=2AAP)", f"{inactive_count:,} ({inactive_pct:.1%})"),
    ("New IB", f"{new_ib:,}"),
    ("New OB", f"{new_ob:,}"),
    ("Unique Male Seniors", f"{male_unique_members:,}"),
    ("Male Unique %", f"{male_unique_pct:.1%}"),
])

if len(centre_summary_kpis) > 1 and not centre_kpi_table.empty:
    st.markdown("## Centre KPI Comparison")
    sortable_table(
        centre_kpi_table,
        "Centre KPI Comparison",
        "centre_kpi_comparison",
        default_sort="Attendances",
        default_ascending=False,
        help_text="This comparison is read from each centre workbook's Summary sheet. No names or phone numbers are stored.",
    )

# Senior attendance frequency by IB/OB status
def _collapse_duplicate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Collapse duplicated column labels by taking the first non-blank value row-wise."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    data = {}
    for col in dict.fromkeys(list(frame.columns)):
        subset = frame.loc[:, frame.columns == col]
        if isinstance(subset, pd.Series):
            data[col] = subset
        elif subset.shape[1] == 1:
            data[col] = subset.iloc[:, 0]
        else:
            cleaned_subset = subset.replace(r"^\s*$", pd.NA, regex=True)
            data[col] = cleaned_subset.bfill(axis=1).iloc[:, 0]
    return pd.DataFrame(data)


def make_senior_attendance_frequency(source_df: pd.DataFrame, status_value: str, fallback_centre: str | None = None) -> pd.DataFrame:
    """Count attended rows for each senior by IB/OB status.

    This helper is intentionally defensive because uploaded Excel workbooks can
    produce duplicated column names after cleaning/renaming. Pandas raises
    `ValueError: Grouper for '<name>' not 1-dimensional` when groupby columns
    are duplicated, so we first collapse duplicated columns and then build the
    report from one-dimensional Series only.
    """
    if source_df is None or source_df.empty:
        return pd.DataFrame()

    temp = source_df.copy()

    # Collapse duplicated column labels. This is safer than simply keeping the
    # first duplicate because some workbooks contain a blank Centre column before
    # the dashboard's uploaded-centre value.
    temp = _collapse_duplicate_columns(temp).copy()

    if "__uploaded_centre__" in temp.columns:
        uploaded_centre = temp["__uploaded_centre__"].astype(str).str.strip()
        if "centre" not in temp.columns:
            temp["centre"] = uploaded_centre
        else:
            centre_text = temp["centre"].astype(str).str.strip()
            temp["centre"] = centre_text.mask(centre_text.eq("") | centre_text.str.lower().eq("nan"), uploaded_centre)

    if fallback_centre and fallback_centre != "All Centres":
        if "centre" not in temp.columns:
            temp["centre"] = fallback_centre
        else:
            centre_text = temp["centre"].astype(str).str.strip()
            temp["centre"] = centre_text.mask(centre_text.eq("") | centre_text.str.lower().eq("nan"), fallback_centre)

    required_cols = {"member", "ib_ob_clean"}
    if not required_cols.issubset(set(temp.columns)):
        return pd.DataFrame()

    temp["member"] = temp["member"].astype(str).str.strip()
    temp["ib_ob_clean"] = temp["ib_ob_clean"].astype(str).str.strip().str.upper()
    status_value = str(status_value).strip().upper()

    temp = temp[(temp["ib_ob_clean"] == status_value) & (temp["member"] != "") & (temp["member"].str.lower() != "nan")].copy()
    if temp.empty:
        return pd.DataFrame()

    # Ensure activity exists for counting. If not available, count member rows.
    if "activity" not in temp.columns:
        temp["activity"] = temp["member"]

    group_cols = ["member"]
    if "centre" in temp.columns:
        group_cols = ["centre", "member"]

    agg_fields = {"activity": ["count", pd.Series.nunique]}
    if "date" in temp.columns:
        agg_fields["date"] = "max"
    if "gender_clean" in temp.columns:
        agg_fields["gender_clean"] = "first"
    if "aap" in temp.columns:
        temp["aap"] = pd.to_numeric(temp["aap"], errors="coerce")
        agg_fields["aap"] = "max"

    freq = temp.groupby(group_cols, as_index=False, dropna=False).agg(agg_fields)
    freq.columns = [
        "_".join([str(part) for part in col if str(part)]) if isinstance(col, tuple) else str(col)
        for col in freq.columns
    ]

    rename_cols = {
        "centre": "Centre",
        "member": "Senior Name",
        "activity_count": "Attendances",
        "activity_nunique": "Unique Activities",
        "date_max": "Latest Attendance Date",
        "gender_clean_first": "Gender",
        "aap_max": "AAP Participated This Year",
    }
    freq = freq.rename(columns=rename_cols)

    if "Latest Attendance Date" in freq.columns:
        freq["Latest Attendance Date"] = pd.to_datetime(freq["Latest Attendance Date"], errors="coerce").dt.date
    if "AAP Participated This Year" in freq.columns:
        freq["AAP Participated This Year"] = pd.to_numeric(freq["AAP Participated This Year"], errors="coerce")

    preferred_cols = [
        "Centre",
        "Senior Name",
        "Attendances",
        "Unique Activities",
        "Latest Attendance Date",
        "Gender",
        "AAP Participated This Year",
    ]
    preferred_cols = [c for c in preferred_cols if c in freq.columns]
    if not preferred_cols:
        return pd.DataFrame()
    return freq[preferred_cols].sort_values(["Attendances", "Senior Name"], ascending=[False, True]).reset_index(drop=True)

st.markdown("## Senior Attendance Frequency")
st.caption("These tables count every cleaned `Attended` row across the attendance sheets for the selected centre/view.")

ib_senior_freq = make_senior_attendance_frequency(df_att, "IB", selected_centre)
ob_senior_freq = make_senior_attendance_frequency(df_att, "OB", selected_centre)

ib_tab, ob_tab = st.tabs([f"IB Seniors ({len(ib_senior_freq):,})", f"OB Seniors ({len(ob_senior_freq):,})"])
with ib_tab:
    sortable_table(
        ib_senior_freq,
        "IB Seniors by Attendance Frequency",
        "ib_seniors_attendance_frequency",
        default_sort="Attendances",
        default_ascending=False,
        help_text="IB means `Is Client = Yes`. Attendances are counted from all cleaned attended records, not from the Summary total row.",
    )
with ob_tab:
    sortable_table(
        ob_senior_freq,
        "OB Seniors by Attendance Frequency",
        "ob_seniors_attendance_frequency",
        default_sort="Attendances",
        default_ascending=False,
        help_text="OB means `Is Client = No`. Attendances are counted from all cleaned attended records, not from the Summary total row.",
    )

# Summary Sheet KPI Table removed.
# The Summary sheet is still used as the source of truth for KPI Overview cards,
# but the full Summary table is not displayed to keep the dashboard clean.

if not programme_clean.empty:
    render_programme_dashboard(programme_clean, "Programme-Level KPIs from Other Centre Files")

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

st.markdown("## Inactive Seniors")
# Correct inactive definition:
# A senior is inactive when their AAP Participated count this year is LESS THAN OR EQUAL TO 2.
# This section must NOT use the old 180-day attendance rule and must NOT filter to only attended rows.
# The list is separated into IB and OB using the mapped IB/OB or Is Client column.
if "aap" in df.columns:
    inactive_source = df.dropna(subset=["aap"]).copy()
    inactive_source = _collapse_duplicate_columns(inactive_source).copy()
    inactive_source["aap"] = pd.to_numeric(inactive_source["aap"], errors="coerce")
    inactive_source = inactive_source.dropna(subset=["aap"])

    if "ib_ob" in inactive_source.columns:
        inactive_source["ib_ob_clean"] = inactive_source["ib_ob"].apply(clean_ib_ob)
    elif "ib_ob_clean" not in inactive_source.columns:
        inactive_source["ib_ob_clean"] = "Unknown"

    if "gender" in inactive_source.columns:
        inactive_source["gender_clean"] = inactive_source["gender"].apply(clean_gender)

    if "__uploaded_centre__" in inactive_source.columns:
        uploaded_centre = inactive_source["__uploaded_centre__"].astype(str).str.strip()
        if "centre" not in inactive_source.columns:
            inactive_source["centre"] = uploaded_centre
        else:
            centre_text = inactive_source["centre"].astype(str).str.strip()
            inactive_source["centre"] = centre_text.mask(centre_text.eq("") | centre_text.str.lower().eq("nan"), uploaded_centre)

    # Keep the selected programme-type filter if the user applied one.
    if activity_type_filter != "All" and "programme_type" in inactive_source.columns:
        inactive_source = inactive_source[inactive_source["programme_type"] == activity_type_filter].copy()

    if inactive_source.empty:
        st.info("No AAP count data found for inactive senior listing.")
    else:
        group_cols = ["member", "ib_ob_clean"]
        if "centre" in inactive_source.columns:
            group_cols = ["centre", "member", "ib_ob_clean"]

        # AAP is a yearly count. If the same senior appears in multiple rows/sheets,
        # use their highest recorded AAP count for the year so duplicate/older rows do not understate activity.
        group_fields = {"aap": "max", "activity": "count"}
        if "date" in inactive_source.columns:
            group_fields["date"] = "max"
        if "gender_clean" in inactive_source.columns:
            group_fields["gender_clean"] = "first"

        inactive_df = inactive_source.groupby(group_cols, as_index=False, dropna=False).agg(group_fields)
        inactive_df = inactive_df.rename(columns={
            "centre": "Centre",
            "member": "Member",
            "ib_ob_clean": "Client Type",
            "aap": "AAP Participated This Year",
            "activity": "Total Records",
            "date": "Last Recorded Date",
            "gender_clean": "Gender",
        })

        # This is the key rule: inactive = AAP <= 2.
        inactive_df = inactive_df[inactive_df["AAP Participated This Year"] <= 2].copy()

        if "Last Recorded Date" in inactive_df.columns:
            inactive_df["Last Recorded Date"] = pd.to_datetime(inactive_df["Last Recorded Date"], errors="coerce").dt.date

        ib_inactive_df = inactive_df[inactive_df["Client Type"] == "IB"].copy()
        ob_inactive_df = inactive_df[inactive_df["Client Type"] == "OB"].copy()
        unknown_inactive_df = inactive_df[~inactive_df["Client Type"].isin(["IB", "OB"])].copy()

        st.write(
            f"Inactive seniors are defined as seniors with **AAP Participated This Year ≤ 2**. "
            f"IB: **{len(ib_inactive_df)}**, OB: **{len(ob_inactive_df)}**."
        )

        ib_inactive_tab, ob_inactive_tab, unknown_inactive_tab = st.tabs([
            f"IB Inactive ({len(ib_inactive_df):,})",
            f"OB Inactive ({len(ob_inactive_df):,})",
            f"Unknown ({len(unknown_inactive_df):,})",
        ])

        with ib_inactive_tab:
            sortable_table(ib_inactive_df, "IB Inactive Seniors List", "inactive_ib", default_sort="AAP Participated This Year", default_ascending=True)
        with ob_inactive_tab:
            sortable_table(ob_inactive_df, "OB Inactive Seniors List", "inactive_ob", default_sort="AAP Participated This Year", default_ascending=True)
        with unknown_inactive_tab:
            if unknown_inactive_df.empty:
                st.info("No inactive seniors with unknown IB/OB status.")
            else:
                sortable_table(unknown_inactive_df, "Unknown IB/OB Inactive Seniors List", "inactive_unknown", default_sort="AAP Participated This Year", default_ascending=True)
else:
    st.info("No AAP count column was mapped. Please map the AAP count column to show the inactive seniors list.")

st.markdown("## Export Full Activity Summary")
st.download_button(
    "Download full activity summary CSV",
    data=activity_stats.to_csv(index=False).encode("utf-8-sig"),
    file_name="full_activity_summary.csv",
    mime="text/csv",
    use_container_width=True,
)
