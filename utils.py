from datetime import datetime
import re
import pandas as pd

__all__ = [
    "read_uploaded_file",
    "guess_attended",
    "standardize_date",
    "classify_programme_type",
    "infer_recurring_activities",
    "build_recommendations",
]


def _extract_date_from_sheet_name(sheet_name):
    """Return a parsed date from sheet names like 4May2026 Attendances."""
    match = re.search(r"(\d{1,2})\s*([A-Za-z]+)\s*(\d{4})", str(sheet_name))
    if not match:
        return pd.NaT
    return pd.to_datetime(" ".join(match.groups()), errors="coerce")


def _find_header_row(raw_df):
    """Find the row containing the real attendance headers."""
    for idx, row in raw_df.iterrows():
        values = {str(v).strip().lower() for v in row.dropna().tolist()}
        if {"activity name", "status", "name"}.issubset(values):
            return idx
    return None


def _clean_sheet_table(raw_df, sheet_name):
    """Convert one raw Excel sheet into a clean table, if it is an attendance sheet."""
    header_row = _find_header_row(raw_df)
    if header_row is None:
        return None

    header = raw_df.iloc[header_row].astype(str).str.strip().tolist()
    data = raw_df.iloc[header_row + 1 :].copy()
    data.columns = header
    data = data.loc[:, ~data.columns.astype(str).str.lower().str.startswith("unnamed")]
    data = data.dropna(how="all")

    # Keep only real attendance columns and ignore calculation blocks pasted on the right.
    expected = [
        "Centre",
        "Activity Name",
        "Status",
        "Name",
        "Is Client",
        "Within Boundary",
        "Gender",
        "AAP Participated count this year",
        "Age",
        "CFS",
        "Created on",
        "Has met KPI (CFS)",
    ]
    keep = [c for c in expected if c in data.columns]
    if not {"Activity Name", "Status", "Name"}.issubset(set(keep)):
        return None
    data = data[keep].copy()
    data["__sheet__"] = sheet_name
    data["__sheet_date__"] = _extract_date_from_sheet_name(sheet_name)
    # Explicit flag used by the dashboard to ensure senior frequency tables
    # are calculated only from real attendance-register sheets, never from
    # Summary / Unique Seniors / lookup sheets.
    data["__attendance_register__"] = True
    return data



def _parse_summary_count(value):
    """Parse Summary cells like '18 (62%)', '-', or numeric values into a count."""
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else float(value)
    text = str(value).strip()
    if not text or text in {"-", "–", "—"}:
        return 0
    # Remove thousands separators first. Without this, values formatted
    # for display such as "1,017" were parsed as 1, which caused
    # the KPI Overview to show Attendances = 1 even though the
    # Summary sheet said 1,017.
    text_for_number = text.replace(",", "")
    m = re.search(r"(-?\d+(?:\.\d+)?)", text_for_number)
    if not m:
        return 0
    number = float(m.group(1))
    return int(number) if number.is_integer() else number


def _format_summary_date(value):
    """Format Summary Date cells like Excel display: d/m/yyyy or total text."""
    if pd.isna(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime)):
        return f"{value.day}/{value.month}/{value.year}"
    text = str(value).strip()
    # Keep manually typed slash dates exactly as Excel shows them, e.g. 4/5/2026.
    if "/" in text:
        return text
    # Reformat ISO-like dates only.
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", text):
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.notna(parsed):
            return f"{parsed.day}/{parsed.month}/{parsed.year}"
    return text


def _format_summary_metric(value):
    """Clean Summary KPI cells for display, e.g. '6(30%)' -> '6 (30%)'."""
    if pd.isna(value):
        return ""
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not float(value).is_integer():
            return f"{value:.1%}" if 0 <= value <= 1 else f"{value:,.2f}".rstrip("0").rstrip(".")
        return f"{int(value):,}"
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(\d)\s*\(", r"\1 (", text)
    return text


def _find_summary_header(raw_df):
    """Find the Summary sheet header row containing the mandatory KPI headers."""
    required = {"programmes", "attendances", "unique members"}
    for idx, row in raw_df.iterrows():
        values = {str(v).strip().lower() for v in row.dropna().tolist()}
        if required.issubset(values):
            return idx
    return None


def _read_summary_table(raw_sheets):
    """Read the mandatory KPI table from the Summary sheet.

    This workbook's Summary sheet is the source of truth for headline KPIs.
    The table can contain multiple monthly sections with repeated headers, so
    this function finds the header row that contains the mandatory KPI names,
    keeps all valid rows below it, and ignores repeated header rows/blank rows.
    """
    summary_name = next((s for s in raw_sheets if str(s).strip().lower() == "summary"), None)
    if summary_name is None:
        return pd.DataFrame()

    raw = raw_sheets[summary_name]
    header_row = _find_summary_header(raw)
    if header_row is None:
        return pd.DataFrame()

    headers = raw.iloc[header_row].astype(str).str.strip().tolist()
    data = raw.iloc[header_row + 1:].copy()
    data.columns = headers
    data = data.dropna(how="all")

    # Keep only the KPI table columns the user needs.
    cols = [
        "Month", "Week", "Date", "Programmes", "Attendances", "Unique Members",
        "IB (%)", "OB (%)", "Male (%)", "Inactive (<=2AAP) (%)", "New IB", "New OB",
    ]
    cols = [c for c in cols if c in data.columns]
    if not cols or "Date" not in cols:
        return pd.DataFrame()
    data = data[cols].copy()

    # Remove repeated header rows in later monthly sections and rows that only
    # contain helper percentages below monthly totals.
    data = data[data["Date"].astype(str).str.strip().str.lower() != "date"].copy()
    data = data[data["Date"].notna()].copy()
    data = data.dropna(how="all")

    # Format the table for display so it mirrors the Excel Summary sheet.
    if "Date" in data.columns:
        data["Date"] = data["Date"].apply(_format_summary_date)
    for c in data.columns:
        if c != "Date":
            data[c] = data[c].apply(_format_summary_metric)
    return data.reset_index(drop=True)


def _read_summary_kpis(raw_sheets):
    """Return aggregate KPI values from the Summary sheet when available.

    The Summary sheet is treated as the source of truth for the KPI Overview.
    The dashboard must not recalculate these headline numbers from attendance
    sheets because duplicate raw sheets and copied sheets can make the totals
    drift from the workbook's approved Summary.
    """
    data = _read_summary_table(raw_sheets)
    if data.empty or "Date" not in data.columns:
        return {}

    date_text = data["Date"].astype(str).str.strip()

    # Source of truth: use the explicit OVERALL TOTAL row when present.
    overall_rows = data[date_text.str.upper().str.contains("OVERALL TOTAL", na=False)].copy()
    source_detail = "Summary OVERALL TOTAL row"

    if not overall_rows.empty:
        # Use the last OVERALL TOTAL row if the workbook has older copies above.
        selected = overall_rows.tail(1)
    else:
        # Fallback only if the workbook has no OVERALL TOTAL row.
        monthly_rows = data[date_text.str.upper().str.contains("TOTAL", na=False)].copy()
        monthly_rows = monthly_rows[~monthly_rows["Date"].astype(str).str.upper().str.contains("OVERALL", na=False)]
        if not monthly_rows.empty:
            selected = monthly_rows
            source_detail = "Summary monthly total rows"
        else:
            parsed_dates = pd.to_datetime(date_text, errors="coerce")
            selected = data[parsed_dates.notna()].copy()
            source_detail = "Summary dated rows"

    def sum_col(col):
        if col not in selected.columns:
            return 0
        return sum(_parse_summary_count(v) for v in selected[col].tolist())

    programmes = int(sum_col("Programmes"))
    attendances = int(sum_col("Attendances"))
    unique_members = int(sum_col("Unique Members"))
    ib_count = int(sum_col("IB (%)"))
    ob_count = int(sum_col("OB (%)"))
    male_count = int(sum_col("Male (%)"))
    inactive_count = int(sum_col("Inactive (<=2AAP) (%)"))
    new_ib = int(sum_col("New IB"))
    new_ob = int(sum_col("New OB"))

    return {
        "source": "Summary",
        "source_detail": source_detail,
        "programmes": programmes,
        "attendances": attendances,
        "unique_members": unique_members,
        "unique_members_daily_sum": unique_members,
        "ib_count": ib_count,
        "ob_count": ob_count,
        "male_count": male_count,
        "inactive_count": inactive_count,
        "new_ib": new_ib,
        "new_ob": new_ob,
        "ib_pct": ib_count / unique_members if unique_members else 0,
        "ob_pct": ob_count / unique_members if unique_members else 0,
        "male_pct": male_count / unique_members if unique_members else 0,
        "inactive_pct": inactive_count / unique_members if unique_members else 0,
        "avg_attendance_per_programme": attendances / programmes if programmes else 0,
    }

def read_uploaded_file(uploaded_file):
    """Read CSV or Excel and combine only real attendance tables.

    The workbook can contain Summary, Unique Seniors, Template, duplicated raw sheets,
    and formula blocks. This reader detects the actual attendance header row and, when
    sheets with "Attend" in the name exist, uses those sheets only to avoid double-counting.
    """
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file), [uploaded_file.name]

    try:
        raw_sheets = pd.read_excel(uploaded_file, sheet_name=None, header=None, dtype=object, engine="openpyxl")
    except Exception:
        raw_sheets = pd.read_excel(uploaded_file, sheet_name=None, header=None, dtype=object)

    summary_kpis = _read_summary_kpis(raw_sheets)
    summary_table = _read_summary_table(raw_sheets)

    skip_terms = ("summary", "unique", "template")

    # Use all real attendance-register tabs, including common naming variants.
    # Some GLOW files contain official tabs named with plural "Attendances",
    # while later imports may use singular "Attendance" or the typo "Attendnace".
    # Excluding those tabs made Summary totals and dashboard details disagree
    # because valid attended rows from those dates were missed.
    #
    # Plain date sheets such as "4May2026" are still excluded because they can be
    # copied duplicates of the official register. The de-duplication below also
    # protects against accidental duplicate attendance tabs for the same date.
    attendance_name_pattern = re.compile(r"\b(attendance|attendances|attendnace|attendnaces)\b", re.IGNORECASE)
    official_attendance_items = [
        (s, d) for s, d in raw_sheets.items()
        if attendance_name_pattern.search(str(s).strip())
        and not any(t in str(s).lower() for t in skip_terms)
    ]
    candidate_items = official_attendance_items or [
        (s, d) for s, d in raw_sheets.items()
        if not any(t in str(s).lower() for t in skip_terms)
    ]

    frames = []
    used_sheets = []
    for sheet_name, raw_df in candidate_items:
        cleaned = _clean_sheet_table(raw_df, sheet_name)
        if cleaned is not None and not cleaned.empty:
            frames.append(cleaned)
            used_sheets.append(sheet_name)

    if frames:
        combined = pd.concat(frames, ignore_index=True, sort=False)

        # Do not de-duplicate rows here. The Summary sheet's Attendances total
        # counts every Attended row in the attendance registers, and the senior
        # frequency tables are explicitly row-frequency reports. Excluding plain
        # date-only copied sheets above prevents the old double-counting problem
        # without accidentally removing legitimate repeated attendance rows.

        out = combined.reset_index(drop=True)
        out.attrs["summary_kpis"] = summary_kpis
        out.attrs["summary_table"] = summary_table
        return out, used_sheets

    # Last-resort fallback for simple files with headers already on row 1.
    try:
        sheets = pd.read_excel(uploaded_file, sheet_name=None, engine="openpyxl")
    except Exception:
        sheets = pd.read_excel(uploaded_file, sheet_name=None)

    frames = []
    for sheet_name, df in sheets.items():
        if any(t in str(sheet_name).lower() for t in skip_terms):
            continue
        df = df.copy()
        df["__sheet__"] = sheet_name
        frames.append(df)

    if not frames:
        empty = pd.DataFrame()
        empty.attrs["summary_kpis"] = summary_kpis if "summary_kpis" in locals() else {}
        empty.attrs["summary_table"] = summary_table if "summary_table" in locals() else pd.DataFrame()
        return empty, []
    out = pd.concat(frames, ignore_index=True, sort=False)
    out.attrs["summary_kpis"] = summary_kpis if "summary_kpis" in locals() else {}
    out.attrs["summary_table"] = summary_table if "summary_table" in locals() else pd.DataFrame()
    return out, list(sheets.keys())

def guess_attended(val):
    """Return True/False from common attendance values."""
    if pd.isna(val):
        return False

    text = str(val).strip().lower()
    positives = {"present", "yes", "attended", "y", "1", "true", "attend", "参加", "出席"}
    negatives = {"absent", "no", "n", "0", "false", "缺席", "no-show", "no show", "cancelled", "canceled", "cancel"}

    if text in positives:
        return True
    if text in negatives:
        return False
    if any(term in text for term in ["no-show", "no show", "absent", "cancelled", "canceled"]):
        return False

    try:
        return float(text) > 0
    except Exception:
        return False


def standardize_date(value):
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.to_datetime(value, errors="coerce")
    return pd.to_datetime(str(value), errors="coerce")


def infer_recurring_activities(df, activity_col="activity", date_col="date"):
    """Infer recurring activities from multiple sheets or multiple unique dates."""
    if activity_col not in df.columns:
        return []

    if "__sheet__" in df.columns:
        counts = (
            df.dropna(subset=[activity_col, "__sheet__"])
            .groupby(activity_col)["__sheet__"]
            .nunique()
        )
        recurring = counts[counts > 1].index.tolist()
        if recurring:
            return sorted(recurring)

    if date_col and date_col in df.columns:
        temp = df.copy()
        temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
        counts = (
            temp.dropna(subset=[activity_col, date_col])
            .groupby(activity_col)[date_col]
            .nunique()
        )
        return sorted(counts[counts > 1].index.tolist())

    return []


def classify_programme_type(df, activity_col="activity", date_col="date"):
    """Return a Series classifying each row as Recurring or One-Time."""
    if activity_col not in df.columns:
        return pd.Series(["One-Time"] * len(df), index=df.index, dtype="object")

    recurring = set(infer_recurring_activities(df, activity_col=activity_col, date_col=date_col))
    return df[activity_col].apply(lambda x: "Recurring" if x in recurring else "One-Time")


def build_recommendations(activity_stats):
    """Create simple, explainable programme recommendations."""
    if activity_stats.empty:
        return pd.DataFrame(columns=["activity", "programme_type", "recommendation", "reason"])

    mean_att = float(activity_stats["total_attendances"].fillna(0).mean())
    mean_ret = float(activity_stats["retention_score"].fillna(0).mean()) if "retention_score" in activity_stats else 0
    mean_unique = float(activity_stats["unique_seniors"].fillna(0).mean())

    rows = []
    for _, row in activity_stats.iterrows():
        activity = row.get("activity", "Unknown")
        programme_type = row.get("programme_type", "Unknown")
        total_att = float(row.get("total_attendances", 0) or 0)
        unique_seniors = float(row.get("unique_seniors", 0) or 0)
        retention = float(row.get("retention_score", 0) or 0)
        male_pct = float(row.get("male_pct", 0) or 0)

        if total_att >= mean_att and unique_seniors >= mean_unique:
            recommendation = "Continue / Scale Up"
            reason = "Strong attendance and strong reach compared with the programme average."
        elif total_att < mean_att and unique_seniors < mean_unique:
            recommendation = "Review Format & Promotion"
            reason = "Both attendance and unique senior reach are below average."
        elif programme_type == "Recurring" and retention < mean_ret:
            recommendation = "Improve Retention"
            reason = "Attendance exists, but repeat participation is weaker than other recurring programmes."
        elif male_pct > 0 and male_pct < 0.2:
            recommendation = "Improve Male Outreach"
            reason = "Male participation appears low, so promotion or programme design may need adjustment."
        else:
            recommendation = "Maintain & Monitor"
            reason = "Performance is acceptable, but should continue to be monitored."

        rows.append(
            {
                "activity": activity,
                "programme_type": programme_type,
                "recommendation": recommendation,
                "reason": reason,
            }
        )

    return pd.DataFrame(rows)
