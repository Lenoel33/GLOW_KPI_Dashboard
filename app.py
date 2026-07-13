import sys
import json
import re
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
    .group-section-title {
        margin: 20px 0 10px 0;
        padding: 10px 14px;
        border-left: 6px solid #C45D2D;
        background: rgba(243, 232, 210, 0.65);
        border-radius: 10px;
        color: #0D2B45;
        font-weight: 800;
        font-size: 1.25rem;
    }
    .section-divider {
        height: 1px;
        background: #E9D6B3;
        margin: 18px 0;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 14px; border-bottom: 2px solid #E9D6B3; }
    .stTabs [data-baseweb="tab"] { font-size: 1rem; font-weight: 650; }
    .stTabs [aria-selected="true"] { color: #FF4B4B; }
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

# Streamlit reruns on widget interaction. On newer Streamlit versions,
# @st.fragment keeps interactive profile/filter blocks from forcing the whole
# page to redraw, which reduces the browser jumping back to the top.
streamlit_fragment = getattr(st, "fragment", lambda func=None, **kwargs: (lambda f: f) if func is None else func)


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




def apply_member_status_rules(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply explicit member-status rules before any dashboard calculation.

    Rules:
    - Names containing Passed On or Deceased are excluded from analytics.
    - Names containing Moved Out are retained but forced to OB.
    The raw source workbook is never modified.
    """
    if frame is None or frame.empty or "member" not in frame.columns:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame(), {
            "passed_on_excluded": 0,
            "moved_out_reclassified": 0,
            "passed_on_members": [],
            "moved_out_members": [],
        }

    out = frame.copy()
    names = out["member"].fillna("").astype(str).str.strip()
    passed_mask = names.str.contains(r"\bpassed\s*on\b|\bdeceased\b", case=False, regex=True, na=False)
    moved_mask = names.str.contains(r"\bmoved\s*out\b", case=False, regex=True, na=False)

    passed_members = sorted(names.loc[passed_mask].replace("", pd.NA).dropna().unique().tolist())
    moved_members = sorted(names.loc[moved_mask & ~passed_mask].replace("", pd.NA).dropna().unique().tolist())

    out["member_status"] = "Active"
    out.loc[moved_mask & ~passed_mask, "member_status"] = "Moved Out"

    # A moved-out senior is treated as OB in every downstream table and chart.
    if "ib_ob" not in out.columns:
        out["ib_ob"] = pd.NA
    out.loc[moved_mask & ~passed_mask, "ib_ob"] = "OB"

    # Passed-on seniors are removed before attendance, KPI, preference and inactive calculations.
    out = out.loc[~passed_mask].copy()

    audit = {
        "passed_on_excluded": len(passed_members),
        "moved_out_reclassified": len(moved_members),
        "passed_on_members": passed_members,
        "moved_out_members": moved_members,
    }
    return out, audit

def clean_ib_ob(value):
    """Normalise client type without treating blanks/invalid values as OB.

    Important: OB must mean an explicit `No` / `OB` value.  Do not classify
    every non-IB value as OB, because blank/unknown values would inflate the
    OB count and make the attendance tables disagree with the Summary page.
    """
    if pd.isna(value):
        return "Unknown"
    text = str(value).strip().lower()
    if text in {"ib", "inbound", "i", "incoming", "yes", "y"}:
        return "IB"
    if text in {"ob", "outbound", "o", "outgoing", "no", "n"}:
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


def normalize_group_label(value) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", ""}:
        return "Unknown"
    return text


def render_grouped_tables(
    df: pd.DataFrame,
    group_col: str,
    table_title_prefix: str,
    table_key_prefix: str,
    default_sort: str = "Attendances",
    default_ascending: bool = False,
    help_text: str | None = None,
):
    """Display a dataframe as clearly separated group tabs.

    This is used whenever the dashboard compares fields such as IB/OB or Gender,
    so users can immediately see that the data is separated instead of mixed.
    """
    if df is None or df.empty or group_col not in df.columns:
        st.info("No data available for this section.")
        return

    temp = df.copy()
    temp[group_col] = temp[group_col].apply(normalize_group_label)

    preferred_order = ["IB", "OB", "Male", "Female", "Unknown"]
    groups = [g for g in preferred_order if g in set(temp[group_col])]
    groups += sorted([g for g in temp[group_col].dropna().unique() if g not in groups])

    tabs = st.tabs([f"{g} ({len(temp[temp[group_col] == g]):,})" for g in groups])
    for tab, group in zip(tabs, groups):
        with tab:
            st.markdown(f"<div class='group-section-title'>{html_lib.escape(group)}</div>", unsafe_allow_html=True)
            out = temp[temp[group_col] == group].drop(columns=[group_col], errors="ignore")
            sortable_table(
                out,
                f"{table_title_prefix} - {group}",
                f"{table_key_prefix}_{str(group).lower().replace(' ', '_').replace('/', '_')}",
                default_sort=default_sort,
                default_ascending=default_ascending,
                help_text=help_text,
            )

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
    """Infer the most specific centre label available from the filename.

    Preserve GLOW/SEEN when stated. Use the broad location only when the
    filename identifies Bukit Batok or Nanyang without a service label.
    """
    name = re.sub(r"[^a-z0-9]+", " ", str(file_name).lower()).strip()
    is_glow = "glow" in name
    is_seen = "seen" in name
    is_bb = "bukit batok" in name or " bb " in f" {name} " or name.endswith(" bb") or "glow bb" in name or "seen bb" in name
    is_ny = "nanyang" in name or " ny " in f" {name} " or name.endswith(" ny") or "glow ny" in name or "seen ny" in name

    if is_bb:
        if is_glow:
            return "GLOW Bukit Batok"
        if is_seen:
            return "Tzu Chi SEEN @ Bukit Batok"
        return "Bukit Batok"
    if is_ny:
        if is_glow:
            return "GLOW Nanyang"
        if is_seen:
            return "Tzu Chi SEEN @ Nanyang"
        return "Nanyang"

    stem = Path(str(file_name)).stem.replace("_", " ").replace("-", " ").strip()
    return stem or "Centre"


def canonical_centre_name(value) -> str | None:
    """Return the most specific supported centre label present in the data.

    Explicit GLOW/SEEN labels are preserved. Generic Bukit Batok or Nanyang is
    used only when the source does not identify the service.
    """
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "unknown", "unknown centre", "-"}:
        return None
    key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    is_glow = "glow" in key
    is_seen = "seen" in key
    is_bb = "bukit batok" in key or key in {"bb", "glow bb", "seen bb"}
    is_ny = "nanyang" in key or key in {"ny", "glow ny", "seen ny"}

    if is_bb:
        if is_glow:
            return "GLOW Bukit Batok"
        if is_seen:
            return "Tzu Chi SEEN @ Bukit Batok"
        return "Bukit Batok"
    if is_ny:
        if is_glow:
            return "GLOW Nanyang"
        if is_seen:
            return "Tzu Chi SEEN @ Nanyang"
        return "Nanyang"
    return text


def detect_centre_series(df: pd.DataFrame, fallback_centre: str) -> pd.Series:
    """Assign a centre without inventing a more specific service label.

    The filename/user fallback is authoritative for the uploaded file. If it is
    only ``Bukit Batok`` or ``Nanyang``, every row remains at that broad location
    even when an imported helper/summary sheet contains an old GLOW/SEEN value.
    A specific GLOW or SEEN label is used only when the filename/fallback itself
    supplies that specificity. This is deliberately conservative for accuracy.
    """
    if df is None or df.empty:
        return pd.Series(dtype="object")

    fallback = canonical_centre_name(fallback_centre) or str(fallback_centre).strip()
    fallback_key = str(fallback).lower()
    fallback_is_specific = "glow" in fallback_key or "seen" in fallback_key

    # A generic file-level label must stay generic. Do not silently upgrade it
    # to GLOW/SEEN using values carried over from helper or Unique Seniors sheets.
    if fallback in {"Bukit Batok", "Nanyang"} or not fallback_is_specific:
        return pd.Series([fallback] * len(df), index=df.index, dtype="object")

    # For a specifically named file, keep that exact centre consistently. This
    # avoids rows being split because of blank, stale, or inconsistent cell data.
    return pd.Series([fallback] * len(df), index=df.index, dtype="object")


def _without_dataframe_attrs(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with metadata removed before pandas concatenation.

    Some loaded frames carry DataFrame objects inside ``attrs`` (for example,
    the parsed Summary table). Pandas 2.x/3.x compares attrs while concatenating;
    comparing DataFrames produces an ambiguous truth-value error. Summary data is
    stored separately, so row-level frames should not retain those attrs.
    """
    clean = frame.copy()
    clean.attrs = {}
    return clean


def safe_concat_frames(frames, **kwargs) -> pd.DataFrame:
    """Concatenate DataFrames after removing attrs that pandas cannot compare."""
    clean_frames = [
        _without_dataframe_attrs(frame)
        for frame in list(frames)
        if isinstance(frame, pd.DataFrame) and not frame.empty
    ]
    if not clean_frames:
        return pd.DataFrame()
    result = pd.concat(clean_frames, **kwargs)
    result.attrs = {}
    return result


def add_centre_frame(store: dict, centre: str, frame: pd.DataFrame) -> None:
    """Append data for a centre without overwriting an earlier uploaded file."""
    clean_frame = _without_dataframe_attrs(frame)
    if centre in store and isinstance(store[centre], pd.DataFrame) and not store[centre].empty:
        store[centre] = safe_concat_frames(
            [store[centre], clean_frame], ignore_index=True, sort=False
        )
    else:
        store[centre] = clean_frame


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
    st.markdown("Upload KPI workbooks, choose programme type, then generate the dashboard.")

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

uploaded_files = st.file_uploader(
    "Upload KPI workbook(s)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
    key=f"kpi_files_{upload_reset_counter}",
    help="Upload one or more attendance/KPI or programme-level files here. The app automatically detects the file type and assigns each row to its centre.",
)

if not uploaded_files:
    stored_snapshot = load_anonymized_snapshot()
    if stored_snapshot:
        show_stored_snapshot(stored_snapshot)
        st.stop()

    st.markdown(
        """
        <div class="section-card">
        <h3>How to use</h3>
        <span class="success-pill">1. Upload one or more KPI workbooks in the single uploader above</span>
        <span class="success-pill">2. The app detects attendance versus programme-level files automatically</span>
        <span class="success-pill">3. Records keep GLOW/SEEN labels when available; otherwise Bukit Batok or Nanyang is used</span>
        <span class="success-pill">4. Confirm mappings and generate the dashboard</span>
        <p class="small-note">Use the Clear uploaded data button before loading a completely new dataset. Files for the same centre are combined automatically.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

with st.sidebar:
    st.markdown("## Uploaded Files")
    fallback_centre_names = []
    for i, file in enumerate(uploaded_files):
        default_name = infer_centre_name(file.name)
        fallback_centre_names.append(
            st.text_input(
                f"Fallback centre if {file.name} has no Centre field",
                value=default_name,
                key=f"fallback_centre_name_{i}_{file.name}",
            ).strip() or default_name
        )

centre_frames = {}
centre_summary_kpis = {}
centre_summary_tables = {}
sheet_names_by_centre = {}
programme_frames_raw = {}

with st.spinner("Reading uploaded file(s)..."):
    for file, fallback_centre in zip(uploaded_files, fallback_centre_names):
        # Inspect the simple first-row structure first. Programme-level exports
        # normally have event/session fields but no member-name field. Attendance
        # workbooks are then read with the dedicated attendance-sheet parser.
        try:
            file.seek(0)
            general_raw = read_general_uploaded_file(file)
        except Exception:
            general_raw = pd.DataFrame()

        general_norm = normalize_columns(general_raw) if not general_raw.empty else pd.DataFrame()
        programme_detected = detect_programme_columns(general_norm) if not general_norm.empty else {}
        attendance_detected = detect_columns(general_norm) if not general_norm.empty else {}
        is_programme_file = bool(
            programme_detected.get("event_name")
            and (programme_detected.get("total_sessions") or programme_detected.get("event_domain") or programme_detected.get("start_date"))
            and not attendance_detected.get("member")
        )

        if is_programme_file:
            prog_raw = general_raw.copy()
            prog_raw["__uploaded_centre__"] = detect_centre_series(prog_raw, fallback_centre)
            for detected_centre, centre_df in prog_raw.groupby("__uploaded_centre__", dropna=False):
                detected_centre = canonical_centre_name(detected_centre) or canonical_centre_name(fallback_centre) or fallback_centre
                centre_df = centre_df.copy()
                centre_df["__uploaded_centre__"] = detected_centre
                add_centre_frame(programme_frames_raw, detected_centre, centre_df)
            continue

        file.seek(0)
        df_one, sheet_names_one = read_uploaded_file(file)
        if df_one.empty:
            continue
        df_one = df_one.copy()
        df_one["__uploaded_centre__"] = detect_centre_series(df_one, fallback_centre)
        df_one["centre"] = df_one["__uploaded_centre__"]
        detected_centres = sorted(df_one["__uploaded_centre__"].dropna().astype(str).unique().tolist())

        for detected_centre, centre_df in df_one.groupby("__uploaded_centre__", dropna=False):
            detected_centre = canonical_centre_name(detected_centre) or canonical_centre_name(fallback_centre) or fallback_centre
            centre_df = centre_df.copy()
            centre_df["__uploaded_centre__"] = detected_centre
            centre_df["centre"] = detected_centre
            add_centre_frame(centre_frames, detected_centre, centre_df)
            sheet_names_by_centre.setdefault(detected_centre, [])
            sheet_names_by_centre[detected_centre] = sorted(set(sheet_names_by_centre[detected_centre] + list(sheet_names_one)))

        if len(detected_centres) == 1:
            detected_centre = detected_centres[0]
            summary_kpis = df_one.attrs.get("summary_kpis", {}) if hasattr(df_one, "attrs") else {}
            centre_summary_kpis[detected_centre] = summary_kpis
            summary_one = df_one.attrs.get("summary_table", pd.DataFrame()) if hasattr(df_one, "attrs") else pd.DataFrame()
            if isinstance(summary_one, pd.DataFrame) and not summary_one.empty:
                summary_one = summary_one.copy()
                if "Centre" in summary_one.columns:
                    summary_one["Centre"] = detected_centre
                else:
                    summary_one.insert(0, "Centre", detected_centre)
            centre_summary_tables[detected_centre] = summary_one
        else:
            for detected_centre in detected_centres:
                centre_summary_kpis.setdefault(detected_centre, {})
                centre_summary_tables.setdefault(detected_centre, pd.DataFrame())

all_centres = sorted(set(centre_frames.keys()) | set(programme_frames_raw.keys()))
if not all_centres:
    st.error("The uploaded file(s) appear to be empty or unreadable.")
    st.stop()

centre_options = ["All Centres"] + all_centres
selected_centre = st.sidebar.selectbox("View KPI for centre", centre_options, index=0)

if selected_centre == "All Centres":
    df_all = safe_concat_frames(centre_frames.values(), ignore_index=True, sort=False)
    programme_raw_all = safe_concat_frames(programme_frames_raw.values(), ignore_index=True, sort=False)
    summary_kpis = combine_summary_kpis(centre_summary_kpis)
    summary_tables = [t for t in centre_summary_tables.values() if isinstance(t, pd.DataFrame) and not t.empty]
    summary_table = safe_concat_frames(summary_tables, ignore_index=True, sort=False)
    sheet_names = [s for sheets in sheet_names_by_centre.values() for s in sheets]
else:
    df_all = centre_frames.get(selected_centre, pd.DataFrame()).copy()
    programme_raw_all = programme_frames_raw.get(selected_centre, pd.DataFrame()).copy()
    summary_kpis = centre_summary_kpis.get(selected_centre, {})
    summary_table = centre_summary_tables.get(selected_centre, pd.DataFrame())
    sheet_names = sheet_names_by_centre.get(selected_centre, [])

centre_kpi_table = make_centre_kpi_table(centre_summary_kpis)

st.success(f"Automatically assigned data to {len(all_centres)} centre dashboard(s). Viewing: {selected_centre}. Read {len(sheet_names)} attendance sheet(s).")

# Programme-level mapping. This lets other centre files with fields such as Centre,
# End Date, Event Domain, Is AAP?, Name of Event, Target Attendees, and Total Sessions
# contribute useful KPIs even when they do not contain member-level attendance data.
programme_clean = pd.DataFrame()
if not programme_raw_all.empty:
    prog_preview = normalize_columns(programme_raw_all)
    prog_detected = detect_programme_columns(prog_preview)
    prog_cols = prog_preview.columns.tolist()
    with st.expander("Programme File Mapping", expanded=True):
        st.markdown("Map these columns for Bukit Batok, Nanyang, or other programme-level files.")
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
    "|".join([f"upload:{f.name}-{getattr(f, 'size', 0)}" for f in uploaded_files])
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

# Preserve the centre detected from each attendance row. The protected
# __uploaded_centre__ field is created during ingestion from the workbook's
# explicit Centre/Location/Site value and falls back to the file label only
# when that row has no centre information.
if df.columns.duplicated().any():
    collapsed = {}
    for col in dict.fromkeys(list(df.columns)):
        subset = df.loc[:, df.columns == col]
        if subset.shape[1] == 1:
            collapsed[col] = subset.iloc[:, 0]
        else:
            collapsed[col] = subset.replace(r"^\s*$", pd.NA, regex=True).bfill(axis=1).iloc[:, 0]
    df = pd.DataFrame(collapsed)
if "__uploaded_centre__" in df.columns:
    df["centre"] = df["__uploaded_centre__"].astype(str).str.strip()
elif "centre" in df.columns:
    df["centre"] = df["centre"].map(canonical_centre_name)
elif selected_centre != "All Centres":
    df["centre"] = selected_centre

df = df.dropna(subset=["activity", "member"])
df["activity"] = df["activity"].astype(str).str.strip()
df["member"] = df["member"].astype(str).str.strip()

# Apply explicit member-status rules once, before any KPI or detail calculation.
# This guarantees that every dashboard section uses the same status-adjusted data.
df, member_status_audit = apply_member_status_rules(df)

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

# Individual senior attendance frequency must be calculated only from real
# attendance-register tabs. Never use Summary, Unique Seniors, lookup, or
# calculation sheets for per-senior attendance counts, as those sheets are
# already aggregated and will create false readings.
if "__attendance_register__" in df_att.columns:
    df_att = df_att[df_att["__attendance_register__"].fillna(False).astype(bool)].copy()
if "__sheet__" in df_att.columns:
    bad_sheet_mask = df_att["__sheet__"].astype(str).str.lower().str.contains(
        r"summary|unique|template|lookup|pivot|frequency", regex=True, na=False
    )
    df_att = df_att[~bad_sheet_mask].copy()

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

# KPI Overview and all detail tables must use ONE source of truth: df_att.
# Do not mix the workbook Summary sheet with cleaned attendance rows, because that
# makes the KPI cards disagree with the IB/OB attendance-frequency tables.
# Summary is still read elsewhere for reference/centre comparisons, but member KPIs
# below are calculated from the same cleaned attended rows used by the tables.
valid_member_rows = df_att.copy()
valid_member_rows["member"] = valid_member_rows["member"].astype(str).str.strip()
valid_member_rows = valid_member_rows[
    (valid_member_rows["member"] != "")
    & (valid_member_rows["member"].str.lower() != "nan")
].copy()

ib_members = set(valid_member_rows.loc[valid_member_rows["ib_ob_clean"] == "IB", "member"].dropna().astype(str).str.strip())
ob_members = set(valid_member_rows.loc[valid_member_rows["ib_ob_clean"] == "OB", "member"].dropna().astype(str).str.strip())
male_members = set(valid_member_rows.loc[valid_member_rows["gender_clean"] == "Male", "member"].dropna().astype(str).str.strip())

total_attendances = raw_total_attendances
total_unique_seniors = int(valid_member_rows["member"].nunique())
total_activities = raw_total_activities
avg_attendance_per_activity = raw_avg_attendance_per_activity
male_attendances = raw_male_attendances
male_unique_members = len(male_members)
male_attendance_pct = raw_male_attendance_pct
male_unique_pct = male_unique_members / total_unique_seniors if total_unique_seniors else 0
ib_count = len(ib_members)
ob_count = len(ob_members)
# Inactive is a member-level KPI: highest recorded AAP count for the senior <= 2.
inactive_count = 0
if "aap" in df.columns:
    inactive_kpi_source = df.copy()
    inactive_kpi_source["member"] = inactive_kpi_source["member"].astype(str).str.strip()
    inactive_kpi_source = inactive_kpi_source[
        (inactive_kpi_source["member"] != "")
        & (inactive_kpi_source["member"].str.lower() != "nan")
    ].copy()
    inactive_kpi_source["aap"] = pd.to_numeric(inactive_kpi_source["aap"], errors="coerce")
    inactive_kpi_source = inactive_kpi_source.dropna(subset=["aap"])
    if not inactive_kpi_source.empty:
        inactive_by_member = inactive_kpi_source.groupby("member", as_index=False)["aap"].max()
        inactive_count = int((inactive_by_member["aap"] <= 2).sum())

new_ib = int(summary_kpis.get("new_ib", 0)) if isinstance(summary_kpis, dict) else 0
new_ob = int(summary_kpis.get("new_ob", 0)) if isinstance(summary_kpis, dict) else 0
ib_pct = ib_count / total_unique_seniors if total_unique_seniors else 0
ob_pct = ob_count / total_unique_seniors if total_unique_seniors else 0
inactive_pct = inactive_count / total_unique_seniors if total_unique_seniors else 0

# Headline KPI cards must follow the workbook Summary page.
# Detail tables below still use cleaned attendance rows because the Summary page
# contains totals only, not member-level attendance frequency.
status_adjustments_present = bool(
    member_status_audit.get("passed_on_excluded", 0)
    or member_status_audit.get("moved_out_reclassified", 0)
)
# A workbook Summary total cannot reflect dashboard-only status corrections.
# When corrections were applied, use the cleaned rows as the KPI source so cards,
# tables and charts remain internally consistent.
use_summary_kpis = isinstance(summary_kpis, dict) and bool(summary_kpis) and not status_adjustments_present
if use_summary_kpis:
    cleaned_snapshot = {
        "programmes": total_activities,
        "attendances": total_attendances,
        "unique_members": total_unique_seniors,
        "ib_count": ib_count,
        "ob_count": ob_count,
        "male_count": male_unique_members,
        "inactive_count": inactive_count,
    }
    total_activities = int(summary_kpis.get("programmes", total_activities) or 0)
    total_attendances = int(summary_kpis.get("attendances", total_attendances) or 0)
    total_unique_seniors = int(summary_kpis.get("unique_members", total_unique_seniors) or 0)
    avg_attendance_per_activity = float(summary_kpis.get("avg_attendance_per_programme", 0) or 0)
    ib_count = int(summary_kpis.get("ib_count", ib_count) or 0)
    ob_count = int(summary_kpis.get("ob_count", ob_count) or 0)
    male_unique_members = int(summary_kpis.get("male_count", male_unique_members) or 0)
    inactive_count = int(summary_kpis.get("inactive_count", inactive_count) or 0)
    new_ib = int(summary_kpis.get("new_ib", new_ib) or 0)
    new_ob = int(summary_kpis.get("new_ob", new_ob) or 0)
    ib_pct = float(summary_kpis.get("ib_pct", ib_count / total_unique_seniors if total_unique_seniors else 0) or 0)
    ob_pct = float(summary_kpis.get("ob_pct", ob_count / total_unique_seniors if total_unique_seniors else 0) or 0)
    male_unique_pct = float(summary_kpis.get("male_pct", male_unique_members / total_unique_seniors if total_unique_seniors else 0) or 0)
    inactive_pct = float(summary_kpis.get("inactive_pct", inactive_count / total_unique_seniors if total_unique_seniors else 0) or 0)
    # The Summary sheet stores male as unique male seniors, so display the same
    # number in the Male card to avoid mixing attendance count with member count.
    male_attendances = male_unique_members
    male_attendance_pct = male_unique_pct

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
    st.caption("KPI Overview is taken directly from the workbook Summary page / OVERALL TOTAL row. Member-frequency tables below use cleaned attendance rows because the Summary page has no per-senior frequency breakdown.")
    # Let staff see when the raw attendance-register rows do not exactly match
    # the approved Summary totals without replacing the Summary source of truth.
    raw_mismatches = []
    if cleaned_snapshot.get("attendances") != total_attendances:
        raw_mismatches.append(f"Attendances: Summary {total_attendances:,} vs cleaned rows {cleaned_snapshot.get('attendances', 0):,}")
    if cleaned_snapshot.get("unique_members") != total_unique_seniors:
        raw_mismatches.append(f"Unique Members: Summary {total_unique_seniors:,} vs cleaned rows {cleaned_snapshot.get('unique_members', 0):,}")
    if cleaned_snapshot.get("ib_count") != ib_count:
        raw_mismatches.append(f"IB: Summary {ib_count:,} vs cleaned rows {cleaned_snapshot.get('ib_count', 0):,}")
    if cleaned_snapshot.get("ob_count") != ob_count:
        raw_mismatches.append(f"OB: Summary {ob_count:,} vs cleaned rows {cleaned_snapshot.get('ob_count', 0):,}")
    if raw_mismatches:
        st.info("Summary source is being used for KPI Overview. Raw attendance-register check: " + "; ".join(raw_mismatches) + ".")
else:
    st.caption("No Summary page totals were found, so KPI Overview is calculated from cleaned attended rows.")

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
        # Use the most specific row-level centre detected during ingestion.
        temp["centre"] = temp["__uploaded_centre__"].astype(str).str.strip()
    elif "centre" in temp.columns:
        temp["centre"] = temp["centre"].map(canonical_centre_name)

    if fallback_centre and fallback_centre != "All Centres":
        if "centre" not in temp.columns:
            temp["centre"] = fallback_centre
        else:
            missing_centre = temp["centre"].isna() | temp["centre"].astype(str).str.strip().isin(["", "nan", "None"])
            temp.loc[missing_centre, "centre"] = fallback_centre

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

    agg_fields = {"activity": ["count", pd.Series.nunique]}
    if "centre" in temp.columns:
        agg_fields["centre"] = "first"
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
        "centre_first": "Centre",
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

# Transparent audit of explicit member-status adjustments.
if member_status_audit.get("passed_on_excluded", 0) or member_status_audit.get("moved_out_reclassified", 0):
    st.info(
        f"Member-status adjustments applied: "
        f"{member_status_audit.get('passed_on_excluded', 0)} passed-on/deceased senior(s) excluded; "
        f"{member_status_audit.get('moved_out_reclassified', 0)} moved-out senior(s) reclassified to OB. "
        "KPI cards use cleaned attendance rows for this upload because the workbook Summary does not include these dashboard corrections."
    )
    with st.expander("View member-status adjustment audit"):
        passed = member_status_audit.get("passed_on_members", [])
        moved = member_status_audit.get("moved_out_members", [])
        if passed:
            st.markdown("**Excluded — Passed On / Deceased**")
            st.dataframe(pd.DataFrame({"Member": passed, "Action": "Excluded from all analytics"}), hide_index=True, use_container_width=True)
        if moved:
            st.markdown("**Reclassified — Moved Out**")
            st.dataframe(pd.DataFrame({"Member": moved, "Action": "Reclassified to OB"}), hide_index=True, use_container_width=True)

st.markdown("## Senior Attendance Frequency")
st.caption("These tables count only cleaned `Attended` rows from real attendance-register sheets. Summary and Unique Seniors sheets are excluded from individual senior frequency counts.")

ib_senior_freq = make_senior_attendance_frequency(df_att, "IB", selected_centre)
ob_senior_freq = make_senior_attendance_frequency(df_att, "OB", selected_centre)

# Reconciliation rule:
# - KPI cards follow the workbook Summary page when it is available.
# - Frequency tables are member-level audits from raw attendance rows.
# To avoid showing two different headline totals, the tab labels use the same
# IB/OB counts as the KPI cards.  If the raw attendance rows disagree, show a
# clear warning instead of silently displaying inconsistent numbers.
ib_tab_count = ib_count if use_summary_kpis else len(ib_senior_freq)
ob_tab_count = ob_count if use_summary_kpis else len(ob_senior_freq)

if len(ib_senior_freq) != ib_count or len(ob_senior_freq) != ob_count:
    mismatch_bits = []
    if len(ib_senior_freq) != ib_count:
        mismatch_bits.append(f"IB: Summary/KPI {ib_count:,} vs attendance rows {len(ib_senior_freq):,}")
    if len(ob_senior_freq) != ob_count:
        mismatch_bits.append(f"OB: Summary/KPI {ob_count:,} vs attendance rows {len(ob_senior_freq):,}")
    st.warning(
        "IB/OB consistency check: " + "; ".join(mismatch_bits) +
        ". The KPI cards and tab labels use the Summary page. The tables below show the raw attendance-row audit so you can identify workbook data that needs updating."
    )

ib_tab, ob_tab = st.tabs([f"IB Seniors ({ib_tab_count:,})", f"OB Seniors ({ob_tab_count:,})"])
with ib_tab:
    sortable_table(
        ib_senior_freq,
        "IB Seniors by Attendance Frequency",
        "ib_seniors_attendance_frequency",
        default_sort="Attendances",
        default_ascending=False,
        help_text="IB means an explicit `Is Client = Yes` / `IB` value. Tab count follows the Summary/KPI count; rows show the raw attendance audit.",
    )
with ob_tab:
    sortable_table(
        ob_senior_freq,
        "OB Seniors by Attendance Frequency",
        "ob_seniors_attendance_frequency",
        default_sort="Attendances",
        default_ascending=False,
        help_text="OB means an explicit `Is Client = No` / `OB` value only. Blank or invalid client values are not counted as OB.",
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

# Gender attendance counts are calculated from the same cleaned attended rows used for total attendances.
# Important: male_attendances is NOT total programme attendance; it is the subset where Gender == Male.
male_activity = (
    df_att[df_att["gender_clean"] == "Male"]
    .groupby("activity")
    .agg(male_attendances=("member", "count"), unique_male_attendances=("member", pd.Series.nunique))
    .reset_index()
)
female_activity = (
    df_att[df_att["gender_clean"] == "Female"]
    .groupby("activity")
    .agg(female_attendances=("member", "count"), unique_female_attendances=("member", pd.Series.nunique))
    .reset_index()
)
activity_stats = activity_stats.merge(male_activity, on="activity", how="left")
activity_stats = activity_stats.merge(female_activity, on="activity", how="left")
gender_count_cols = [
    "male_attendances", "unique_male_attendances",
    "female_attendances", "unique_female_attendances",
]
activity_stats[gender_count_cols] = activity_stats[gender_count_cols].fillna(0).astype(int)
activity_stats["male_pct"] = activity_stats["male_attendances"] / activity_stats["total_attendances"].replace(0, np.nan)
activity_stats["unique_male_pct"] = activity_stats["unique_male_attendances"] / activity_stats["unique_seniors"].replace(0, np.nan)
activity_stats["female_pct"] = activity_stats["female_attendances"] / activity_stats["total_attendances"].replace(0, np.nan)
activity_stats["unique_female_pct"] = activity_stats["unique_female_attendances"] / activity_stats["unique_seniors"].replace(0, np.nan)
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





def make_profile_label(attendances: int) -> str:
    """Objective engagement bands based only on total attendance counts in the KPI workbook."""
    try:
        n = int(attendances)
    except Exception:
        n = 0
    if n >= 20:
        return "Super Active (≥20)"
    if n >= 10:
        return "Active (10–19)"
    if n >= 5:
        return "Regular (5–9)"
    if n >= 3:
        return "Occasional (3–4)"
    return "Low / Inactive (≤2)"


def make_programme_type_overview(source_df: pd.DataFrame) -> pd.DataFrame:
    """One-time vs recurring is derived only from workbook attendance rows.

    Programme Type is based on whether the programme appears on more than one date/session in
    the uploaded KPI workbook. No external or inferred preference data is used.
    """
    if source_df is None or source_df.empty or "programme_type" not in source_df.columns:
        return pd.DataFrame()
    out = source_df.groupby("programme_type").agg(
        Programmes=("activity", pd.Series.nunique),
        Attendances=("member", "count"),
        Unique_Seniors=("member", pd.Series.nunique),
    ).reset_index().rename(columns={"programme_type": "Programme Type"})
    out["Avg Attendance / Programme"] = out["Attendances"] / out["Programmes"].replace(0, np.nan)
    out["Avg Attendance / Senior"] = out["Attendances"] / out["Unique_Seniors"].replace(0, np.nan)
    return out.sort_values("Attendances", ascending=False).reset_index(drop=True)


def make_profile_summary(source_df: pd.DataFrame) -> pd.DataFrame:
    """Senior engagement groups based only on attendance frequency."""
    if source_df is None or source_df.empty:
        return pd.DataFrame()
    senior = source_df.groupby("member").agg(
        Attendances=("activity", "count"),
        Unique_Programmes=("activity", pd.Series.nunique),
        IB_OB=("ib_ob_clean", "first"),
        Gender=("gender_clean", "first"),
    ).reset_index()
    senior["Engagement Level"] = senior["Attendances"].apply(make_profile_label)
    profile = senior.groupby(["Engagement Level", "IB_OB", "Gender"], dropna=False).agg(
        Seniors=("member", pd.Series.nunique),
        Total_Attendances=("Attendances", "sum"),
        Avg_Attendances=("Attendances", "mean"),
        Avg_Unique_Programmes=("Unique_Programmes", "mean"),
    ).reset_index()
    # Keep engagement groups in a natural low-to-high order for every table/chart.
    order = {
        "Low / Inactive (≤2)": 1,
        "Occasional (3–4)": 2,
        "Regular (5–9)": 3,
        "Active (10–19)": 4,
        "Super Active (≥20)": 5,
    }
    profile["_order"] = profile["Engagement Level"].map(order).fillna(99)
    return profile.sort_values(["_order", "Seniors"], ascending=[True, False]).drop(columns=["_order"]).reset_index(drop=True)


def make_profile_programme_preferences(source_df: pd.DataFrame, profile_col: str) -> pd.DataFrame:
    """Programme preferences by explicit workbook field: IB/OB or Gender."""
    if source_df is None or source_df.empty or profile_col not in source_df.columns:
        return pd.DataFrame()
    out = source_df.groupby([profile_col, "activity", "programme_type"], dropna=False).agg(
        Attendances=("member", "count"),
        Unique_Seniors=("member", pd.Series.nunique),
    ).reset_index()
    total_by_profile = out.groupby(profile_col)["Attendances"].transform("sum")
    out["Share Within Group"] = out["Attendances"] / total_by_profile.replace(0, np.nan)
    out = out.rename(columns={profile_col: "Group", "activity": "Programme", "programme_type": "Programme Type"})
    return out.sort_values(["Group", "Attendances"], ascending=[True, False]).reset_index(drop=True)


def make_programme_preferences_by_status(source_df: pd.DataFrame, status_value: str) -> pd.DataFrame:
    temp = source_df[source_df.get("ib_ob_clean", "") == status_value].copy() if source_df is not None and not source_df.empty else pd.DataFrame()
    if temp.empty:
        return pd.DataFrame()
    out = temp.groupby(["activity", "programme_type"], dropna=False).agg(
        Attendances=("member", "count"),
        Unique_Seniors=("member", pd.Series.nunique),
    ).reset_index()
    out["Avg Attendance / Senior"] = out["Attendances"] / out["Unique_Seniors"].replace(0, np.nan)
    return out.rename(columns={"activity": "Programme", "programme_type": "Programme Type"}).sort_values("Attendances", ascending=False).reset_index(drop=True)


def make_favourite_programmes(source_df: pd.DataFrame, status_value: str = "IB") -> pd.DataFrame:
    temp = source_df[source_df.get("ib_ob_clean", "") == status_value].copy() if source_df is not None and not source_df.empty else pd.DataFrame()
    if temp.empty:
        return pd.DataFrame()
    counts = temp.groupby(["member", "activity", "programme_type"]).size().reset_index(name="Times Attended")
    counts = counts.sort_values(["member", "Times Attended", "activity"], ascending=[True, False, True])
    favourite = counts.groupby("member", as_index=False).first()
    totals = temp.groupby("member").agg(
        Total_Attendances=("activity", "count"),
        Unique_Programmes=("activity", pd.Series.nunique),
        Latest_Attendance=("date", "max") if "date" in temp.columns else ("activity", "count"),
        Gender=("gender_clean", "first"),
    ).reset_index()
    out = favourite.merge(totals, on="member", how="left")
    out["Favourite Share"] = out["Times Attended"] / out["Total_Attendances"].replace(0, np.nan)
    out["Engagement Level"] = out["Total_Attendances"].apply(make_profile_label)
    if "Latest_Attendance" in out.columns:
        out["Latest_Attendance"] = pd.to_datetime(out["Latest_Attendance"], errors="coerce").dt.date
    out = out.rename(columns={
        "member": "Senior Name",
        "activity": "Favourite Programme",
        "programme_type": "Favourite Programme Type",
        "Total_Attendances": "Total Attendances",
        "Unique_Programmes": "Unique Programmes",
        "Latest_Attendance": "Latest Attendance",
    })
    preferred = ["Senior Name", "Gender", "Total Attendances", "Unique Programmes", "Favourite Programme", "Times Attended", "Favourite Share", "Favourite Programme Type", "Engagement Level", "Latest Attendance"]
    return out[[c for c in preferred if c in out.columns]].sort_values(["Total Attendances", "Senior Name"], ascending=[False, True]).reset_index(drop=True)


def make_senior_programme_breakdown(source_df: pd.DataFrame, senior_name: str) -> pd.DataFrame:
    if source_df is None or source_df.empty or not senior_name:
        return pd.DataFrame()
    temp = source_df[source_df["member"].astype(str).str.strip() == str(senior_name).strip()].copy()
    if temp.empty:
        return pd.DataFrame()
    out = temp.groupby(["activity", "programme_type"], dropna=False).agg(
        Attendances=("member", "count"),
        Sessions=("date", pd.Series.nunique) if "date" in temp.columns else ("member", "count"),
    ).reset_index()
    out["Share"] = out["Attendances"] / out["Attendances"].sum()
    return out.rename(columns={"activity": "Programme", "programme_type": "Programme Type"}).sort_values("Attendances", ascending=False).reset_index(drop=True)


st.markdown("## Programme & Senior Attendance Analytics")
st.caption("Only data directly available from the KPI workbook is shown. Inferred categories, living-alone analysis, AI recommendations, and other unsupported fields have been removed.")

profile_tab, type_tab, pref_tab = st.tabs([
    "Senior Attendance Groups",
    "One-Time vs Recurring",
    "Programme Preferences",
])

with profile_tab:
    profile_summary_raw = make_profile_summary(df_att)
    engagement_order = [
        "Low / Inactive (≤2)",
        "Occasional (3–4)",
        "Regular (5–9)",
        "Active (10–19)",
        "Super Active (≥20)",
    ]

    st.markdown("### Senior Attendance Groups")
    st.caption(
        "Engagement levels are calculated only from total attended rows: "
        "Low/Inactive ≤2, Occasional 3–4, Regular 5–9, Active 10–19, Super Active ≥20."
    )

    if not profile_summary_raw.empty and "Engagement Level" in profile_summary_raw.columns:
        chart_df = profile_summary_raw.groupby("Engagement Level", as_index=False)["Seniors"].sum()
        chart_df["Engagement Level"] = pd.Categorical(chart_df["Engagement Level"], categories=engagement_order, ordered=True)
        chart_df = chart_df.sort_values("Engagement Level")
        fig = px.bar(
            chart_df,
            x="Engagement Level",
            y="Seniors",
            title="Number of Seniors by Attendance Group",
            text="Seniors",
            category_orders={"Engagement Level": engagement_order},
        )
        fig.update_layout(
            title_font_size=20,
            title_font_color="#0D2B45",
            xaxis_title=None,
            yaxis_title=None,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=60, b=120),
            xaxis_tickangle=-35,
            showlegend=False,
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig, use_container_width=True, key="attendance_group_chart_ordered")

        ib_ob_df = profile_summary_raw.groupby(["Engagement Level", "IB_OB"], as_index=False)["Seniors"].sum()
        ib_ob_df["Engagement Level"] = pd.Categorical(ib_ob_df["Engagement Level"], categories=engagement_order, ordered=True)
        ib_ob_df = ib_ob_df.sort_values("Engagement Level")
        fig2 = px.bar(
            ib_ob_df,
            x="Engagement Level",
            y="Seniors",
            color="IB_OB",
            barmode="group",
            title="Senior Attendance Groups by IB/OB",
            text="Seniors",
            category_orders={"Engagement Level": engagement_order, "IB_OB": ["IB", "OB", "Unknown"]},
        )
        fig2.update_layout(
            title_font_size=20,
            title_font_color="#0D2B45",
            xaxis_title=None,
            yaxis_title=None,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=60, b=120),
            xaxis_tickangle=-35,
            legend_title_text="IB / OB",
        )
        fig2.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig2, use_container_width=True, key="attendance_group_ib_ob_chart")

        gender_df = profile_summary_raw.groupby(["Engagement Level", "Gender"], as_index=False)["Seniors"].sum()
        gender_df["Engagement Level"] = pd.Categorical(gender_df["Engagement Level"], categories=engagement_order, ordered=True)
        gender_df = gender_df.sort_values("Engagement Level")
        fig3 = px.bar(
            gender_df,
            x="Engagement Level",
            y="Seniors",
            color="Gender",
            barmode="group",
            title="Senior Attendance Groups by Gender",
            text="Seniors",
            category_orders={"Engagement Level": engagement_order, "Gender": ["Male", "Female", "Unknown"]},
        )
        fig3.update_layout(
            title_font_size=20,
            title_font_color="#0D2B45",
            xaxis_title=None,
            yaxis_title=None,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=60, b=120),
            xaxis_tickangle=-35,
            legend_title_text="Gender",
        )
        fig3.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig3, use_container_width=True, key="attendance_group_gender_chart")

        with st.expander("Show detailed attendance group table"):
            sortable_table(
                nice_columns(profile_summary_raw),
                "Senior Attendance Groups by IB/OB and Gender",
                "senior_attendance_groups",
                default_sort="Seniors",
                default_ascending=False,
                help_text="Detailed numbers behind the charts. Tables are hidden by default to reduce clutter.",
            )
    else:
        st.info("No senior attendance group data available.")

with type_tab:
    programme_type_overview = make_programme_type_overview(df_att)
    sortable_table(
        programme_type_overview,
        "One-Time vs Recurring Programme Overview",
        "programme_type_overview",
        default_sort="Attendances",
        default_ascending=False,
        help_text="Programme type is derived only from attendance dates in the workbook. A programme appearing on more than one date/session is treated as recurring.",
    )
    if not programme_type_overview.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            bar_chart(programme_type_overview, "Programme Type", "Programmes", "Number of Programmes by Type", key="programme_type_programmes_chart")
        with col_b:
            bar_chart(programme_type_overview, "Programme Type", "Attendances", "Attendances by Programme Type", key="programme_type_attendances_chart")

with pref_tab:
    st.markdown("### Programme Preferences by Clearly Separated Groups")
    st.caption("IB/OB and Gender are shown in separate tabs so groups are not visually mixed.")
    status_pref_tab, gender_pref_tab = st.tabs(["IB / OB", "Gender"])

    with status_pref_tab:
        pref_df = nice_columns(make_profile_programme_preferences(df_att, "ib_ob_clean"))
        if "Group" in pref_df.columns:
            render_grouped_tables(
                pref_df,
                "Group",
                "Programme Preferences by IB/OB",
                "programme_preferences_ib_ob",
                default_sort="Attendances",
                default_ascending=False,
                help_text="IB and OB programme preferences are separated into clear tabs.",
            )
        else:
            st.info("No IB/OB preference data available.")

    with gender_pref_tab:
        gender_pref_df = nice_columns(make_profile_programme_preferences(df_att, "gender_clean"))
        if "Group" in gender_pref_df.columns:
            render_grouped_tables(
                gender_pref_df,
                "Group",
                "Programme Preferences by Gender",
                "programme_preferences_gender",
                default_sort="Attendances",
                default_ascending=False,
                help_text="Gender preferences are separated into clear tabs.",
            )
        else:
            st.info("No gender preference data available.")

st.markdown("## IB Preferences")
st.caption("This section focuses only on IB seniors using real attendance rows from the KPI workbook.")

ib_pref_tab, ib_fav_tab, ib_gender_tab, ib_profile_tab = st.tabs([
    "Popular IB Programmes",
    "Favourite Programme per IB Senior",
    "IB Preferences by Gender",
    "IB Senior Profile Card",
])

with ib_pref_tab:
    ib_prefs = make_programme_preferences_by_status(df_att, "IB")
    sortable_table(
        ib_prefs,
        "Most Popular Programmes Among IB Seniors",
        "ib_programme_preferences",
        default_sort="Attendances",
        default_ascending=False,
        help_text="Attendances counts every attended IB row. Unique Seniors counts distinct IB seniors per programme.",
    )
    if not ib_prefs.empty:
        bar_chart(ib_prefs.head(20), "Programme", "Attendances", "Top IB Programmes by Attendance", color="Programme Type", key="ib_preference_chart")

with ib_fav_tab:
    ib_favourites = make_favourite_programmes(df_att, "IB")
    sortable_table(
        ib_favourites,
        "Favourite Programme of Every IB Senior",
        "ib_favourite_programmes",
        default_sort="Total Attendances",
        default_ascending=False,
        help_text="Favourite Programme is the programme the senior attended most often. Favourite Share shows how much of their attendance is concentrated in that programme.",
    )

with ib_gender_tab:
    ib_only = df_att[df_att.get("ib_ob_clean", "") == "IB"].copy()
    ib_gender_prefs = nice_columns(make_profile_programme_preferences(ib_only, "gender_clean"))
    if "Group" in ib_gender_prefs.columns:
        render_grouped_tables(
            ib_gender_prefs,
            "Group",
            "IB Programme Preferences by Gender",
            "ib_gender_preferences",
            default_sort="Attendances",
            default_ascending=False,
            help_text="Male and female IB preferences are separated into clear tabs.",
        )
    else:
        st.info("No IB gender preference data available.")

@streamlit_fragment
def render_ib_profile_card_section(att_df: pd.DataFrame):
    ib_names = sorted(att_df.loc[att_df["ib_ob_clean"] == "IB", "member"].dropna().astype(str).str.strip().unique())
    if not ib_names:
        st.info("No IB seniors found in the cleaned attendance rows.")
        return

    # Keep the displayed profile card locked to the latest selected value.
    # In Streamlit, widgets rerun the script; using a stable session-state
    # value prevents the selectbox from visually changing while the card still
    # shows the previous senior.
    if st.session_state.get("ib_profile_selected_senior") not in ib_names:
        st.session_state["ib_profile_selected_senior"] = ib_names[0]

    def sync_ib_profile_selection():
        chosen = st.session_state.get("ib_profile_card_select")
        if chosen in ib_names:
            st.session_state["ib_profile_selected_senior"] = chosen

    st.caption("Use the selector below to view one IB senior. Gender is taken from the cleaned attendance rows in the KPI workbook.")
    current_index = ib_names.index(st.session_state["ib_profile_selected_senior"])
    selected_widget_value = st.selectbox(
        "Select an IB senior",
        ib_names,
        index=current_index,
        key="ib_profile_card_select",
        on_change=sync_ib_profile_selection,
        help="Selection is stored in session state so the profile card updates to the selected senior.",
    )
    selected_ib_senior = st.session_state.get("ib_profile_selected_senior", selected_widget_value)
    if selected_ib_senior not in ib_names:
        selected_ib_senior = selected_widget_value
        st.session_state["ib_profile_selected_senior"] = selected_ib_senior

    senior_breakdown = make_senior_programme_breakdown(att_df, selected_ib_senior)
    senior_rows = att_df[att_df["member"].astype(str).str.strip() == selected_ib_senior]
    total_att = len(senior_rows)
    unique_prog = senior_rows["activity"].nunique() if not senior_rows.empty else 0
    latest = pd.to_datetime(senior_rows["date"], errors="coerce").max().date() if "date" in senior_rows.columns and not senior_rows.empty else ""
    fav = senior_breakdown.iloc[0]["Programme"] if not senior_breakdown.empty else "-"

    gender = "Unknown"
    if not senior_rows.empty:
        if "gender_clean" in senior_rows.columns:
            gender_values = senior_rows["gender_clean"].dropna().astype(str).str.strip()
        elif "gender" in senior_rows.columns:
            gender_values = senior_rows["gender"].apply(clean_gender).dropna().astype(str).str.strip()
        else:
            gender_values = pd.Series(dtype=str)
        gender_values = gender_values[~gender_values.str.lower().isin(["", "nan", "none", "unknown"])]
        if not gender_values.empty:
            gender = gender_values.mode().iloc[0]

    render_kpi_cards([
        ("Selected IB Senior", selected_ib_senior),
        ("Gender", gender),
        ("Total Attendances", f"{total_att:,}"),
        ("Unique Programmes", f"{unique_prog:,}"),
        ("Favourite Programme", fav),
        ("Engagement Level", make_profile_label(total_att)),
        ("Latest Attendance", str(latest)),
        ("IB/OB", "IB"),
    ])
    sortable_table(
        senior_breakdown,
        f"Programme Breakdown for {selected_ib_senior}",
        "selected_ib_senior_breakdown",
        default_sort="Attendances",
        default_ascending=False,
    )
    if not senior_breakdown.empty:
        bar_chart(senior_breakdown, "Programme", "Attendances", f"{selected_ib_senior}'s Programme Preferences", color="Programme Type", key="selected_ib_senior_chart")

with ib_profile_tab:
    render_ib_profile_card_section(df_att)

st.markdown("## Activity Insights")
summary_cols = [
    "activity", "programme_type", "total_attendances", "unique_seniors", "number_of_sessions",
    "avg_attendance_per_session", "returning_members", "retention_score",
    "male_attendances", "female_attendances", "unique_male_attendances", "unique_female_attendances",
    "male_pct", "female_pct", "unique_male_pct", "unique_female_pct", "sample_note"
]
summary_cols = [c for c in summary_cols if c in activity_stats.columns]
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
    cols = ["activity", "total_attendances", "unique_seniors", "male_attendances", "unique_male_attendances", "male_pct", "ib_participants", "ob_participants", "attendance_rate"]
    cols = [c for c in cols if c in one_time.columns]
    one_time_display = nice_columns(one_time[cols])
    one_time_sorted = sortable_table(one_time_display, "One-Time Programmes", "one_time", default_sort="Total Attendances", default_ascending=False)
    bar_chart(one_time_sorted.head(20), "Activity", "Total Attendances", "One-Time Programmes by Attendance", key="one_time_chart")
else:
    st.info("No one-time programmes found for this filter.")

recurring = activity_stats[activity_stats["programme_type"] == "Recurring"].copy()
if not recurring.empty:
    cols = ["activity", "total_attendances", "number_of_sessions", "avg_attendance_per_session", "returning_members", "retention_score", "unique_seniors"]
    cols = [c for c in cols if c in recurring.columns]
    recurring_display = nice_columns(recurring[cols])
    recurring_sorted = sortable_table(recurring_display, "Recurring Programmes", "recurring", default_sort="Avg Attendance Per Session", default_ascending=False)
    bar_chart(recurring_sorted.head(20), "Activity", "Avg Attendance Per Session", "Recurring Programmes by Average Attendance per Session", key="recurring_chart")
else:
    st.info("No recurring programmes found for this filter.")

st.markdown("## Gender Participation Analysis")
st.caption("Total Attendances is shown first so it is clear that Male/Female Attendances are subsets of the same programme total. For example, 17 total attendances can display as 16 male + 1 female.")
gender_cols = [
    "activity", "programme_type", "total_attendances", "male_attendances", "female_attendances",
    "unique_seniors", "unique_male_attendances", "unique_female_attendances",
    "male_pct", "female_pct", "sample_note",
]
gender_cols = [c for c in gender_cols if c in activity_stats.columns]
gender_display = activity_stats[gender_cols].copy()
gender_sorted = sortable_table(
    nice_columns(gender_display),
    "Gender Attendances by Activity",
    "gender_activity",
    default_sort="Total Attendances",
    default_ascending=False,
    help_text="Total Attendances counts all attended rows. Male/Female Attendances count only rows with that gender value.",
)
chart_left, chart_right = st.columns(2)
with chart_left:
    bar_chart(gender_sorted.head(20), "Activity", "Male Attendances", "Male Attendances by Activity", color="Programme Type", key="male_att_chart")
with chart_right:
    bar_chart(gender_sorted.head(20), "Activity", "Female Attendances", "Female Attendances by Activity", color="Programme Type", key="female_att_chart")

# Save only aggregate values. Unsupported recommendation outputs are intentionally removed.
rec_df = pd.DataFrame()
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
        inactive_source["centre"] = inactive_source["__uploaded_centre__"].astype(str).str.strip()
    elif selected_centre != "All Centres":
        inactive_source["centre"] = selected_centre

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
