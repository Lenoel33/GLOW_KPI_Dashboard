from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


COLUMN_ALIASES: Dict[str, List[str]] = {
    "date": ["date", "attendance date", "session date", "activity date"],
    "status": ["status", "attendance status", "attended", "attendance"],
    "name": ["name", "member", "member name", "senior", "client name", "participant", "participant name"],
    "activity": ["activity", "activity name", "programme", "program", "programme name", "program name", "session"],
    "is_client": ["is client", "client", "ib", "is ib", "ib/ob", "member type", "client type"],
    "gender": ["gender", "sex"],
    "aap": ["aap", "aap participated this year", "aap this year", "aap participated", "active ageing programme"],
    "centre": ["centre", "center", "site", "location", "aac", "branch"],
}


def _clean_col(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalise_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _find_column(columns: Iterable[str], aliases: List[str]) -> Optional[str]:
    cleaned = {_clean_col(c): c for c in columns}
    alias_cleaned = [_clean_col(a) for a in aliases]

    for alias in alias_cleaned:
        if alias in cleaned:
            return cleaned[alias]

    for clean_name, original in cleaned.items():
        for alias in alias_cleaned:
            if alias and alias in clean_name:
                return original
    return None


def standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename common attendance columns into standard internal names."""
    result = df.copy()
    rename_map = {}
    for standard, aliases in COLUMN_ALIASES.items():
        found = _find_column(result.columns, aliases)
        if found:
            rename_map[found] = standard
    result = result.rename(columns=rename_map)
    return result


def read_excel_all_sheets(uploaded_file) -> pd.DataFrame:
    """Read all sheets from an uploaded Excel file and combine them."""
    sheets = pd.read_excel(uploaded_file, sheet_name=None)
    frames = []
    for sheet_name, sheet_df in sheets.items():
        if sheet_df is None or sheet_df.empty:
            continue
        temp = sheet_df.copy()
        temp["source_sheet"] = sheet_name
        frames.append(temp)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def prepare_attendance_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    df = standardise_columns(raw_df)

    required_defaults = {
        "date": pd.NaT,
        "status": "Attended",
        "name": "",
        "activity": "Unknown Activity",
        "is_client": "",
        "gender": "",
        "aap": pd.NA,
        "centre": "Unknown Centre",
    }
    for col, default in required_defaults.items():
        if col not in df.columns:
            df[col] = default

    df["name"] = df["name"].map(_normalise_text)
    df["activity"] = df["activity"].map(_normalise_text).replace("", "Unknown Activity")
    df["status"] = df["status"].map(_normalise_text)
    df["gender"] = df["gender"].map(lambda x: _normalise_text(x).lower())
    df["centre"] = df["centre"].map(_normalise_text).replace("", "Unknown Centre")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["aap"] = pd.to_numeric(df["aap"], errors="coerce")

    df = df[df["name"].ne("")].copy()
    return df


def attended_only(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    status = df["status"].astype(str).str.strip().str.lower()
    mask = status.eq("attended") | status.eq("present") | status.eq("yes") | status.eq("1") | status.eq("true")
    # If no status values look like attended, assume rows in the sheet are attended records.
    if mask.sum() == 0:
        return df.copy()
    return df[mask].copy()


def is_ib(value: object) -> bool:
    text = _normalise_text(value).lower()
    return text in {"yes", "y", "true", "1", "ib", "client", "inbound"}


def is_ob(value: object) -> bool:
    text = _normalise_text(value).lower()
    return text in {"no", "n", "false", "0", "ob", "non client", "non-client", "outbound"}


def member_summary(attended_df: pd.DataFrame) -> pd.DataFrame:
    """Summarise each member. Inactive is based on total attended records <= 2."""
    if attended_df.empty:
        return pd.DataFrame(columns=["name", "total_records", "last_attendance", "gender", "is_client", "aap", "inactive"])

    summary = (
        attended_df.groupby("name", dropna=False)
        .agg(
            total_records=("name", "size"),
            last_attendance=("date", "max"),
            gender=("gender", "first"),
            is_client=("is_client", "first"),
            aap=("aap", "max"),
        )
        .reset_index()
    )
    summary["inactive"] = summary["total_records"] <= 2
    return summary


def calculate_kpis(df: pd.DataFrame) -> Tuple[Dict[str, object], pd.DataFrame, pd.DataFrame]:
    attended = attended_only(df)
    members = member_summary(attended)

    total_attendances = len(attended)
    unique_members = members["name"].nunique() if not members.empty else 0
    programmes = attended["activity"].nunique() if not attended.empty else 0

    ib_count = int(members["is_client"].map(is_ib).sum()) if not members.empty else 0
    ob_count = int(members["is_client"].map(is_ob).sum()) if not members.empty else 0
    male_count = int(members["gender"].astype(str).str.lower().eq("male").sum()) if not members.empty else 0
    inactive_count = int(members["inactive"].sum()) if not members.empty else 0

    kpis = {
        "Programmes": programmes,
        "Attendances": total_attendances,
        "Unique Members": unique_members,
        "IB Count": ib_count,
        "IB %": ib_count / unique_members if unique_members else 0,
        "OB Count": ob_count,
        "OB %": ob_count / unique_members if unique_members else 0,
        "Male Count": male_count,
        "Male %": male_count / unique_members if unique_members else 0,
        "Inactive Count": inactive_count,
        "Inactive %": inactive_count / unique_members if unique_members else 0,
    }
    return kpis, attended, members


def activity_summary(attended_df: pd.DataFrame) -> pd.DataFrame:
    if attended_df.empty:
        return pd.DataFrame(columns=["Activity", "Attendances", "Unique Members", "Male Members"])

    rows = []
    for activity, group in attended_df.groupby("activity"):
        member_level = member_summary(group)
        rows.append(
            {
                "Activity": activity,
                "Attendances": len(group),
                "Unique Members": group["name"].nunique(),
                "Male Members": int(member_level["gender"].astype(str).str.lower().eq("male").sum()) if not member_level.empty else 0,
                "Returning Members": int((member_level["total_records"] > 1).sum()) if not member_level.empty else 0,
            }
        )
    return pd.DataFrame(rows).sort_values(["Attendances", "Unique Members"], ascending=False)


def format_count_pct(count: int, pct: float) -> str:
    return f"{count} ({pct:.0%})"
