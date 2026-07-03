import streamlit as st
import pandas as pd
import re

st.set_page_config(
    page_title="GLOW KPI Dashboard",
    page_icon="📊",
    layout="wide"
)

# -----------------------------
# Helper Functions
# -----------------------------

def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def find_column(df, possible_names):
    cols = {clean_text(col): col for col in df.columns}
    for name in possible_names:
        key = clean_text(name)
        if key in cols:
            return cols[key]
    return None


def extract_number(value):
    """
    Converts values like:
    20 (57%) -> 20
    14 (54%） -> 14
    blank -> 0
    """
    if pd.isna(value):
        return 0

    text = str(value).strip()
    if text == "":
        return 0

    match = re.search(r"\d+", text)
    if match:
        return int(match.group())

    return 0


def load_all_sheets(uploaded_file):
    excel = pd.ExcelFile(uploaded_file)
    all_dfs = []

    for sheet in excel.sheet_names:
        temp_df = pd.read_excel(uploaded_file, sheet_name=sheet)
        temp_df["Source Sheet"] = sheet
        all_dfs.append(temp_df)

    return pd.concat(all_dfs, ignore_index=True)


def calculate_from_summary_table(df):
    """
    Reads KPI summary rows such as:
    OVERALL TOTAL:
    JULY TOTAL:
    """

    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]

    first_col = df.columns[0]

    overall_rows = df[
        df[first_col]
        .astype(str)
        .str.strip()
        .str.upper()
        .str.contains("OVERALL TOTAL", na=False)
    ]

    if overall_rows.empty:
        return None

    row = overall_rows.iloc[-1]

    programmes_col = find_column(df, ["Programmes"])
    attendances_col = find_column(df, ["Attendances"])
    unique_col = find_column(df, ["Unique Members", "Unique Seniors"])
    ib_col = find_column(df, ["IB (%)", "IB"])
    ob_col = find_column(df, ["OB (%)", "OB"])
    male_col = find_column(df, ["Male (%)", "Male"])
    inactive_col = find_column(df, ["Inactive (<=2AAP) (%)", "Inactive"])
    new_ib_col = find_column(df, ["New IB"])
    new_ob_col = find_column(df, ["New OB"])

    total_attendances = extract_number(row[attendances_col]) if attendances_col else 0
    unique_seniors = extract_number(row[unique_col]) if unique_col else 0
    activities = extract_number(row[programmes_col]) if programmes_col else 0
    ib = extract_number(row[ib_col]) if ib_col else 0
    ob = extract_number(row[ob_col]) if ob_col else 0
    male = extract_number(row[male_col]) if male_col else 0
    inactive = extract_number(row[inactive_col]) if inactive_col else 0
    new_ib = extract_number(row[new_ib_col]) if new_ib_col else 0
    new_ob = extract_number(row[new_ob_col]) if new_ob_col else 0

    avg_attendance = total_attendances / activities if activities else 0
    male_unique_pct = male / unique_seniors * 100 if unique_seniors else 0
    inactive_pct = inactive / unique_seniors * 100 if unique_seniors else 0
    ib_pct = ib / unique_seniors * 100 if unique_seniors else 0
    ob_pct = ob / unique_seniors * 100 if unique_seniors else 0

    return {
        "total_attendances": total_attendances,
        "unique_seniors": unique_seniors,
        "activities": activities,
        "avg_attendance": avg_attendance,
        "ib": ib,
        "ob": ob,
        "male": male,
        "inactive": inactive,
        "new_ib": new_ib,
        "new_ob": new_ob,
        "ib_pct": ib_pct,
        "ob_pct": ob_pct,
        "male_unique_pct": male_unique_pct,
        "inactive_pct": inactive_pct,
    }


def calculate_from_raw_data(df):
    """
    Backup calculation if there is no OVERALL TOTAL row.
    """

    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]

    name_col = find_column(df, ["Name", "Member", "Unique Members", "Senior"])
    status_col = find_column(df, ["Status", "Attendance Status"])
    gender_col = find_column(df, ["Gender", "Sex"])
    activity_col = find_column(df, ["Activity Name", "Activity", "Programme", "Programmes"])
    client_col = find_column(df, ["Is Client", "Client", "IB/OB"])
    aap_col = find_column(df, ["AAP Participated this year", "AAP", "AAP Participated"])

    if status_col:
        df = df[df[status_col].apply(clean_text) == "attended"]

    if name_col:
        df = df[df[name_col].notna()]
        df = df[df[name_col].astype(str).str.strip() != ""]
        df["Name_clean"] = df[name_col].astype(str).str.strip().str.lower()
    else:
        df["Name_clean"] = df.index.astype(str)

    total_attendances = len(df)
    unique_seniors = df["Name_clean"].nunique()

    activities = 0
    if activity_col:
        activities = df[activity_col].dropna().astype(str).str.strip()
        activities = activities[activities != ""].nunique()

    male_df = pd.DataFrame()
    if gender_col:
        male_df = df[df[gender_col].apply(clean_text).isin(["male", "m"])]

    male_attendances = len(male_df)
    unique_male = male_df["Name_clean"].nunique() if not male_df.empty else 0

    ib = 0
    ob = 0
    if client_col:
        ib_df = df[df[client_col].apply(clean_text).isin(["yes", "ib", "true", "client"])]
        ob_df = df[df[client_col].apply(clean_text).isin(["no", "ob", "false", "non-client"])]
        ib = ib_df["Name_clean"].nunique()
        ob = ob_df["Name_clean"].nunique()

    inactive = 0
    if aap_col:
        df["AAP_numeric"] = pd.to_numeric(df[aap_col], errors="coerce")
        inactive_df = df[df["AAP_numeric"] <= 2]
        inactive = inactive_df["Name_clean"].nunique()

    avg_attendance = total_attendances / activities if activities else 0
    male_unique_pct = unique_male / unique_seniors * 100 if unique_seniors else 0
    inactive_pct = inactive / unique_seniors * 100 if unique_seniors else 0
    ib_pct = ib / unique_seniors * 100 if unique_seniors else 0
    ob_pct = ob / unique_seniors * 100 if unique_seniors else 0

    return {
        "total_attendances": total_attendances,
        "unique_seniors": unique_seniors,
        "activities": activities,
        "avg_attendance": avg_attendance,
        "ib": ib,
        "ob": ob,
        "male": unique_male,
        "inactive": inactive,
        "new_ib": 0,
        "new_ob": 0,
        "ib_pct": ib_pct,
        "ob_pct": ob_pct,
        "male_unique_pct": male_unique_pct,
        "inactive_pct": inactive_pct,
        "male_attendances": male_attendances,
    }


def get_kpis(df):
    summary_kpis = calculate_from_summary_table(df)

    if summary_kpis:
        return summary_kpis, "summary"

    raw_kpis = calculate_from_raw_data(df)
    return raw_kpis, "raw"


def metric_card(title, value):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


# -----------------------------
# Styling
# -----------------------------

st.markdown(
    """
    <style>
    body {
        background-color: #F8F4EC;
    }

    .main {
        background-color: #F8F4EC;
    }

    h1 {
        color: #30323D;
        font-size: 42px;
        font-weight: 800;
    }

    .metric-card {
        background-color: #FFFFFF;
        border: 1px solid #E6CFA8;
        border-radius: 24px;
        padding: 28px;
        height: 150px;
        box-shadow: 0px 8px 18px rgba(0,0,0,0.04);
        margin-bottom: 24px;
    }

    .metric-title {
        color: #53633F;
        font-size: 18px;
        font-weight: 500;
        margin-bottom: 18px;
    }

    .metric-value {
        color: #0D2B45;
        font-size: 44px;
        font-weight: 800;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# -----------------------------
# Main App
# -----------------------------

st.title("KPI Overview")

uploaded_file = st.file_uploader(
    "Upload your KPI Excel file",
    type=["xlsx", "xls"]
)

if uploaded_file is None:
    st.info("Please upload your Excel file to view the KPI dashboard.")
    st.stop()

try:
    df = load_all_sheets(uploaded_file)
    kpis, source_type = get_kpis(df)

    if source_type == "summary":
        st.success("Dashboard calculated using the OVERALL TOTAL row from your Excel summary.")
    else:
        st.warning("No OVERALL TOTAL row found. Dashboard calculated from raw attendance data.")

    row1 = st.columns(4)
    with row1[0]:
        metric_card("Total Attendances", f"{kpis['total_attendances']:,}")
    with row1[1]:
        metric_card("Unique Seniors", f"{kpis['unique_seniors']:,}")
    with row1[2]:
        metric_card("Activities / Programmes", f"{kpis['activities']:,}")
    with row1[3]:
        metric_card("Avg Attendance / Activity", f"{kpis['avg_attendance']:.1f}")

    row2 = st.columns(4)
    with row2[0]:
        metric_card("IB Seniors", f"{kpis['ib']:,}")
    with row2[1]:
        metric_card("OB Seniors", f"{kpis['ob']:,}")
    with row2[2]:
        metric_card("Male Seniors", f"{kpis['male']:,}")
    with row2[3]:
        metric_card("Inactive Seniors", f"{kpis['inactive']:,}")

    row3 = st.columns(4)
    with row3[0]:
        metric_card("IB %", f"{kpis['ib_pct']:.1f}%")
    with row3[1]:
        metric_card("OB %", f"{kpis['ob_pct']:.1f}%")
    with row3[2]:
        metric_card("Male Unique %", f"{kpis['male_unique_pct']:.1f}%")
    with row3[3]:
        metric_card("Inactive %", f"{kpis['inactive_pct']:.1f}%")

    st.divider()

    st.subheader("Uploaded Data Preview")
    st.dataframe(df, use_container_width=True)

except Exception as e:
    st.error("Something went wrong while reading the file.")
    st.exception(e)
