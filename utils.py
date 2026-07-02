from datetime import datetime
import pandas as pd

__all__ = [
    "read_uploaded_file",
    "guess_attended",
    "standardize_date",
    "classify_programme_type",
    "infer_recurring_activities",
    "build_recommendations",
]


def read_uploaded_file(uploaded_file):
    """Read CSV or Excel. Excel files are read across all sheets and combined."""
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file), [uploaded_file.name]

    try:
        sheets = pd.read_excel(uploaded_file, sheet_name=None, engine="openpyxl")
    except Exception:
        sheets = pd.read_excel(uploaded_file, sheet_name=None)

    frames = []
    for sheet_name, df in sheets.items():
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
    negatives = {"absent", "no", "n", "0", "false", "缺席"}

    if text in positives:
        return True
    if text in negatives:
        return False

    try:
        return float(text) > 0
    except Exception:
        return True


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
