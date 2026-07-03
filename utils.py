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
    return data


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

    skip_terms = ("summary", "unique", "template")
    candidate_items = [(s, d) for s, d in raw_sheets.items() if not any(t in str(s).lower() for t in skip_terms)]

    frames = []
    used_sheets = []
    for sheet_name, raw_df in candidate_items:
        cleaned = _clean_sheet_table(raw_df, sheet_name)
        if cleaned is not None and not cleaned.empty:
            frames.append(cleaned)
            used_sheets.append(sheet_name)

    if frames:
        combined = pd.concat(frames, ignore_index=True, sort=False)

        # Read every real attendance sheet, then remove duplicate attendance records.
        # Some workbooks contain both exported sheets and copied/raw sheets for the
        # same date, for example "4May2026 Attendances" and "4May2026". These
        # copies may have different AAP counts/ages because the source was exported
        # at a different time, so those changing fields must NOT be part of the
        # duplicate key.
        #
        # A real repeat attendance is still protected because the date and activity
        # remain in the key. One senior attending two different activities on the
        # same date will still count twice, while the same senior/activity/status
        # copied across duplicate sheets will count once.
        key_cols = [
            "__sheet_date__",
            "Activity Name",
            "Status",
            "Name",
        ]
        key_cols = [c for c in key_cols if c in combined.columns]
        if key_cols:
            dedupe_key = combined[key_cols].copy()
            for c in key_cols:
                dedupe_key[c] = dedupe_key[c].astype(str).str.strip().str.lower()
            combined = combined.loc[~dedupe_key.duplicated()].copy()

        return combined.reset_index(drop=True), used_sheets

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
        return pd.DataFrame(), []
    return pd.concat(frames, ignore_index=True, sort=False), list(sheets.keys())

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
