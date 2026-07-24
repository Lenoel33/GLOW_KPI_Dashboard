"""AIC/CST project KPI extraction, validation and Streamlit rendering.

This module is intentionally conservative:
- it reads common structured file formats and scans every sheet/table;
- it counts only records explicitly tied to Project APRIL or Project L'Harmoni;
- it never treats ordinary centre attendance as project participation;
- it separates annual, cumulative and three-year measures;
- it exposes unmatched fields, exclusions and formula assumptions for audit.

The numerical targets and monitoring commitments mirror the CST FY2025
application supplied by the user. Project APRIL covers four named centres.
Project L'Harmoni is restricted to the two GLOW centres according to the
user's confirmed operational mapping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Iterable
import html as html_lib
import json
import re
import zipfile

import numpy as np
import pandas as pd
import plotly.express as px
try:
    import streamlit as st
except ModuleNotFoundError:  # Allows calculation tests in environments without Streamlit.
    st = None

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".txt", ".json", ".zip"}

APRIL_CENTRES = [
    "GLOW Bukit Batok",
    "Tzu Chi SEEN @ Bukit Batok",
    "GLOW Nanyang",
    "Tzu Chi SEEN @ Nanyang",
]
LHARMONI_CENTRES = ["GLOW Bukit Batok", "GLOW Nanyang"]

APRIL_TARGETS = [
    ("Seniors onboarded onto APRIL tools", 1000, "Cumulative project total"),
    ("At-risk seniors validated by staff assessments", 0.80, "Percentage of all APRIL-flagged seniors"),
    ("AAC clients reached", 1000, "Per reporting year"),
    ("Volunteers reached", 100, "Per reporting year"),
    ("Caregivers reached", 200, "Per reporting year"),
    ("AAC client beneficiary instances", 3000, "Sum of annual unique client counts across three years"),
    ("Volunteer beneficiary instances", 300, "Sum of annual unique volunteer counts across three years"),
    ("Caregiver beneficiary instances", 600, "Sum of annual unique caregiver counts across three years"),
    ("Total beneficiary instances", 3900, "Three-year beneficiary-table commitment"),
    ("Complete MMSE/GDS/SPPB assessment sets", 100, "Per reporting year"),
    ("Unique seniors tracked", 300, "Across the three-year study period"),
]
LHARMONI_TARGETS = [
    ("Seniors participating in L'Harmoni", 1000, "Cumulative project total"),
    ("GLOW Bukit Batok participants", 500, "Cumulative centre target"),
    ("GLOW Nanyang participants", 500, "Cumulative centre target"),
    ("Tracked seniors improving or maintaining physical and/or cognitive scores", 0.60, "One year after joining"),
    ("Complete MMSE/GDS/SPPB assessment sets", 100, "Per reporting year"),
    ("Unique seniors tracked", 300, "Across the three-year study period"),
]

APRIL_MILESTONES = [
    "Project kick-off",
    "System architecture design",
    "APRIL prototype developed",
    "Training content generator developed",
    "Internal UAT and refinement",
    "Privacy and AI governance review",
    "Pilot deployed at selected AACs",
    "Feedback gathered and adjustments completed",
    "Scaled to all AACs",
    "Volunteer and staff training completed",
    "Outcome evaluation completed",
    "Sector sharing report prepared",
]
LHARMONI_MILESTONES = [
    "Design completed and tender awarded",
    "Staff recruited and trained",
    "Construction completed",
    "L'Harmoni programmes developed",
    "Initial operational capability at 50%",
    "Final operational capability at 100%",
]


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


ALIASES: dict[str, list[str]] = {
    # Common identity and audit fields
    "centre": ["centre", "center", "centre name", "center name", "site", "location", "branch", "aac centre", "service centre"],
    "project": ["project", "project name", "initiative", "programme", "program", "programme name", "program name", "activity", "activity name", "event", "event name"],
    "reporting_date": ["reporting date", "as at date", "as of date", "data cut off date", "data cutoff date", "cut off date", "cutoff date", "report date"],
    "record_date": ["date", "record date", "activity date", "session date", "engagement date", "created on", "created date"],
    "person_id": ["senior id", "client id", "member id", "participant id", "beneficiary id", "user id", "person id", "staff id", "resident id", "case id", "masked nric", "id number"],
    "person_name": ["senior name", "client name", "member name", "participant name", "beneficiary name", "resident name", "full name", "name"],
    "beneficiary_type": ["beneficiary type", "participant type", "person type", "client type", "role", "stakeholder type", "category"],
    "source_reference": ["source reference", "source", "evidence", "evidence reference", "file reference", "record source"],
    "prepared_by": ["prepared by", "data prepared by"],
    "reviewed_by": ["reviewed by", "verified by", "approved by", "reviewer"],
    # Direct APRIL aggregate indicators
    "seniors_onboarded": ["seniors onboarded", "senior onboarded", "april seniors onboarded", "onboarded seniors", "number onboarded", "clients onboarded"],
    "risk_flags_total": ["risk flags total", "total risk flags", "all risk flags", "at risk seniors flagged", "flagged seniors", "total flagged seniors", "seniors flagged by april"],
    "risk_flags_reviewed": ["risk flags reviewed", "flags reviewed", "reviewed risk flags", "at risk seniors reviewed", "flagged seniors reviewed"],
    "risk_flags_validated": ["risk flags validated", "validated risk flags", "validated flags", "at risk seniors validated", "flagged seniors validated"],
    "complete_assessment_sets_annual": ["complete assessment sets annual", "annual complete assessment sets", "complete mmse gds sppb sets", "mmse gds sppb completed", "complete assessments annual", "annual assessment cohort"],
    "unique_tracked_seniors_3_year": ["unique tracked seniors 3 year", "unique seniors tracked 3 years", "three year tracked seniors", "3 year tracked seniors", "unique tracked seniors"],
    "aac_clients_reached_annual": ["aac clients reached annual", "annual aac clients reached", "aac clients reached", "annual clients reached"],
    "volunteers_reached_annual": ["volunteers reached annual", "annual volunteers reached", "volunteers reached", "annual volunteers"],
    "caregivers_reached_annual": ["caregivers reached annual", "annual caregivers reached", "caregivers reached", "annual caregivers"],
    "aac_client_instances_3_year": ["aac client beneficiary instances 3 year", "three year aac client beneficiaries", "aac clients 3 year total", "aac client instances 3 years"],
    "volunteer_instances_3_year": ["volunteer beneficiary instances 3 year", "three year volunteer beneficiaries", "volunteers 3 year total", "volunteer instances 3 years"],
    "caregiver_instances_3_year": ["caregiver beneficiary instances 3 year", "three year caregiver beneficiaries", "caregivers 3 year total", "caregiver instances 3 years"],
    "total_beneficiary_instances_3_year": ["total beneficiary instances 3 year", "total beneficiaries 3 years", "three year total beneficiaries", "total number of beneficiaries"],
    # APRIL raw fields
    "onboarded": ["onboarded", "onboarding status", "april onboarded", "registered for april", "april user", "april registration status"],
    "onboarding_date": ["onboarding date", "onboarded date", "april onboarding date", "registration date", "april registration date"],
    "risk_flag_id": ["risk flag id", "flag id", "alert id", "risk id"],
    "risk_flagged": ["risk flagged", "at risk", "risk flag", "flagged", "april risk flag", "risk status"],
    "risk_reviewed": ["reviewed by staff", "staff reviewed", "risk reviewed", "review status", "flag reviewed"],
    "risk_validated": ["validated as risk", "validated", "risk validated", "staff validation", "validated by staff"],
    "validation_outcome": ["validation outcome", "review outcome", "risk outcome", "staff assessment outcome", "validation status"],
    "validation_assessment_type": ["validation assessment type", "staff assessment type", "assessment used for validation", "validation tool", "validation instrument"],
    "review_date": ["review date", "staff review date", "validation date"],
    # Assessments
    "assessment_episode_id": ["assessment episode id", "assessment set id", "assessment cycle id", "episode id", "visit id"],
    "assessment_type": ["assessment type", "test type", "instrument", "assessment tool", "tool"],
    "assessment_date": ["assessment date", "test date", "screening date", "evaluation date"],
    "assessment_point": ["assessment point", "assessment stage", "timepoint", "baseline follow up", "pre post", "visit type"],
    "mmse": ["mmse", "mini mental state examination", "mini state mental examination", "mmse score"],
    "gds": ["gds", "geriatric depression scale", "gds score"],
    "sppb": ["sppb", "short physical performance battery", "sppb score", "overall sppb score"],
    # APRIL supplementary evaluation commitments
    "interaction_id": ["interaction id", "usage id", "event id", "session id", "query id"],
    "interaction_date": ["interaction date", "usage date", "login date", "query date", "session date"],
    "april_module": ["april module", "module", "feature", "tool used", "usage type"],
    "staff_time_before_minutes": ["staff time before minutes", "time before minutes", "before time minutes", "manual time minutes", "prep time before"],
    "staff_time_after_minutes": ["staff time after minutes", "time after minutes", "after time minutes", "april time minutes", "prep time after"],
    "time_saved_minutes": ["time saved minutes", "minutes saved", "staff minutes saved", "productivity savings minutes"],
    "satisfaction_rating": ["satisfaction rating", "user satisfaction", "rating", "satisfaction score"],
    "rating_scale_max": ["rating scale max", "maximum rating", "max rating", "rating out of"],
    "satisfied": ["satisfied", "satisfaction met", "positive satisfaction", "satisfied user"],
    "respondent_type": ["respondent type", "survey respondent", "feedback group"],
    # Direct L'Harmoni aggregate indicators
    "participating_seniors": ["participating seniors", "seniors participated", "lharmoni participants", "l harmoni participants", "participants enrolled", "unique participants", "total participants"],
    "tracked_seniors_due": ["tracked seniors due", "seniors due for one year follow up", "one year follow up due", "outcome denominator", "tracked seniors one year"],
    "outcome_eligible_seniors": ["outcome eligible seniors", "eligible seniors", "valid paired assessments", "paired assessment seniors", "eligible for outcome"],
    "improved_or_maintained_seniors": ["improved or maintained seniors", "improved maintained seniors", "seniors improved or maintained", "positive outcome seniors", "improved maintained participants"],
    # L'Harmoni raw fields
    "enrolment_date": ["enrolment date", "enrollment date", "joined date", "programme joining date", "program joining date", "lharmoni enrolment date", "l harmoni enrolment date"],
    "participant_status": ["participant status", "enrolment status", "enrollment status", "programme status", "program status", "active status"],
    "baseline_date": ["baseline date", "pre assessment date", "baseline assessment date"],
    "followup_date": ["follow up date", "followup date", "post assessment date", "one year follow up date", "1 year follow up date"],
    "physical_outcome": ["physical outcome", "physical wellbeing outcome", "sppb outcome", "physical change"],
    "cognitive_outcome": ["cognitive outcome", "cognitive wellbeing outcome", "mmse outcome", "cognitive change"],
    "outcome_domain": ["outcome domain", "wellbeing domain", "domain"],
    "outcome_classification": ["outcome classification", "overall outcome", "outcome", "change category", "result classification", "wellbeing outcome"],
    "outcome_approved": ["outcome approved", "approved outcome", "classification approved", "reviewed outcome", "approved"],
    "outcome_rule_version": ["outcome rule version", "rule version", "classification rule", "outcome definition version"],
    "baseline_mmse": ["baseline mmse", "pre mmse", "mmse pre", "pre mmse score"],
    "followup_mmse": ["followup mmse", "post mmse", "mmse post", "post mmse score"],
    "baseline_sppb": ["baseline sppb", "pre sppb", "sppb pre", "pre sppb score"],
    "followup_sppb": ["followup sppb", "post sppb", "sppb post", "post sppb score"],
    "lharmoni_track": ["lharmoni track", "l harmoni track", "programme track", "program track", "track"],
    "sessions_attended": ["sessions attended", "attendance sessions", "number of sessions attended", "sessions completed"],
    "sessions_per_week": ["sessions per week", "weekly sessions", "sessions weekly", "weekly session frequency"],
    "group_size": ["group size", "participants in group", "session group size"],
    "transition_outcome": ["transition outcome", "programme transition", "program transition", "discharge destination"],
    "escalated_to_iccp": ["escalated to iccp", "iccp escalation", "referred to iccp", "escalation status"],
    # Implementation milestones for both projects
    "milestone": ["milestone", "project milestone", "implementation milestone", "deliverable"],
    "milestone_status": ["milestone status", "implementation status", "deliverable status", "status"],
    "milestone_due_date": ["milestone due date", "planned completion date", "target date", "due date"],
    "milestone_completed_date": ["milestone completed date", "actual completion date", "completion date"],
}

ALIAS_KEYS = {canonical: {_compact(x) for x in values + [canonical]} for canonical, values in ALIASES.items()}
ALL_ALIAS_COMPACT = set().union(*ALIAS_KEYS.values())


@dataclass
class SourceTable:
    source_file: str
    source_sheet: str
    frame: pd.DataFrame


@dataclass
class ProjectResult:
    project: str
    reporting_year: int
    project_start_year: int
    centre_summary: pd.DataFrame
    totals: dict[str, float | int | None]
    supplementary: dict[str, float | int | None]
    assessment_summary: pd.DataFrame
    milestone_summary: pd.DataFrame
    source_register: pd.DataFrame
    field_register: pd.DataFrame
    readiness: pd.DataFrame
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)


def _match_column(columns: Iterable[Any], canonical: str) -> str | None:
    expected = ALIAS_KEYS.get(canonical, {_compact(canonical)})
    normalized = {str(col): _compact(col) for col in columns}
    for col, compact in normalized.items():
        if compact in expected:
            return col
    # Conservative partial match: the source header may add a suffix, but a
    # short source header must never match a longer controlled field.
    for col, compact in normalized.items():
        if len(compact) < 6:
            continue
        for alias in expected:
            if len(alias) >= 8 and compact.startswith(alias):
                return col
    return None


def detect_fields(frame: pd.DataFrame) -> dict[str, str]:
    return {name: col for name in ALIASES if (col := _match_column(frame.columns, name)) is not None}


def _header_score(values: Iterable[Any]) -> int:
    score = 0
    for value in values:
        compact = _compact(value)
        if compact in ALL_ALIAS_COMPACT:
            score += 2
        elif any(len(alias) >= 8 and (compact.startswith(alias) or alias.startswith(compact)) for alias in ALL_ALIAS_COMPACT):
            score += 1
    return score


def _table_from_raw(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        return pd.DataFrame()
    best_row, best_score = 0, -1
    for idx in range(min(40, len(raw))):
        score = _header_score(raw.iloc[idx].tolist())
        if score > best_score:
            best_row, best_score = idx, score
    # If nothing resembles the controlled vocabulary, treat first row as header.
    header_row = best_row if best_score > 0 else 0
    headers = []
    seen: dict[str, int] = {}
    for i, value in enumerate(raw.iloc[header_row].tolist()):
        base = str(value).strip() if pd.notna(value) else f"column_{i+1}"
        if not base or base.lower() == "nan":
            base = f"column_{i+1}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        headers.append(base if count == 0 else f"{base}_{count+1}")
    frame = raw.iloc[header_row + 1 :].copy()
    frame.columns = headers
    frame = frame.dropna(how="all").dropna(axis=1, how="all")
    return frame.reset_index(drop=True)


def _read_csv_bytes(data: bytes, sep: str | None = None) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            text = data.decode(encoding)
            return pd.read_csv(StringIO(text), header=None, sep=sep, engine="python", dtype=object)
        except Exception:
            continue
    return pd.DataFrame()


def _read_json_bytes(data: bytes) -> list[tuple[str, pd.DataFrame]]:
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except Exception:
        return []
    out: list[tuple[str, pd.DataFrame]] = []
    if isinstance(obj, list):
        out.append(("JSON", pd.json_normalize(obj)))
    elif isinstance(obj, dict):
        scalar = {k: v for k, v in obj.items() if not isinstance(v, (list, dict))}
        if scalar:
            out.append(("JSON summary", pd.DataFrame([scalar])))
        for key, value in obj.items():
            if isinstance(value, list):
                out.append((str(key), pd.json_normalize(value)))
            elif isinstance(value, dict):
                out.append((str(key), pd.json_normalize(value)))
    return [(name, frame) for name, frame in out if not frame.empty]


def _read_bytes(name: str, data: bytes, parent: str = "") -> list[SourceTable]:
    ext = Path(name).suffix.lower()
    source_name = f"{parent}{name}" if parent else name
    tables: list[SourceTable] = []
    if ext in {".xlsx", ".xls", ".xlsm"}:
        engine = "openpyxl" if ext in {".xlsx", ".xlsm"} else None
        try:
            sheets = pd.read_excel(BytesIO(data), sheet_name=None, header=None, dtype=object, engine=engine)
        except Exception:
            sheets = pd.read_excel(BytesIO(data), sheet_name=None, header=None, dtype=object)
        for sheet, raw in sheets.items():
            sheet_key = _key(sheet)
            if any(term in sheet_key for term in ("instruction", "read me", "expected result", "target reference", "category", "lookup")):
                continue
            frame = _table_from_raw(raw)
            if not frame.empty:
                tables.append(SourceTable(source_name, str(sheet), frame))
    elif ext == ".csv":
        frame = _table_from_raw(_read_csv_bytes(data))
        if not frame.empty:
            tables.append(SourceTable(source_name, "CSV", frame))
    elif ext in {".tsv", ".txt"}:
        frame = _table_from_raw(_read_csv_bytes(data, sep="\t" if ext == ".tsv" else None))
        if not frame.empty:
            tables.append(SourceTable(source_name, ext.lstrip(".").upper(), frame))
    elif ext == ".json":
        for sheet, frame in _read_json_bytes(data):
            tables.append(SourceTable(source_name, sheet, frame))
    elif ext == ".zip":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                for member in archive.infolist():
                    if member.is_dir() or member.file_size > 50_000_000:
                        continue
                    member_ext = Path(member.filename).suffix.lower()
                    if member_ext in SUPPORTED_EXTENSIONS - {".zip"}:
                        tables.extend(_read_bytes(Path(member.filename).name, archive.read(member), parent=f"{source_name}::"))
        except zipfile.BadZipFile:
            return []
    return tables


def read_project_files(uploaded_files: Iterable[Any]) -> tuple[list[SourceTable], list[str]]:
    tables: list[SourceTable] = []
    errors: list[str] = []
    for uploaded in uploaded_files:
        name = getattr(uploaded, "name", "uploaded_file")
        try:
            data = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
            ext = Path(name).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                errors.append(f"{name}: unsupported format. Use XLSX, XLS, XLSM, CSV, TSV, TXT, JSON or ZIP.")
                continue
            found = _read_bytes(name, data)
            if not found:
                errors.append(f"{name}: no readable structured table was found.")
            tables.extend(found)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    return tables, errors


def canonical_centre(value: Any, source_hint: str = "") -> str | None:
    text = _key(value)
    hint = _key(source_hint)
    combined = f"{text} {hint}".strip()
    row_has_service = "glow" in text or "seen" in text
    row_has_location = "bukit batok" in text or "nanyang" in text or re.search(r"\b(?:bb|ny)\b", text) is not None
    if row_has_service and row_has_location:
        combined = text
    is_glow = "glow" in combined and "seen" not in text
    is_seen = "seen" in combined
    is_bb = "bukit batok" in combined or re.search(r"\bbb\b", combined) is not None
    is_ny = "nanyang" in combined or re.search(r"\bny\b", combined) is not None
    if is_bb and is_glow:
        return "GLOW Bukit Batok"
    if is_bb and is_seen:
        return "Tzu Chi SEEN @ Bukit Batok"
    if is_ny and is_glow:
        return "GLOW Nanyang"
    if is_ny and is_seen:
        return "Tzu Chi SEEN @ Nanyang"
    if is_bb:
        return "Bukit Batok (service unspecified)"
    if is_ny:
        return "Nanyang (service unspecified)"
    return None


def _truthy(value: Any) -> bool:
    if pd.isna(value):
        return False
    return _key(value) in {
        "yes", "y", "true", "1", "onboarded", "registered", "active", "completed",
        "reviewed", "validated", "approved", "at risk", "risk", "satisfied", "positive",
    }


def _falsey(value: Any) -> bool:
    if pd.isna(value):
        return False
    return _key(value) in {"no", "n", "false", "0", "not validated", "not approved", "not reviewed", "inactive", "cancelled", "negative"}


def _entity_series(frame: pd.DataFrame, fields: dict[str, str], warnings: list[str], source_label: str) -> pd.Series:
    if "person_id" in fields:
        values = frame[fields["person_id"]].fillna("").astype(str).str.strip()
        values = values.where(~values.str.lower().isin({"", "nan", "none"}))
        return values
    if "person_name" in fields:
        warnings.append(f"{source_label}: stable person ID was not found; normalized names were used for de-duplication. Review before submission.")
        values = frame[fields["person_name"]].fillna("").astype(str).str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
        return values.where(~values.isin({"", "nan", "none"}))
    return pd.Series(pd.NA, index=frame.index, dtype="object")


def _parse_date_values(values: pd.Series) -> pd.Series:
    """Parse normal dates and Excel serial date values safely."""
    source = values.copy()
    numeric = pd.to_numeric(source, errors="coerce")
    parsed = pd.to_datetime(source.where(numeric.isna()), errors="coerce")
    serial_mask = numeric.between(20000, 80000, inclusive="both")
    if serial_mask.any():
        parsed.loc[serial_mask] = pd.to_datetime(numeric.loc[serial_mask], unit="D", origin="1899-12-30", errors="coerce")
    return parsed


def _date_series(frame: pd.DataFrame, fields: dict[str, str], preferred: list[str]) -> pd.Series:
    for canonical in preferred:
        col = fields.get(canonical)
        if col:
            parsed = _parse_date_values(frame[col])
            if parsed.notna().any():
                return parsed
    return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")


def _centre_series(table: SourceTable, fields: dict[str, str]) -> pd.Series:
    hint = f"{table.source_file} {table.source_sheet}"
    if "centre" in fields:
        return table.frame[fields["centre"]].apply(lambda v: canonical_centre(v, hint))
    inferred = canonical_centre("", hint)
    return pd.Series(inferred, index=table.frame.index, dtype="object")


def _project_mask(table: SourceTable, fields: dict[str, str], project: str) -> pd.Series:
    token = "april" if project == "APRIL" else "lharmoni"
    source_has = token in _compact(f"{table.source_file} {table.source_sheet}")
    if "project" in fields:
        values = table.frame[fields["project"]].apply(_compact)
        return values.str.contains(token, na=False)
    return pd.Series(source_has, index=table.frame.index)


def _numeric(frame: pd.DataFrame, col: str | None) -> pd.Series:
    if not col:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[col], errors="coerce")


def _project_window(project_start_year: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    return pd.Timestamp(project_start_year, 1, 1), pd.Timestamp(project_start_year + 2, 12, 31, 23, 59, 59)


def discover_years(tables: list[SourceTable]) -> list[int]:
    years: set[int] = set()
    for table in tables:
        fields = detect_fields(table.frame)
        dates = _date_series(table.frame, fields, ["reporting_date", "record_date", "onboarding_date", "review_date", "assessment_date", "interaction_date", "enrolment_date", "followup_date", "baseline_date"])
        years.update(int(y) for y in dates.dropna().dt.year.unique())
    return sorted(years)


def _source_register(tables: list[SourceTable]) -> pd.DataFrame:
    rows = []
    for table in tables:
        fields = detect_fields(table.frame)
        rows.append({
            "Source File": table.source_file,
            "Sheet / Table": table.source_sheet,
            "Rows Scanned": len(table.frame),
            "Columns Scanned": len(table.frame.columns),
            "Recognised Fields": ", ".join(sorted(fields)) if fields else "None",
        })
    return pd.DataFrame(rows)


def _field_register(tables: list[SourceTable]) -> pd.DataFrame:
    rows = []
    for table in tables:
        fields = detect_fields(table.frame)
        for canonical, source_col in fields.items():
            rows.append({
                "Source File": table.source_file,
                "Sheet / Table": table.source_sheet,
                "Controlled Field": canonical,
                "Matched Source Column": source_col,
            })
    return pd.DataFrame(rows)


def _latest_aggregate_values(
    tables: list[SourceTable],
    project: str,
    metric_names: list[str],
    reporting_year: int,
    annual_metrics: set[str],
    allowed_centres: set[str],
    warnings: list[str],
) -> pd.DataFrame:
    """Read direct aggregate fields conservatively.

    For repeated reports for the same centre and metric, the row with the latest
    reporting date is used. If dates are unavailable and values conflict, the
    metric is left unavailable and a warning is emitted.
    """
    records: list[dict[str, Any]] = []
    for table in tables:
        fields = detect_fields(table.frame)
        metric_cols = {metric: fields.get(metric) for metric in metric_names if fields.get(metric)}
        if not metric_cols:
            continue
        mask = _project_mask(table, fields, project)
        centres = _centre_series(table, fields)
        dates = _date_series(table.frame, fields, ["reporting_date", "record_date", "assessment_date", "onboarding_date", "enrolment_date"])
        for idx in table.frame.index[mask]:
            centre = centres.loc[idx]
            if centre not in allowed_centres and centre is not None:
                continue
            for metric, col in metric_cols.items():
                value = pd.to_numeric(pd.Series([table.frame.at[idx, col]]), errors="coerce").iloc[0]
                if pd.isna(value):
                    continue
                record_date = dates.loc[idx]
                if metric in annual_metrics and pd.notna(record_date) and int(record_date.year) != reporting_year:
                    continue
                records.append({
                    "centre": centre or "Project total (centre not stated)",
                    "metric": metric,
                    "value": float(value),
                    "date": record_date,
                    "source": f"{table.source_file} / {table.source_sheet}",
                })
    if not records:
        return pd.DataFrame(columns=["centre"] + metric_names)
    rec = pd.DataFrame(records)
    chosen: list[dict[str, Any]] = []
    for (centre, metric), group in rec.groupby(["centre", "metric"], dropna=False):
        with_dates = group[group["date"].notna()].sort_values("date")
        if not with_dates.empty:
            row = with_dates.iloc[-1]
            if group["value"].nunique() > 1:
                warnings.append(f"{metric.replace('_', ' ').title()} had multiple snapshots for {centre}; the latest dated value was used.")
            chosen.append({"centre": centre, "metric": metric, "value": row["value"]})
        else:
            distinct = group["value"].dropna().unique()
            if len(distinct) == 1:
                chosen.append({"centre": centre, "metric": metric, "value": float(distinct[0])})
            else:
                warnings.append(f"Conflicting undated aggregate values were found for {metric.replace('_', ' ')} at {centre}; the metric was not used.")
    if not chosen:
        return pd.DataFrame(columns=["centre"] + metric_names)
    return pd.DataFrame(chosen).pivot(index="centre", columns="metric", values="value").reset_index()


def _assessment_records(
    tables: list[SourceTable],
    project: str,
    reporting_year: int,
    project_start_year: int,
    allowed_centres: set[str],
    warnings: list[str],
) -> tuple[pd.DataFrame, dict[str, set[str]], dict[str, set[str]]]:
    """Return annual complete-set summary and person sets.

    A complete set must belong to one assessment episode. The episode key is:
    explicit episode ID when supplied, otherwise the exact assessment date.
    Records without either are not combined across a reporting year.
    """
    annual_complete_by_centre: dict[str, set[str]] = {}
    annual_instrument_by_centre: dict[str, dict[str, set[str]]] = {}
    tracked_by_centre: dict[str, set[str]] = {}
    long_rows: list[dict[str, Any]] = []
    wide_rows: list[dict[str, Any]] = []
    instrument_evidence = {"mmse": False, "gds": False, "sppb": False}
    any_assessment_evidence = False
    start, end = _project_window(project_start_year)

    for table in tables:
        fields = detect_fields(table.frame)
        if not any(name in fields for name in ("assessment_type", "mmse", "gds", "sppb", "baseline_mmse", "followup_mmse", "baseline_sppb", "followup_sppb")):
            continue
        mask = _project_mask(table, fields, project)
        if mask.any():
            any_assessment_evidence = True
            for instrument in ("mmse", "gds", "sppb"):
                instrument_evidence[instrument] = instrument_evidence[instrument] or instrument in fields
            if "assessment_type" in fields:
                values = table.frame.loc[mask, fields["assessment_type"]].astype(str).map(_key)
                instrument_evidence["mmse"] = instrument_evidence["mmse"] or values.str.contains("mmse|mental state", regex=True).any()
                instrument_evidence["gds"] = instrument_evidence["gds"] or values.str.contains("gds|depression", regex=True).any()
                instrument_evidence["sppb"] = instrument_evidence["sppb"] or values.str.contains("sppb|physical performance", regex=True).any()
        centres = _centre_series(table, fields)
        entities = _entity_series(table.frame, fields, warnings, f"{table.source_file} / {table.source_sheet}")
        dates = _date_series(table.frame, fields, ["assessment_date", "record_date", "followup_date", "baseline_date"])
        episodes = table.frame[fields["assessment_episode_id"]].astype(str).str.strip() if "assessment_episode_id" in fields else pd.Series("", index=table.frame.index)
        for idx in table.frame.index[mask]:
            centre = centres.loc[idx]
            entity = entities.loc[idx]
            when = dates.loc[idx]
            if centre not in allowed_centres or pd.isna(entity):
                continue
            if pd.notna(when) and start <= when <= end:
                tracked_by_centre.setdefault(centre, set()).add(str(entity))
            # Wide-format scores.
            present = {
                instrument: fields.get(instrument) and pd.notna(pd.to_numeric(pd.Series([table.frame.at[idx, fields[instrument]]]), errors="coerce").iloc[0])
                for instrument in ("mmse", "gds", "sppb")
            }
            if any(present.values()):
                if pd.isna(when):
                    warnings.append(f"{table.source_file} / {table.source_sheet}: an assessment row for {entity} had scores but no assessment date; it was not counted as an annual set.")
                else:
                    episode = episodes.loc[idx] if episodes.loc[idx] and episodes.loc[idx].lower() not in {"nan", "none"} else when.date().isoformat()
                    wide_rows.append({"centre": centre, "entity": str(entity), "date": when, "episode": episode, **present})
            # Long-format assessment rows.
            if "assessment_type" in fields:
                instrument = _key(table.frame.at[idx, fields["assessment_type"]])
                canonical = None
                if "mmse" in instrument or "mental state" in instrument:
                    canonical = "mmse"
                elif "gds" in instrument or "depression" in instrument:
                    canonical = "gds"
                elif "sppb" in instrument or "physical performance" in instrument:
                    canonical = "sppb"
                if canonical:
                    if pd.isna(when):
                        warnings.append(f"{table.source_file} / {table.source_sheet}: a {canonical.upper()} record for {entity} had no assessment date and was excluded from the annual set count.")
                    else:
                        episode = episodes.loc[idx] if episodes.loc[idx] and episodes.loc[idx].lower() not in {"nan", "none"} else when.date().isoformat()
                        long_rows.append({"centre": centre, "entity": str(entity), "date": when, "episode": episode, "instrument": canonical})

    # Build instrument sets by exact episode.
    episode_map: dict[tuple[str, str, str], set[str]] = {}
    for row in wide_rows:
        key = (row["centre"], row["entity"], str(row["episode"]))
        episode_map.setdefault(key, set()).update({i for i in ("mmse", "gds", "sppb") if row[i]})
        if int(row["date"].year) == reporting_year:
            for instrument in ("mmse", "gds", "sppb"):
                if row[instrument]:
                    annual_instrument_by_centre.setdefault(row["centre"], {}).setdefault(instrument, set()).add(row["entity"])
    for row in long_rows:
        key = (row["centre"], row["entity"], str(row["episode"]))
        episode_map.setdefault(key, set()).add(row["instrument"])
        if int(row["date"].year) == reporting_year:
            annual_instrument_by_centre.setdefault(row["centre"], {}).setdefault(row["instrument"], set()).add(row["entity"])

    for (centre, entity, episode), instruments in episode_map.items():
        # Episode strings derived from dates are guaranteed annual; explicit IDs need
        # a matching annual row. Check source rows to avoid cross-year reuse.
        episode_dates = [r["date"] for r in wide_rows if r["centre"] == centre and r["entity"] == entity and str(r["episode"]) == episode]
        episode_dates += [r["date"] for r in long_rows if r["centre"] == centre and r["entity"] == entity and str(r["episode"]) == episode]
        if episode_dates and any(int(d.year) == reporting_year for d in episode_dates) and {"mmse", "gds", "sppb"}.issubset(instruments):
            annual_complete_by_centre.setdefault(centre, set()).add(entity)

    rows = []
    for centre in sorted(allowed_centres):
        instruments = annual_instrument_by_centre.get(centre, {})
        rows.append({
            "centre": centre,
            "mmse_completed_annual": len(instruments.get("mmse", set())) if instrument_evidence["mmse"] else np.nan,
            "gds_completed_annual": len(instruments.get("gds", set())) if instrument_evidence["gds"] else np.nan,
            "sppb_completed_annual": len(instruments.get("sppb", set())) if instrument_evidence["sppb"] else np.nan,
            "complete_assessment_sets_annual": len(annual_complete_by_centre.get(centre, set())) if all(instrument_evidence.values()) else np.nan,
            "unique_tracked_seniors_3_year": len(tracked_by_centre.get(centre, set())) if any_assessment_evidence else np.nan,
        })
    total_sets = {
        "annual_complete": set().union(*annual_complete_by_centre.values()) if annual_complete_by_centre else set(),
        "three_year_tracked": set().union(*tracked_by_centre.values()) if tracked_by_centre else set(),
        "tracked_by_centre": tracked_by_centre,
    }
    instrument_totals = {
        instrument: set().union(*[m.get(instrument, set()) for m in annual_instrument_by_centre.values()]) if annual_instrument_by_centre else set()
        for instrument in ("mmse", "gds", "sppb")
    }
    return pd.DataFrame(rows), total_sets, instrument_totals


def _beneficiary_type(value: Any) -> str | None:
    text = _key(value)
    if "volunteer" in text:
        return "volunteer"
    if "caregiver" in text or "carer" in text:
        return "caregiver"
    if "aac" in text and ("client" in text or "senior" in text):
        return "aac_client"
    if text in {"client", "senior", "participant", "beneficiary"}:
        return "aac_client"
    return None


def _april_record_level(
    tables: list[SourceTable], reporting_year: int, project_start_year: int, warnings: list[str]
) -> tuple[pd.DataFrame, dict[str, set[str]], dict[str, Any]]:
    onboarded: dict[str, set[str]] = {}
    flagged: dict[str, set[str]] = {}
    reviewed: dict[str, set[str]] = {}
    validated: dict[str, set[str]] = {}
    validated_explicit_assessment: dict[str, set[str]] = {}
    clients: dict[str, set[str]] = {}
    volunteers: dict[str, set[str]] = {}
    caregivers: dict[str, set[str]] = {}
    clients_3yr: dict[str, set[tuple[int, str]]] = {}
    volunteers_3yr: dict[str, set[tuple[int, str]]] = {}
    caregivers_3yr: dict[str, set[tuple[int, str]]] = {}
    interactions: set[str] = set()
    active_users: set[str] = set()
    time_saved: list[float] = []
    satisfaction_ratings: list[float] = []
    satisfaction_positive: set[str] = set()
    satisfaction_respondents: set[str] = set()
    evidence = {"onboarded": False, "risk": False, "beneficiaries": False}
    start, end = _project_window(project_start_year)

    for table in tables:
        fields = detect_fields(table.frame)
        mask = _project_mask(table, fields, "APRIL")
        if not mask.any():
            continue
        evidence["onboarded"] = evidence["onboarded"] or any(name in fields for name in ("onboarded", "onboarding_date"))
        evidence["risk"] = evidence["risk"] or any(name in fields for name in ("risk_flag_id", "risk_flagged", "risk_reviewed", "risk_validated", "validation_outcome", "validation_assessment_type"))
        evidence["beneficiaries"] = evidence["beneficiaries"] or "beneficiary_type" in fields
        centres = _centre_series(table, fields)
        entities = _entity_series(table.frame, fields, warnings, f"{table.source_file} / {table.source_sheet}")
        record_dates = _date_series(table.frame, fields, ["record_date", "onboarding_date", "review_date", "interaction_date", "assessment_date", "reporting_date"])
        for idx in table.frame.index[mask]:
            centre = centres.loc[idx]
            entity = entities.loc[idx]
            when = record_dates.loc[idx]
            if centre not in APRIL_CENTRES:
                if pd.notna(centre):
                    warnings.append(f"{table.source_file} / {table.source_sheet}: APRIL row excluded because centre '{centre}' was not one of the four approved centres.")
                continue
            if pd.isna(entity):
                continue
            ent = str(entity)
            in_project_window = pd.isna(when) or (start <= when <= end)
            # Onboarding is cumulative across the project period.
            onboarding_evidence = False
            if "onboarded" in fields:
                onboarding_evidence = _truthy(table.frame.at[idx, fields["onboarded"]])
            elif "onboarding_date" in fields:
                onboarding_evidence = pd.notna(_parse_date_values(pd.Series([table.frame.at[idx, fields["onboarding_date"]]])).iloc[0])
            if onboarding_evidence and in_project_window:
                onboarded.setdefault(centre, set()).add(ent)

            # All flagged seniors/flags are the official denominator basis.
            is_flagged = False
            if "risk_flag_id" in fields:
                value = table.frame.at[idx, fields["risk_flag_id"]]
                is_flagged = pd.notna(value) and str(value).strip().lower() not in {"", "nan", "none"}
            if "risk_flagged" in fields:
                is_flagged = is_flagged or _truthy(table.frame.at[idx, fields["risk_flagged"]])
            if is_flagged:
                flagged.setdefault(centre, set()).add(ent)
            is_reviewed = "risk_reviewed" in fields and _truthy(table.frame.at[idx, fields["risk_reviewed"]])
            if "validation_outcome" in fields:
                outcome = _key(table.frame.at[idx, fields["validation_outcome"]])
                is_reviewed = is_reviewed or outcome in {"validated", "not validated", "confirmed", "not confirmed"}
            if is_reviewed:
                reviewed.setdefault(centre, set()).add(ent)
                # A reviewed record is also evidence that it was flagged, if no separate field exists.
                if not is_flagged:
                    flagged.setdefault(centre, set()).add(ent)
            is_validated = False
            if "risk_validated" in fields:
                is_validated = _truthy(table.frame.at[idx, fields["risk_validated"]])
            if "validation_outcome" in fields:
                outcome = _key(table.frame.at[idx, fields["validation_outcome"]])
                is_validated = is_validated or outcome in {"validated", "confirmed", "true risk", "at risk confirmed"}
            if is_validated:
                validated.setdefault(centre, set()).add(ent)
                reviewed.setdefault(centre, set()).add(ent)
                flagged.setdefault(centre, set()).add(ent)
                if "validation_assessment_type" in fields:
                    assessment_used = _key(table.frame.at[idx, fields["validation_assessment_type"]])
                    if any(token in assessment_used for token in ("mmse", "gds", "sppb", "mental state", "depression scale", "physical performance")):
                        validated_explicit_assessment.setdefault(centre, set()).add(ent)

            # Annual and three-year beneficiary commitments.
            if pd.notna(when) and "beneficiary_type" in fields:
                role = _beneficiary_type(table.frame.at[idx, fields["beneficiary_type"]])
                year_value = int(when.year)
                if start <= when <= end:
                    if role == "aac_client": clients_3yr.setdefault(centre, set()).add((year_value, ent))
                    elif role == "volunteer": volunteers_3yr.setdefault(centre, set()).add((year_value, ent))
                    elif role == "caregiver": caregivers_3yr.setdefault(centre, set()).add((year_value, ent))
                if year_value == reporting_year:
                    if role == "aac_client": clients.setdefault(centre, set()).add(ent)
                    elif role == "volunteer": volunteers.setdefault(centre, set()).add(ent)
                    elif role == "caregiver": caregivers.setdefault(centre, set()).add(ent)

            # Usage monitoring.
            if "interaction_id" in fields or "interaction_date" in fields or "april_module" in fields:
                interaction_value = table.frame.at[idx, fields["interaction_id"]] if "interaction_id" in fields else f"{table.source_file}|{table.source_sheet}|{idx}"
                interaction_date = _parse_date_values(pd.Series([table.frame.at[idx, fields["interaction_date"]]])).iloc[0] if "interaction_date" in fields else when
                if pd.isna(interaction_date) or int(interaction_date.year) == reporting_year:
                    interactions.add(str(interaction_value))
                    active_users.add(ent)

            # Productivity savings.
            saved = np.nan
            if "time_saved_minutes" in fields:
                saved = pd.to_numeric(pd.Series([table.frame.at[idx, fields["time_saved_minutes"]]]), errors="coerce").iloc[0]
            elif "staff_time_before_minutes" in fields and "staff_time_after_minutes" in fields:
                before = pd.to_numeric(pd.Series([table.frame.at[idx, fields["staff_time_before_minutes"]]]), errors="coerce").iloc[0]
                after = pd.to_numeric(pd.Series([table.frame.at[idx, fields["staff_time_after_minutes"]]]), errors="coerce").iloc[0]
                if pd.notna(before) and pd.notna(after):
                    saved = before - after
            if pd.notna(saved):
                time_saved.append(float(saved))

            # Satisfaction monitoring.
            respondent = ent
            if "satisfaction_rating" in fields:
                rating = pd.to_numeric(pd.Series([table.frame.at[idx, fields["satisfaction_rating"]]]), errors="coerce").iloc[0]
                if pd.notna(rating):
                    satisfaction_ratings.append(float(rating))
                    satisfaction_respondents.add(respondent)
            if "satisfied" in fields:
                satisfaction_respondents.add(respondent)
                if _truthy(table.frame.at[idx, fields["satisfied"]]):
                    satisfaction_positive.add(respondent)

    rows = []
    for centre in APRIL_CENTRES:
        rows.append({
            "centre": centre,
            "seniors_onboarded": len(onboarded.get(centre, set())) if evidence["onboarded"] else np.nan,
            "risk_flags_total": len(flagged.get(centre, set())) if evidence["risk"] else np.nan,
            "risk_flags_reviewed": len(reviewed.get(centre, set())) if evidence["risk"] else np.nan,
            "risk_flags_validated_recorded": len(validated.get(centre, set())) if evidence["risk"] else np.nan,
            "risk_flags_validated": len(validated.get(centre, set())) if evidence["risk"] else np.nan,
            "aac_clients_reached_annual": len(clients.get(centre, set())) if evidence["beneficiaries"] else np.nan,
            "volunteers_reached_annual": len(volunteers.get(centre, set())) if evidence["beneficiaries"] else np.nan,
            "caregivers_reached_annual": len(caregivers.get(centre, set())) if evidence["beneficiaries"] else np.nan,
            "aac_client_instances_3_year": len(clients_3yr.get(centre, set())) if evidence["beneficiaries"] else np.nan,
            "volunteer_instances_3_year": len(volunteers_3yr.get(centre, set())) if evidence["beneficiaries"] else np.nan,
            "caregiver_instances_3_year": len(caregivers_3yr.get(centre, set())) if evidence["beneficiaries"] else np.nan,
        })
    sets = {
        "onboarded": set().union(*onboarded.values()) if onboarded else set(),
        "flagged": set().union(*flagged.values()) if flagged else set(),
        "reviewed": set().union(*reviewed.values()) if reviewed else set(),
        "validated": set().union(*validated.values()) if validated else set(),
        "validated_by_centre": validated,
        "validated_explicit_assessment_by_centre": validated_explicit_assessment,
        "clients": set().union(*clients.values()) if clients else set(),
        "volunteers": set().union(*volunteers.values()) if volunteers else set(),
        "caregivers": set().union(*caregivers.values()) if caregivers else set(),
        "client_instances_3_year": set().union(*clients_3yr.values()) if clients_3yr else set(),
        "volunteer_instances_3_year": set().union(*volunteers_3yr.values()) if volunteers_3yr else set(),
        "caregiver_instances_3_year": set().union(*caregivers_3yr.values()) if caregivers_3yr else set(),
    }
    supplementary = {
        "unique_active_april_users_annual": len(active_users) if interactions or active_users else None,
        "april_interactions_annual": len(interactions) if interactions else None,
        "total_staff_hours_saved": sum(time_saved) / 60 if time_saved else None,
        "average_minutes_saved_per_record": float(np.mean(time_saved)) if time_saved else None,
        "satisfaction_respondents": len(satisfaction_respondents) if satisfaction_respondents else None,
        "average_satisfaction_rating": float(np.mean(satisfaction_ratings)) if satisfaction_ratings else None,
        "explicit_satisfaction_rate": len(satisfaction_positive) / len(satisfaction_respondents) if satisfaction_respondents and satisfaction_positive else None,
    }
    return pd.DataFrame(rows), sets, supplementary


def _normalise_outcome(value: Any) -> str | None:
    text = _key(value)
    if not text or text in {"nan", "none"}:
        return None
    if "improved" in text or "improvement" in text:
        return "Improved"
    if "maintained" in text or "stable" in text:
        return "Maintained"
    if "declined" in text or "deteriorated" in text or "worsened" in text:
        return "Declined"
    # Deliberately do not map generic 'no change' to Maintained without an approved rule.
    if "no change" in text:
        return "No Change (unapproved)"
    return None


def _lharmoni_record_level(
    tables: list[SourceTable],
    reporting_year: int,
    project_start_year: int,
    followup_min_days: int,
    followup_max_days: int,
    timing_rule_approved: bool,
    raw_score_rule_approved: bool,
    data_cutoff: pd.Timestamp,
    warnings: list[str],
) -> tuple[pd.DataFrame, dict[str, set[str]], dict[str, Any], pd.DataFrame]:
    participants: dict[str, set[str]] = {}
    due: dict[str, set[str]] = {}
    eligible: dict[str, set[str]] = {}
    success: dict[str, set[str]] = {}
    physical_outcomes: list[dict[str, Any]] = []
    cognitive_outcomes: list[dict[str, Any]] = []
    track_counts: dict[str, set[str]] = {}
    transitions: dict[str, set[str]] = {}
    escalated: set[str] = set()
    sessions: list[float] = []
    sessions_weekly: list[float] = []
    group_sizes: list[float] = []
    excluded_non_glow = 0
    evidence = {"participants": False, "due": False, "outcomes": False}
    start, end = _project_window(project_start_year)

    for table in tables:
        fields = detect_fields(table.frame)
        mask = _project_mask(table, fields, "LHARMONI")
        if not mask.any():
            continue
        evidence["participants"] = evidence["participants"] or any(name in fields for name in ("enrolment_date", "participant_status"))
        evidence["due"] = evidence["due"] or "enrolment_date" in fields
        evidence["outcomes"] = evidence["outcomes"] or any(name in fields for name in ("physical_outcome", "cognitive_outcome", "baseline_mmse", "followup_mmse", "baseline_sppb", "followup_sppb"))
        centres = _centre_series(table, fields)
        entities = _entity_series(table.frame, fields, warnings, f"{table.source_file} / {table.source_sheet}")
        enrolments = _date_series(table.frame, fields, ["enrolment_date"])
        followups = _date_series(table.frame, fields, ["followup_date"])
        for idx in table.frame.index[mask]:
            centre = centres.loc[idx]
            entity = entities.loc[idx]
            if centre not in LHARMONI_CENTRES:
                if pd.notna(centre):
                    excluded_non_glow += 1
                continue
            if pd.isna(entity):
                continue
            ent = str(entity)
            enrolment = enrolments.loc[idx]
            followup = followups.loc[idx]
            status_ok = True
            if "participant_status" in fields:
                status = _key(table.frame.at[idx, fields["participant_status"]])
                status_ok = status not in {"cancelled", "duplicate", "error", "not enrolled"}
            if status_ok and pd.notna(enrolment) and start <= enrolment <= end:
                participants.setdefault(centre, set()).add(ent)
            elif status_ok and "enrolment_date" not in fields and "participant_status" in fields:
                # A project-specific participant register may omit dates, but an
                # assessment/operations table must never create extra participants.
                participants.setdefault(centre, set()).add(ent)

            # One-year denominator: seniors whose one-year point is due by cutoff.
            if pd.notna(enrolment) and enrolment + pd.Timedelta(days=365) <= data_cutoff:
                due.setdefault(centre, set()).add(ent)

            physical = _normalise_outcome(table.frame.at[idx, fields["physical_outcome"]]) if "physical_outcome" in fields else None
            cognitive = _normalise_outcome(table.frame.at[idx, fields["cognitive_outcome"]]) if "cognitive_outcome" in fields else None
            # Generic outcomes are accepted only when the source explicitly says the domain is physical/cognitive.
            if physical is None and cognitive is None and "outcome_classification" in fields and "outcome_domain" in fields:
                domain = _key(table.frame.at[idx, fields["outcome_domain"]])
                outcome = _normalise_outcome(table.frame.at[idx, fields["outcome_classification"]])
                if "physical" in domain or "sppb" in domain:
                    physical = outcome
                if "cognitive" in domain or "mmse" in domain:
                    cognitive = outcome
            elif physical is None and cognitive is None and "outcome_classification" in fields and "outcome_domain" not in fields:
                warnings.append(f"{table.source_file} / {table.source_sheet}: generic outcome for {ent} was excluded because no Physical/Cognitive outcome domain was identified.")
            # Optional raw score direction rule, only after explicit approval in the UI.
            if raw_score_rule_approved:
                if physical is None and "baseline_sppb" in fields and "followup_sppb" in fields:
                    pre = pd.to_numeric(pd.Series([table.frame.at[idx, fields["baseline_sppb"]]]), errors="coerce").iloc[0]
                    post = pd.to_numeric(pd.Series([table.frame.at[idx, fields["followup_sppb"]]]), errors="coerce").iloc[0]
                    if pd.notna(pre) and pd.notna(post):
                        physical = "Improved" if post > pre else "Maintained" if post == pre else "Declined"
                if cognitive is None and "baseline_mmse" in fields and "followup_mmse" in fields:
                    pre = pd.to_numeric(pd.Series([table.frame.at[idx, fields["baseline_mmse"]]]), errors="coerce").iloc[0]
                    post = pd.to_numeric(pd.Series([table.frame.at[idx, fields["followup_mmse"]]]), errors="coerce").iloc[0]
                    if pd.notna(pre) and pd.notna(post):
                        cognitive = "Improved" if post > pre else "Maintained" if post == pre else "Declined"

            approved = "outcome_approved" in fields and _truthy(table.frame.at[idx, fields["outcome_approved"]])
            rule_present = "outcome_rule_version" in fields and bool(str(table.frame.at[idx, fields["outcome_rule_version"]]).strip()) and str(table.frame.at[idx, fields["outcome_rule_version"]]).strip().lower() not in {"nan", "none"}
            timing_valid = False
            days_after = None
            if pd.notna(enrolment) and pd.notna(followup):
                days_after = int((followup - enrolment).days)
                timing_valid = followup_min_days <= days_after <= followup_max_days
            if timing_rule_approved and approved and rule_present and timing_valid and (physical in {"Improved", "Maintained", "Declined"} or cognitive in {"Improved", "Maintained", "Declined"}):
                eligible.setdefault(centre, set()).add(ent)
                if physical in {"Improved", "Maintained"} or cognitive in {"Improved", "Maintained"}:
                    success.setdefault(centre, set()).add(ent)
                if physical:
                    physical_outcomes.append({"centre": centre, "entity": ent, "outcome": physical})
                if cognitive:
                    cognitive_outcomes.append({"centre": centre, "entity": ent, "outcome": cognitive})
            elif any(x is not None for x in (physical, cognitive)) and not timing_rule_approved:
                # Records are visible in the audit but not in the official result.
                pass

            if "lharmoni_track" in fields:
                track = str(table.frame.at[idx, fields["lharmoni_track"]]).strip()
                if track and track.lower() not in {"nan", "none"}:
                    track_counts.setdefault(track, set()).add(ent)
            if "transition_outcome" in fields:
                transition = str(table.frame.at[idx, fields["transition_outcome"]]).strip()
                if transition and transition.lower() not in {"nan", "none"}:
                    transitions.setdefault(transition, set()).add(ent)
            if "escalated_to_iccp" in fields and _truthy(table.frame.at[idx, fields["escalated_to_iccp"]]):
                escalated.add(ent)
            if "sessions_attended" in fields:
                value = pd.to_numeric(pd.Series([table.frame.at[idx, fields["sessions_attended"]]]), errors="coerce").iloc[0]
                if pd.notna(value):
                    sessions.append(float(value))
            if "sessions_per_week" in fields:
                value = pd.to_numeric(pd.Series([table.frame.at[idx, fields["sessions_per_week"]]]), errors="coerce").iloc[0]
                if pd.notna(value): sessions_weekly.append(float(value))
            if "group_size" in fields:
                value = pd.to_numeric(pd.Series([table.frame.at[idx, fields["group_size"]]]), errors="coerce").iloc[0]
                if pd.notna(value):
                    group_sizes.append(float(value))

    if excluded_non_glow:
        warnings.append(f"{excluded_non_glow} L’Harmoni row(s) were excluded because the centre was not explicitly GLOW Bukit Batok or GLOW Nanyang.")
    rows = []
    for centre in LHARMONI_CENTRES:
        rows.append({
            "centre": centre,
            "participating_seniors": len(participants.get(centre, set())) if evidence["participants"] else np.nan,
            "tracked_seniors_due": len(due.get(centre, set())) if evidence["due"] else np.nan,
            "outcome_eligible_seniors": len(eligible.get(centre, set())) if evidence["outcomes"] else np.nan,
            "improved_or_maintained_seniors": len(success.get(centre, set())) if evidence["outcomes"] else np.nan,
        })
    sets = {
        "participants": set().union(*participants.values()) if participants else set(),
        "due": set().union(*due.values()) if due else set(),
        "eligible": set().union(*eligible.values()) if eligible else set(),
        "success": set().union(*success.values()) if success else set(),
    }
    supplementary = {
        "average_sessions_attended": float(np.mean(sessions)) if sessions else None,
        "average_sessions_per_week": float(np.mean(sessions_weekly)) if sessions_weekly else None,
        "weekly_session_compliance_rate_2_to_3": sum(2 <= x <= 3 for x in sessions_weekly) / len(sessions_weekly) if sessions_weekly else None,
        "average_group_size": float(np.mean(group_sizes)) if group_sizes else None,
        "group_size_compliance_rate_6_to_10": sum(6 <= x <= 10 for x in group_sizes) / len(group_sizes) if group_sizes else None,
        "escalated_to_iccp": len(escalated) if escalated else None,
    }
    # Add dynamic track and transition counts with stable keys.
    for label, people in sorted(track_counts.items()):
        supplementary[f"track: {label}"] = len(people)
    for label, people in sorted(transitions.items()):
        supplementary[f"transition: {label}"] = len(people)

    outcome_rows = []
    for domain, records in (("Physical", physical_outcomes), ("Cognitive", cognitive_outcomes)):
        if records:
            frame = pd.DataFrame(records).drop_duplicates(["centre", "entity", "outcome"])
            for (centre, outcome), group in frame.groupby(["centre", "outcome"]):
                outcome_rows.append({"Domain": domain, "Centre": centre, "Outcome": outcome, "Seniors": group["entity"].nunique()})
    return pd.DataFrame(rows), sets, supplementary, pd.DataFrame(outcome_rows)


def _milestone_summary(tables: list[SourceTable], project: str, expected: list[str]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for table in tables:
        fields = detect_fields(table.frame)
        if "milestone" not in fields:
            continue
        mask = _project_mask(table, fields, project)
        for idx in table.frame.index[mask]:
            name = str(table.frame.at[idx, fields["milestone"]]).strip()
            if not name or name.lower() in {"nan", "none"}:
                continue
            status = str(table.frame.at[idx, fields["milestone_status"]]).strip() if "milestone_status" in fields else "Data unavailable"
            due = _parse_date_values(pd.Series([table.frame.at[idx, fields["milestone_due_date"]]])).iloc[0] if "milestone_due_date" in fields else pd.NaT
            completed = _parse_date_values(pd.Series([table.frame.at[idx, fields["milestone_completed_date"]]])).iloc[0] if "milestone_completed_date" in fields else pd.NaT
            records.append({"Milestone": name, "Status": status or "Data unavailable", "Due Date": due, "Completed Date": completed, "Source": f"{table.source_file} / {table.source_sheet}"})
    result_rows = []
    used: set[int] = set()
    for expected_name in expected:
        match_idx = None
        expected_key = _key(expected_name)
        for idx, record in enumerate(records):
            if idx in used:
                continue
            record_key = _key(record["Milestone"])
            tokens = [t for t in expected_key.split() if len(t) > 3]
            if record_key == expected_key or (tokens and sum(t in record_key for t in tokens) >= max(1, len(tokens) // 2)):
                match_idx = idx
                break
        if match_idx is None:
            result_rows.append({"Milestone": expected_name, "Status": "Data unavailable", "Due Date": pd.NaT, "Completed Date": pd.NaT, "Source": "Not found"})
        else:
            used.add(match_idx)
            record = records[match_idx].copy()
            record["Milestone"] = expected_name
            result_rows.append(record)
    return pd.DataFrame(result_rows)


def _combine_sources(
    record: pd.DataFrame,
    assessment: pd.DataFrame,
    aggregate: pd.DataFrame,
    metrics: list[str],
    warnings: list[str],
) -> pd.DataFrame:
    rows = []
    centres = set()
    for frame in (record, assessment, aggregate):
        if frame is not None and not frame.empty and "centre" in frame.columns:
            centres.update(frame["centre"].dropna().astype(str).tolist())
    for centre in sorted(centres):
        row: dict[str, Any] = {"centre": centre}
        for metric in metrics:
            values = []
            sources = []
            for source_name, frame in (("record-level", record), ("assessment", assessment), ("aggregate", aggregate)):
                if frame is None or frame.empty or metric not in frame.columns:
                    continue
                selected = frame[frame["centre"] == centre][metric].dropna()
                if not selected.empty:
                    values.append(float(selected.iloc[-1]))
                    sources.append(source_name)
            if values:
                # Priority order follows the loop: record-level, assessment, aggregate.
                row[metric] = values[0]
                if len(set(round(v, 8) for v in values)) > 1:
                    warnings.append(f"{metric.replace('_', ' ').title()} differed between {', '.join(sources)} sources for {centre}; the highest-priority record-level value was used.")
            else:
                row[metric] = np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _project_total(summary: pd.DataFrame, metric: str) -> float | None:
    if summary is None or summary.empty or metric not in summary.columns:
        return None
    centre = summary[~summary["centre"].eq("Project total (centre not stated)")]
    if centre[metric].notna().any():
        return float(centre[metric].fillna(0).sum())
    project = summary[summary["centre"].eq("Project total (centre not stated)")][metric].dropna()
    return float(project.iloc[-1]) if not project.empty else None


def _readiness_table(rows: list[tuple[str, Any, str, bool, str]]) -> pd.DataFrame:
    out = []
    for kpi, value, formula, required, note in rows:
        available = value is not None and not (isinstance(value, float) and np.isnan(value))
        status = "Ready" if available else "Data unavailable"
        if required and not available:
            status = "Not ready"
        out.append({"KPI / Requirement": kpi, "Status": status, "Formula / Rule": formula, "Submission Note": note})
    return pd.DataFrame(out)


def analyse_april(tables: list[SourceTable], reporting_year: int, project_start_year: int = 2025) -> ProjectResult:
    warnings: list[str] = []
    errors: list[str] = []
    record, sets, supplementary = _april_record_level(tables, reporting_year, project_start_year, warnings)
    assessment, assessment_sets, instrument_sets = _assessment_records(tables, "APRIL", reporting_year, project_start_year, set(APRIL_CENTRES), warnings)
    aggregate = _latest_aggregate_values(
        tables,
        "APRIL",
        ["seniors_onboarded", "risk_flags_total", "risk_flags_reviewed", "risk_flags_validated", "complete_assessment_sets_annual", "unique_tracked_seniors_3_year", "aac_clients_reached_annual", "volunteers_reached_annual", "caregivers_reached_annual", "aac_client_instances_3_year", "volunteer_instances_3_year", "caregiver_instances_3_year", "total_beneficiary_instances_3_year"],
        reporting_year,
        {"complete_assessment_sets_annual", "aac_clients_reached_annual", "volunteers_reached_annual", "caregivers_reached_annual"},
        set(APRIL_CENTRES),
        warnings,
    )
    summary = _combine_sources(record, assessment, aggregate, [
        "seniors_onboarded", "risk_flags_total", "risk_flags_reviewed", "risk_flags_validated_recorded", "risk_flags_validated",
        "complete_assessment_sets_annual", "unique_tracked_seniors_3_year",
        "aac_clients_reached_annual", "volunteers_reached_annual", "caregivers_reached_annual",
        "aac_client_instances_3_year", "volunteer_instances_3_year", "caregiver_instances_3_year", "total_beneficiary_instances_3_year",
        "mmse_completed_annual", "gds_completed_annual", "sppb_completed_annual",
    ], warnings)
    # Ensure all four centres are visible even if no data is found.
    summary = pd.DataFrame({"centre": APRIL_CENTRES}).merge(summary, on="centre", how="left")
    totals = {metric: _project_total(summary, metric) for metric in [
        "seniors_onboarded", "risk_flags_total", "risk_flags_reviewed", "risk_flags_validated_recorded", "risk_flags_validated",
        "complete_assessment_sets_annual", "unique_tracked_seniors_3_year",
        "aac_clients_reached_annual", "volunteers_reached_annual", "caregivers_reached_annual",
        "aac_client_instances_3_year", "volunteer_instances_3_year", "caregiver_instances_3_year", "total_beneficiary_instances_3_year",
        "mmse_completed_annual", "gds_completed_annual", "sppb_completed_annual",
    ]}
    # Record-level sets are more reliable for project totals and cross-centre de-duplication.
    set_metric_map = {
        "seniors_onboarded": "onboarded", "risk_flags_total": "flagged", "risk_flags_reviewed": "reviewed", "risk_flags_validated_recorded": "validated",
        "aac_clients_reached_annual": "clients", "volunteers_reached_annual": "volunteers", "caregivers_reached_annual": "caregivers",
        "aac_client_instances_3_year": "client_instances_3_year", "volunteer_instances_3_year": "volunteer_instances_3_year", "caregiver_instances_3_year": "caregiver_instances_3_year",
    }
    for metric, set_name in set_metric_map.items():
        if sets.get(set_name):
            totals[metric] = float(len(sets[set_name]))
    if assessment_sets["annual_complete"]:
        totals["complete_assessment_sets_annual"] = float(len(assessment_sets["annual_complete"]))
    if assessment_sets["three_year_tracked"]:
        totals["unique_tracked_seniors_3_year"] = float(len(assessment_sets["three_year_tracked"]))
    for instrument in ("mmse", "gds", "sppb"):
        if instrument_sets[instrument]:
            totals[f"{instrument}_completed_annual"] = float(len(instrument_sets[instrument]))
    # The application requires staff-assessment validation. Record-level
    # validated flags are accepted for the official numerator only when the
    # source names the validation instrument, or the same senior has assessment evidence.
    raw_validated_by_centre = sets.get("validated_by_centre", {})
    explicit_by_centre = sets.get("validated_explicit_assessment_by_centre", {})
    official_validated_global: set[str] = set()
    if sets.get("validated"):
        for centre in APRIL_CENTRES:
            raw_people = set(raw_validated_by_centre.get(centre, set()))
            explicit_people = set(explicit_by_centre.get(centre, set()))
            official_people = explicit_people
            official_validated_global.update(official_people)
            if raw_people:
                summary.loc[summary["centre"] == centre, "risk_flags_validated"] = float(len(official_people)) if explicit_people else np.nan
        totals["risk_flags_validated"] = float(len(official_validated_global)) if official_validated_global else None
        if not official_validated_global:
            warnings.append("Validated APRIL flags were found, but the source did not identify MMSE, GDS or SPPB as the validation assessment. The official validation numerator was withheld.")
    totals["total_beneficiary_instances_3_year"] = (
        (totals.get("aac_client_instances_3_year") or 0) +
        (totals.get("volunteer_instances_3_year") or 0) +
        (totals.get("caregiver_instances_3_year") or 0)
    ) if any(totals.get(k) is not None for k in ("aac_client_instances_3_year", "volunteer_instances_3_year", "caregiver_instances_3_year")) else totals.get("total_beneficiary_instances_3_year")

    flagged = totals.get("risk_flags_total")
    reviewed = totals.get("risk_flags_reviewed")
    validated = totals.get("risk_flags_validated")
    totals["official_risk_validation_rate"] = validated / flagged if flagged and validated is not None else None
    totals["risk_review_coverage"] = reviewed / flagged if flagged and reviewed is not None else None
    totals["reviewed_only_validation_rate"] = validated / reviewed if reviewed and validated is not None else None
    totals["risk_flags_pending_review"] = max(float(flagged - reviewed), 0) if flagged is not None and reviewed is not None else None

    milestone = _milestone_summary(tables, "APRIL", APRIL_MILESTONES)
    readiness = _readiness_table([
        ("1,000 seniors onboarded", totals.get("seniors_onboarded"), "Unique person IDs explicitly onboarded during the three-year project period", True, "Cumulative project measure"),
        ("80% validated at-risk seniors", totals.get("official_risk_validation_rate"), "APRIL-flagged seniors validated with MMSE/GDS/SPPB evidence ÷ all APRIL-flagged seniors", True, "Reviewed-only rate is shown separately and is not the application denominator"),
        ("1,000 AAC clients annually", totals.get("aac_clients_reached_annual"), "Unique AAC client IDs engaged in the selected reporting year", True, "Separate from APRIL onboarding"),
        ("100 volunteers annually", totals.get("volunteers_reached_annual"), "Unique volunteer IDs engaged in the selected reporting year", True, "Annual beneficiary commitment"),
        ("200 caregivers annually", totals.get("caregivers_reached_annual"), "Unique caregiver IDs engaged in the selected reporting year", True, "Annual beneficiary commitment"),
        ("3,000 AAC client beneficiary instances over three years", totals.get("aac_client_instances_3_year"), "Sum of each year's unique AAC client count across the three-year window", True, "Beneficiary-table total"),
        ("300 volunteer beneficiary instances over three years", totals.get("volunteer_instances_3_year"), "Sum of each year's unique volunteer count across the three-year window", True, "Beneficiary-table total"),
        ("600 caregiver beneficiary instances over three years", totals.get("caregiver_instances_3_year"), "Sum of each year's unique caregiver count across the three-year window", True, "Beneficiary-table total"),
        ("3,900 total beneficiary instances over three years", totals.get("total_beneficiary_instances_3_year"), "AAC client + volunteer + caregiver beneficiary instances", True, "Beneficiary-table total"),
        ("100 complete assessment sets annually", totals.get("complete_assessment_sets_annual"), "Unique seniors with MMSE, GDS and SPPB in one dated assessment episode", True, "Selected reporting year"),
        ("300 unique seniors tracked over three years", totals.get("unique_tracked_seniors_3_year"), "Unique seniors with assessment evidence across the full three-year project window", True, "Not restricted to the selected reporting year"),
        ("APRIL usage monitoring", supplementary.get("april_interactions_annual"), "Unique source-backed APRIL interaction records", False, "No numeric target in application"),
        ("Productivity savings", supplementary.get("total_staff_hours_saved"), "Sum of source-backed staff time saved", False, "No numeric target in application"),
        ("User satisfaction", supplementary.get("satisfaction_respondents"), "Source-backed satisfaction respondents and ratings", False, "No numeric target in application"),
    ])
    if not tables:
        errors.append("No readable structured project tables were found.")
    if totals.get("risk_flags_total") is None and totals.get("risk_flags_reviewed") is not None:
        warnings.append("Risk reviews were found but the total number of APRIL-flagged seniors was unavailable. The official 80% validation KPI cannot be calculated from reviewed records alone.")
    return ProjectResult(
        "APRIL", reporting_year, project_start_year, summary, totals, supplementary, assessment,
        milestone, _source_register(tables), _field_register(tables), readiness, errors,
        list(dict.fromkeys(warnings)),
        notes={"risk_formula": "Flagged seniors validated with MMSE/GDS/SPPB evidence ÷ all APRIL-flagged seniors"},
    )


def analyse_lharmoni(
    tables: list[SourceTable],
    reporting_year: int,
    project_start_year: int = 2025,
    followup_min_days: int = 335,
    followup_max_days: int = 395,
    timing_rule_approved: bool = False,
    raw_score_rule_approved: bool = False,
    data_cutoff: pd.Timestamp | None = None,
) -> ProjectResult:
    warnings: list[str] = []
    errors: list[str] = []
    if data_cutoff is None:
        all_dates = []
        for table in tables:
            fields = detect_fields(table.frame)
            dates = _date_series(table.frame, fields, ["reporting_date", "record_date", "followup_date", "assessment_date", "enrolment_date"])
            all_dates.extend(dates.dropna().tolist())
        data_cutoff = max(all_dates) if all_dates else pd.Timestamp.today().normalize()
    record, sets, supplementary, outcome_breakdown = _lharmoni_record_level(
        tables, reporting_year, project_start_year, followup_min_days, followup_max_days,
        timing_rule_approved, raw_score_rule_approved, pd.Timestamp(data_cutoff), warnings,
    )
    assessment, assessment_sets, instrument_sets = _assessment_records(tables, "LHARMONI", reporting_year, project_start_year, set(LHARMONI_CENTRES), warnings)
    aggregate = _latest_aggregate_values(
        tables,
        "LHARMONI",
        ["participating_seniors", "tracked_seniors_due", "outcome_eligible_seniors", "improved_or_maintained_seniors", "complete_assessment_sets_annual", "unique_tracked_seniors_3_year"],
        reporting_year,
        {"complete_assessment_sets_annual"},
        set(LHARMONI_CENTRES),
        warnings,
    )
    summary = _combine_sources(record, assessment, aggregate, [
        "participating_seniors", "tracked_seniors_due", "outcome_eligible_seniors", "improved_or_maintained_seniors",
        "complete_assessment_sets_annual", "unique_tracked_seniors_3_year",
        "mmse_completed_annual", "gds_completed_annual", "sppb_completed_annual",
    ], warnings)
    summary = pd.DataFrame({"centre": LHARMONI_CENTRES}).merge(summary, on="centre", how="left")
    totals = {metric: _project_total(summary, metric) for metric in [
        "participating_seniors", "tracked_seniors_due", "outcome_eligible_seniors", "improved_or_maintained_seniors",
        "complete_assessment_sets_annual", "unique_tracked_seniors_3_year",
        "mmse_completed_annual", "gds_completed_annual", "sppb_completed_annual",
    ]}
    for metric, set_name in {
        "participating_seniors": "participants", "tracked_seniors_due": "due", "outcome_eligible_seniors": "eligible", "improved_or_maintained_seniors": "success"
    }.items():
        if sets.get(set_name):
            totals[metric] = float(len(sets[set_name]))
    if assessment_sets["annual_complete"]:
        totals["complete_assessment_sets_annual"] = float(len(assessment_sets["annual_complete"]))
    if assessment_sets["three_year_tracked"]:
        totals["unique_tracked_seniors_3_year"] = float(len(assessment_sets["three_year_tracked"]))
    for instrument in ("mmse", "gds", "sppb"):
        if instrument_sets[instrument]:
            totals[f"{instrument}_completed_annual"] = float(len(instrument_sets[instrument]))

    due = totals.get("tracked_seniors_due")
    eligible = totals.get("outcome_eligible_seniors")
    success = totals.get("improved_or_maintained_seniors")
    totals["official_outcome_rate"] = success / due if timing_rule_approved and due and success is not None else None
    totals["one_year_assessment_coverage"] = eligible / due if timing_rule_approved and due and eligible is not None else None
    totals["completed_assessment_outcome_rate"] = success / eligible if eligible and success is not None else None

    milestone = _milestone_summary(tables, "LHARMONI", LHARMONI_MILESTONES)
    bb = summary.loc[summary["centre"] == "GLOW Bukit Batok", "participating_seniors"].dropna()
    ny = summary.loc[summary["centre"] == "GLOW Nanyang", "participating_seniors"].dropna()
    readiness = _readiness_table([
        ("1,000 participating seniors", totals.get("participating_seniors"), "Unique explicitly enrolled L'Harmoni seniors across both GLOW centres", True, "Cumulative project measure"),
        ("500 GLOW Bukit Batok participants", float(bb.iloc[0]) if not bb.empty else None, "Unique L'Harmoni participants at GLOW Bukit Batok", True, "Centre target"),
        ("500 GLOW Nanyang participants", float(ny.iloc[0]) if not ny.empty else None, "Unique L'Harmoni participants at GLOW Nanyang", True, "Centre target"),
        ("60% improve or maintain physical/cognitive scores", totals.get("official_outcome_rate"), "Successful one-year physical/cognitive outcomes ÷ all tracked seniors due for one-year follow-up", True, "Requires approved one-year timing window"),
        ("One-year assessment coverage", totals.get("one_year_assessment_coverage"), "Valid approved one-year outcomes ÷ tracked seniors due", False, "Supporting completeness measure"),
        ("100 complete assessment sets annually", totals.get("complete_assessment_sets_annual"), "Unique seniors with MMSE, GDS and SPPB in one dated assessment episode", True, "Selected reporting year"),
        ("300 unique seniors tracked over three years", totals.get("unique_tracked_seniors_3_year"), "Unique seniors with assessment evidence across the full three-year project window", True, "Not restricted to the selected reporting year"),
    ])
    if not timing_rule_approved:
        warnings.append("The official L’Harmoni 60% outcome KPI is withheld until the one-year follow-up window is approved in the dashboard controls.")
    if not tables:
        errors.append("No readable structured project tables were found.")
    notes = {
        "outcome_formula": "Successful physical/cognitive outcomes ÷ all tracked seniors due for one-year follow-up",
        "followup_window": f"{followup_min_days} to {followup_max_days} days after enrolment",
        "data_cutoff": pd.Timestamp(data_cutoff).date().isoformat(),
    }
    # Store the outcome breakdown in supplementary as a hidden dataframe reference is not suitable;
    # attach it to the assessment summary for the renderer via attrs.
    assessment.attrs["outcome_breakdown"] = outcome_breakdown
    return ProjectResult(
        "L’Harmoni", reporting_year, project_start_year, summary, totals, supplementary,
        assessment, milestone, _source_register(tables), _field_register(tables), readiness,
        errors, list(dict.fromkeys(warnings)), notes,
    )


# ---------------------------------------------------------------------------
# Streamlit rendering
# ---------------------------------------------------------------------------

def _fmt_count(value: Any) -> str:
    if value is None or pd.isna(value):
        return "Data unavailable"
    return f"{int(round(float(value))):,}"


def _fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "Data unavailable"
    return f"{float(value):.1%}"


def _inject_metric_card_css() -> None:
    """Apply responsive KPI-card styling so labels, values and notes never clip."""
    st.markdown(
        """
        <style>
        .aic-kpi-card {
            background: #FFFFFF;
            border: 1px solid #E9D6B3;
            border-radius: 18px;
            padding: 18px 18px 16px 18px;
            min-height: 176px;
            height: auto;
            box-shadow: 0 6px 18px rgba(13,43,69,.08);
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
            overflow: visible;
            margin-bottom: 12px;
            box-sizing: border-box;
        }
        .aic-kpi-label {
            color: #55623B;
            font-weight: 750;
            font-size: clamp(.88rem, 1.05vw, 1.02rem);
            line-height: 1.28;
            min-height: 2.55em;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: normal;
            margin-bottom: 10px;
        }
        .aic-kpi-value {
            color: #0D2B45;
            font-weight: 850;
            font-size: clamp(1.65rem, 2.5vw, 2.65rem);
            line-height: 1.08;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: normal;
            margin-bottom: 8px;
        }
        .aic-kpi-value.aic-long {
            font-size: clamp(1.22rem, 1.75vw, 1.9rem);
        }
        .aic-kpi-target {
            color: #C45D2D;
            font-weight: 700;
            font-size: .9rem;
            line-height: 1.25;
            white-space: normal;
            overflow-wrap: anywhere;
        }
        .aic-kpi-note {
            color: #55623B;
            font-size: .82rem;
            line-height: 1.3;
            margin-top: 7px;
            white-space: normal;
            overflow-wrap: anywhere;
        }
        div[data-testid="column"] { min-width: 0; }
        div[data-testid="stHorizontalBlock"] {
            gap: 2rem !important;
            align-items: stretch !important;
            margin-bottom: 1.25rem !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            flex: 1 1 300px !important;
            min-width: 280px !important;
        }
        @media (max-width: 1100px) {
            div[data-testid="stHorizontalBlock"] { gap: 1.5rem !important; }
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"] { min-width: 260px !important; }
        }
        @media (max-width: 900px) {
            .aic-kpi-card { min-height: 156px; padding: 18px; }
            .aic-kpi-label { min-height: auto; }
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: 1.25rem !important;
            }
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                flex: 1 1 calc(50% - 1.25rem) !important;
                min-width: 240px !important;
            }
        }
        @media (max-width: 640px) {
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                flex-basis: 100% !important;
                min-width: 100% !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _metric_card(
    label: str,
    value: Any,
    target: float | int | None = None,
    percentage: bool = False,
    note: str | None = None,
    decimals: int | None = None,
) -> None:
    """Render a full-height, wrapping KPI card that cannot truncate long text."""
    if value is None or pd.isna(value):
        display = "Data unavailable"
    elif percentage:
        display = f"{float(value):.1%}"
    elif decimals is not None:
        display = f"{float(value):,.{decimals}f}"
    else:
        display = f"{int(round(float(value))):,}"

    target_text = None
    if target is not None:
        target_text = f"Target: {target:.0%}" if percentage else f"Target: {int(target):,}"

    safe_label = html_lib.escape(str(label))
    safe_display = html_lib.escape(display)
    safe_target = html_lib.escape(target_text) if target_text else ""
    safe_note = html_lib.escape(str(note)) if note else ""
    long_class = " aic-long" if len(display) > 12 else ""

    st.markdown(
        f"""
        <div class="aic-kpi-card">
          <div class="aic-kpi-label">{safe_label}</div>
          <div class="aic-kpi-value{long_class}">{safe_display}</div>
          {f'<div class="aic-kpi-target">{safe_target}</div>' if safe_target else ''}
          {f'<div class="aic-kpi-note">{safe_note}</div>' if safe_note else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _progress_comparison_chart(items: list[dict], title: str, key: str) -> None:
    """Show grouped bar charts comparing the exact current value with target.

    Count KPIs and percentage KPIs are rendered in separate charts so unlike
    units never share the same axis. Missing source values are omitted rather
    than treated as zero. Numeric KPI cards above the chart remain visible.
    """
    count_rows: list[dict] = []
    rate_rows: list[dict] = []

    for item in items:
        value = item.get("value")
        target = item.get("target")
        if value is None or target is None or pd.isna(value) or pd.isna(target):
            continue
        value = float(value)
        target = float(target)
        label = str(item.get("label", "KPI"))

        if item.get("percentage", False):
            rate_rows.extend([
                {"KPI": label, "Measure": "Current", "Value": value * 100.0},
                {"KPI": label, "Measure": "Target", "Value": target * 100.0},
            ])
        else:
            count_rows.extend([
                {"KPI": label, "Measure": "Current", "Value": value},
                {"KPI": label, "Measure": "Target", "Value": target},
            ])

    if not count_rows and not rate_rows:
        st.info("No source-backed KPI values are available for target comparison.")
        return

    if count_rows:
        count_df = pd.DataFrame(count_rows)
        order = (count_df[count_df["Measure"] == "Target"]
                 .sort_values("Value", ascending=True)["KPI"].tolist())
        count_df["KPI"] = pd.Categorical(count_df["KPI"], categories=order, ordered=True)
        count_df = count_df.sort_values("KPI")
        count_df["Label"] = count_df["Value"].map(lambda x: f"{x:,.0f}")
        fig_counts = px.bar(
            count_df,
            x="Value",
            y="KPI",
            color="Measure",
            orientation="h",
            barmode="group",
            text="Label",
            title=f"{title} — counts",
            category_orders={"Measure": ["Current", "Target"]},
        )
        fig_counts.update_traces(
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{fullData.name}: %{x:,.0f}<extra></extra>",
        )
        fig_counts.update_layout(
            xaxis_title="Number",
            yaxis_title="",
            height=max(390, 72 * len(order) + 150),
            margin=dict(l=20, r=100, t=80, b=55),
            legend_title_text="",
            bargap=0.28,
            bargroupgap=0.08,
        )
        fig_counts.update_yaxes(automargin=True, tickfont=dict(size=13))
        fig_counts.update_xaxes(rangemode="tozero", gridcolor="rgba(13,43,69,0.10)")
        st.plotly_chart(fig_counts, use_container_width=True, key=f"{key}_counts")

    if rate_rows:
        rate_df = pd.DataFrame(rate_rows)
        order = (rate_df[rate_df["Measure"] == "Target"]
                 .sort_values("Value", ascending=True)["KPI"].tolist())
        rate_df["KPI"] = pd.Categorical(rate_df["KPI"], categories=order, ordered=True)
        rate_df = rate_df.sort_values("KPI")
        rate_df["Label"] = rate_df["Value"].map(lambda x: f"{x:.1f}%")
        fig_rates = px.bar(
            rate_df,
            x="Value",
            y="KPI",
            color="Measure",
            orientation="h",
            barmode="group",
            text="Label",
            title=f"{title} — rates",
            category_orders={"Measure": ["Current", "Target"]},
        )
        max_rate = max(100.0, float(rate_df["Value"].max()) * 1.18)
        fig_rates.update_traces(
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{fullData.name}: %{x:.1f}%<extra></extra>",
        )
        fig_rates.update_layout(
            xaxis_title="Percentage",
            yaxis_title="",
            xaxis_range=[0, max_rate],
            height=max(300, 90 * len(order) + 150),
            margin=dict(l=20, r=100, t=80, b=55),
            legend_title_text="",
            bargap=0.30,
            bargroupgap=0.08,
        )
        fig_rates.update_yaxes(automargin=True, tickfont=dict(size=13))
        fig_rates.update_xaxes(ticksuffix="%", gridcolor="rgba(13,43,69,0.10)")
        st.plotly_chart(fig_rates, use_container_width=True, key=f"{key}_rates")

def _header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="hero-card">
            <h1>{html_lib.escape(title)}</h1>
            <p>{html_lib.escape(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _targets_table(project: str) -> None:
    targets = APRIL_TARGETS if project == "APRIL" else LHARMONI_TARGETS
    rows = []
    for indicator, target, basis in targets:
        rows.append({"AIC/CST indicator": indicator, "Target": f"{target:.0%}" if isinstance(target, float) and target < 1 else f"{int(target):,}", "Reporting basis": basis})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _messages(result: ProjectResult, file_errors: list[str]) -> None:
    for error in file_errors + result.errors:
        st.error(error)
    for warning in result.warnings:
        st.warning(warning)


def _audit_tabs(result: ProjectResult) -> None:
    with st.expander("AIC submission readiness and calculation audit", expanded=True):
        st.dataframe(result.readiness, use_container_width=True, hide_index=True)
        not_ready = result.readiness["Status"].isin(["Not ready"])
        if not_ready.any():
            st.error("AIC submission status: NOT READY. Resolve every 'Not ready' item and reconcile against source records before submission.")
        else:
            st.success("All required KPI fields are available. A human reviewer must still reconcile the figures against the source files before submission.")
    audit1, audit2 = st.tabs(["Source register", "Matched fields"])
    with audit1:
        st.dataframe(result.source_register, use_container_width=True, hide_index=True)
    with audit2:
        st.dataframe(result.field_register, use_container_width=True, hide_index=True)


def _year_and_start_controls(tables: list[SourceTable], key_prefix: str) -> tuple[int, int]:
    years = discover_years(tables)
    current = datetime.now().year
    reporting_options = years if years else [current]
    reporting_year = st.selectbox("Reporting year for annual KPIs", reporting_options, index=len(reporting_options) - 1, key=f"{key_prefix}_reporting_year")
    default_start = min(years) if years else 2025
    project_start_year = st.number_input("Three-year study start year", min_value=2020, max_value=2035, value=int(default_start), step=1, key=f"{key_prefix}_project_start")
    st.caption(f"Annual KPIs use {reporting_year}. The cumulative study window is {int(project_start_year)}–{int(project_start_year)+2}.")
    return int(reporting_year), int(project_start_year)


def _upload_files(label: str, key: str):
    return st.file_uploader(
        label,
        type=["xlsx", "xls", "xlsm", "csv", "tsv", "txt", "json", "zip"],
        accept_multiple_files=True,
        key=key,
        help="Every sheet/table is scanned. The dashboard counts only fields that explicitly support the project KPI.",
    )


def render_april_page(template_path: Path | None = None) -> None:
    _inject_metric_card_css()
    _header("Project APRIL KPI Dashboard", "All four centres. Official CST indicators, annual beneficiary commitments, outcome-study measures, evaluation measures and implementation milestones.")
    st.info("Project APRIL uses GLOW Bukit Batok, Tzu Chi SEEN @ Bukit Batok, GLOW Nanyang and Tzu Chi SEEN @ Nanyang. Ordinary attendance is not treated as APRIL participation unless the project is explicitly identified.")
    with st.expander("All AIC/CST APRIL indicators reflected in this dashboard", expanded=True):
        _targets_table("APRIL")
        st.caption("Additional application evaluation measures shown below: APRIL usage, risk accuracy, productivity savings, user satisfaction and implementation milestones. These have no fixed numerical target in the application.")
    if template_path and template_path.exists():
        st.download_button("Download controlled AIC project data template", template_path.read_bytes(), file_name=template_path.name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    files = _upload_files("Upload APRIL source file(s)", "april_aic_upload")
    if not files:
        st.caption("Upload structured source files. Missing evidence remains 'Data unavailable'; the dashboard never fills missing KPI values with zero or estimates.")
        return
    tables, file_errors = read_project_files(files)
    reporting_year, project_start_year = _year_and_start_controls(tables, "april")
    result = analyse_april(tables, reporting_year, project_start_year)

    st.markdown("## Official numerical indicators")
    c1, c2, c3 = st.columns(3)
    with c1:
        _metric_card("Seniors onboarded", result.totals.get("seniors_onboarded"), 1000)
    with c2:
        _metric_card("Official risk validation rate", result.totals.get("official_risk_validation_rate"), 0.80, True, "Validated flagged seniors ÷ all APRIL-flagged seniors")
    with c3:
        _metric_card("Complete assessment sets", result.totals.get("complete_assessment_sets_annual"), 100, note=f"MMSE + GDS + SPPB in one dated episode, {reporting_year}")
    c4, c5, c6 = st.columns(3)
    with c4:
        _metric_card("AAC clients reached", result.totals.get("aac_clients_reached_annual"), 1000, note=str(reporting_year))
    with c5:
        _metric_card("Volunteers reached", result.totals.get("volunteers_reached_annual"), 100, note=str(reporting_year))
    with c6:
        _metric_card("Caregivers reached", result.totals.get("caregivers_reached_annual"), 200, note=str(reporting_year))
    c7, _, _ = st.columns(3)
    with c7:
        _metric_card("Unique seniors tracked", result.totals.get("unique_tracked_seniors_3_year"), 300, note=f"{project_start_year}–{project_start_year+2}")

    st.markdown("### Current versus target bar charts")
    _progress_comparison_chart([
        {"label": "Seniors onboarded", "value": result.totals.get("seniors_onboarded"), "target": 1000},
        {"label": "Risk validation rate", "value": result.totals.get("official_risk_validation_rate"), "target": 0.80, "percentage": True},
        {"label": "Complete assessment sets", "value": result.totals.get("complete_assessment_sets_annual"), "target": 100},
        {"label": "AAC clients reached", "value": result.totals.get("aac_clients_reached_annual"), "target": 1000},
        {"label": "Volunteers reached", "value": result.totals.get("volunteers_reached_annual"), "target": 100},
        {"label": "Caregivers reached", "value": result.totals.get("caregivers_reached_annual"), "target": 200},
        {"label": "Unique seniors tracked", "value": result.totals.get("unique_tracked_seniors_3_year"), "target": 300},
    ], "APRIL current versus official targets", "april_official_progress")

    st.markdown("## Risk-flag validation audit")
    r1, r2, r3 = st.columns(3)
    with r1: _metric_card("All seniors flagged", result.totals.get("risk_flags_total"))
    with r2: _metric_card("Reviewed by staff", result.totals.get("risk_flags_reviewed"))
    with r3: _metric_card("Validated as recorded", result.totals.get("risk_flags_validated_recorded"), note="Before assessment-evidence check")
    r4, r5, r6 = st.columns(3)
    with r4: _metric_card("Validated with assessment evidence", result.totals.get("risk_flags_validated"))
    with r5: _metric_card("Pending review", result.totals.get("risk_flags_pending_review"))
    with r6: _metric_card("Review coverage", result.totals.get("risk_review_coverage"), percentage=True)
    st.caption("Reviewed-only validation rate (supporting measure only): " + _fmt_pct(result.totals.get("reviewed_only_validation_rate")))

    st.markdown("## Centre comparison")
    display = result.centre_summary.copy().rename(columns={
        "centre": "Centre", "seniors_onboarded": "Onboarded", "risk_flags_total": "Flagged", "risk_flags_reviewed": "Reviewed", "risk_flags_validated_recorded": "Validated Recorded", "risk_flags_validated": "Validated with Assessment Evidence",
        "aac_clients_reached_annual": "AAC Clients", "volunteers_reached_annual": "Volunteers", "caregivers_reached_annual": "Caregivers",
        "aac_client_instances_3_year": "3-Year AAC Client Instances", "volunteer_instances_3_year": "3-Year Volunteer Instances", "caregiver_instances_3_year": "3-Year Caregiver Instances",
        "mmse_completed_annual": "MMSE", "gds_completed_annual": "GDS", "sppb_completed_annual": "SPPB", "complete_assessment_sets_annual": "Complete Sets", "unique_tracked_seniors_3_year": "3-Year Tracked",
    })
    st.dataframe(display, use_container_width=True, hide_index=True)

    st.markdown("## Three-year beneficiary-table commitment")
    b1, b2, b3 = st.columns(3)
    with b1: _metric_card("AAC client instances", result.totals.get("aac_client_instances_3_year"), 3000, note=f"{project_start_year}–{project_start_year+2}")
    with b2: _metric_card("Volunteer instances", result.totals.get("volunteer_instances_3_year"), 300, note=f"{project_start_year}–{project_start_year+2}")
    with b3: _metric_card("Caregiver instances", result.totals.get("caregiver_instances_3_year"), 600, note=f"{project_start_year}–{project_start_year+2}")
    b4, _, _ = st.columns(3)
    with b4: _metric_card("Total beneficiary instances", result.totals.get("total_beneficiary_instances_3_year"), 3900, note="Application beneficiary-table total")

    _progress_comparison_chart([
        {"label": "AAC client instances", "value": result.totals.get("aac_client_instances_3_year"), "target": 3000},
        {"label": "Volunteer instances", "value": result.totals.get("volunteer_instances_3_year"), "target": 300},
        {"label": "Caregiver instances", "value": result.totals.get("caregiver_instances_3_year"), "target": 600},
        {"label": "Total beneficiary instances", "value": result.totals.get("total_beneficiary_instances_3_year"), "target": 3900},
    ], "APRIL three-year beneficiary current versus target", "april_beneficiary_progress")

    st.markdown("## Annual assessment coverage")
    a1, a2, a3 = st.columns(3)
    with a1: _metric_card("MMSE completed", result.totals.get("mmse_completed_annual"))
    with a2: _metric_card("GDS completed", result.totals.get("gds_completed_annual"))
    with a3: _metric_card("SPPB completed", result.totals.get("sppb_completed_annual"))
    a4, _, _ = st.columns(3)
    with a4: _metric_card("All three completed", result.totals.get("complete_assessment_sets_annual"), 100)

    st.markdown("## Application evaluation measures")
    s1, s2, s3 = st.columns(3)
    with s1: _metric_card("APRIL interactions", result.supplementary.get("april_interactions_annual"), note=str(reporting_year))
    with s2: _metric_card("Unique APRIL users", result.supplementary.get("unique_active_april_users_annual"), note=str(reporting_year))
    with s3:
        _metric_card("Staff hours saved", result.supplementary.get("total_staff_hours_saved"), decimals=1)
    s4, _, _ = st.columns(3)
    with s4:
        _metric_card("Average satisfaction rating", result.supplementary.get("average_satisfaction_rating"), decimals=2)
    if result.supplementary.get("explicit_satisfaction_rate") is not None:
        st.caption(f"Explicit satisfaction rate: {result.supplementary['explicit_satisfaction_rate']:.1%} across {int(result.supplementary.get('satisfaction_respondents') or 0)} respondent(s).")

    st.markdown("## Implementation milestones")
    st.dataframe(result.milestone_summary, use_container_width=True, hide_index=True)
    _messages(result, file_errors)
    _audit_tabs(result)


def render_lharmoni_page(template_path: Path | None = None) -> None:
    _inject_metric_card_css()
    _header("Project L’Harmoni KPI Dashboard", "GLOW Bukit Batok and GLOW Nanyang only. Official participation, one-year physical/cognitive outcome, annual assessment and implementation measures.")
    st.info("Only records explicitly identified as GLOW Bukit Batok or GLOW Nanyang are included. SEEN and service-unspecified records are excluded from official L’Harmoni figures.")
    with st.expander("All AIC/CST L’Harmoni indicators reflected in this dashboard", expanded=True):
        _targets_table("LHARMONI")
        st.caption("The dashboard also shows one-year assessment coverage, track/session monitoring, transitions, ICCP escalation and implementation milestones where source data exists.")
    if template_path and template_path.exists():
        st.download_button("Download controlled AIC project data template", template_path.read_bytes(), file_name=template_path.name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    files = _upload_files("Upload L’Harmoni source file(s)", "lharmoni_aic_upload")
    if not files:
        st.caption("Upload structured source files. The official 60% KPI is withheld unless the one-year timing rule is explicitly approved below.")
        return
    tables, file_errors = read_project_files(files)
    reporting_year, project_start_year = _year_and_start_controls(tables, "lharmoni")

    st.markdown("### Official one-year outcome controls")
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        min_days = st.number_input("Minimum days after enrolment", min_value=1, max_value=730, value=335, step=1, key="lh_min_days")
    with cc2:
        max_days = st.number_input("Maximum days after enrolment", min_value=1, max_value=730, value=395, step=1, key="lh_max_days")
    with cc3:
        cutoff = st.date_input("Data cut-off date", value=date.today(), key="lh_cutoff")
    timing_approved = st.checkbox("The one-year follow-up window above has been approved for official reporting.", value=False, key="lh_timing_approved")
    score_rule_approved = st.checkbox("Use raw SPPB/MMSE score direction (post ≥ pre = improved/maintained) as an approved outcome rule when explicit domain classifications are absent.", value=False, key="lh_score_rule_approved")
    st.caption("Without approval, the dashboard shows evidence and coverage but does not publish an official 60% outcome result.")

    result = analyse_lharmoni(
        tables, reporting_year, project_start_year, int(min_days), int(max_days), timing_approved,
        score_rule_approved, pd.Timestamp(cutoff),
    )
    summary = result.centre_summary.copy()
    bb = summary.loc[summary["centre"] == "GLOW Bukit Batok", "participating_seniors"].dropna()
    ny = summary.loc[summary["centre"] == "GLOW Nanyang", "participating_seniors"].dropna()

    st.markdown("## Official numerical indicators")
    c1, c2, c3 = st.columns(3)
    with c1: _metric_card("Total participating seniors", result.totals.get("participating_seniors"), 1000)
    with c2: _metric_card("GLOW Bukit Batok participants", float(bb.iloc[0]) if not bb.empty else None, 500)
    with c3: _metric_card("GLOW Nanyang participants", float(ny.iloc[0]) if not ny.empty else None, 500)
    c4, c5, c6 = st.columns(3)
    with c4: _metric_card("Official improve/maintain rate", result.totals.get("official_outcome_rate"), 0.60, True, "Successful physical/cognitive outcomes ÷ all tracked seniors due")
    with c5: _metric_card("Complete assessment sets", result.totals.get("complete_assessment_sets_annual"), 100, note=f"{reporting_year}")
    with c6: _metric_card("Unique seniors tracked", result.totals.get("unique_tracked_seniors_3_year"), 300, note=f"{project_start_year}–{project_start_year+2}")

    st.markdown("### Current versus target bar charts")
    _progress_comparison_chart([
        {"label": "Total participating seniors", "value": result.totals.get("participating_seniors"), "target": 1000},
        {"label": "GLOW Bukit Batok participants", "value": float(bb.iloc[0]) if not bb.empty else None, "target": 500},
        {"label": "GLOW Nanyang participants", "value": float(ny.iloc[0]) if not ny.empty else None, "target": 500},
        {"label": "Improve / maintain rate", "value": result.totals.get("official_outcome_rate"), "target": 0.60, "percentage": True},
        {"label": "Complete assessment sets", "value": result.totals.get("complete_assessment_sets_annual"), "target": 100},
        {"label": "Unique seniors tracked", "value": result.totals.get("unique_tracked_seniors_3_year"), "target": 300},
    ], "L’Harmoni current versus official targets", "lharmoni_official_progress")

    st.markdown("## One-year outcome completeness")
    o1, o2, o3 = st.columns(3)
    with o1: _metric_card("Tracked seniors due", result.totals.get("tracked_seniors_due"))
    with o2: _metric_card("Valid one-year outcomes", result.totals.get("outcome_eligible_seniors"))
    with o3: _metric_card("Improved / maintained", result.totals.get("improved_or_maintained_seniors"))
    o4, _, _ = st.columns(3)
    with o4: _metric_card("Assessment coverage", result.totals.get("one_year_assessment_coverage"), percentage=True)
    st.caption("Completed-assessment outcome rate (supporting only): " + _fmt_pct(result.totals.get("completed_assessment_outcome_rate")))

    st.markdown("## GLOW centre comparison")
    display = summary.copy()
    display["official_outcome_rate"] = np.where(
        timing_approved & (pd.to_numeric(display.get("tracked_seniors_due"), errors="coerce") > 0),
        pd.to_numeric(display.get("improved_or_maintained_seniors"), errors="coerce") / pd.to_numeric(display.get("tracked_seniors_due"), errors="coerce"),
        np.nan,
    )
    display = display.rename(columns={
        "centre": "Centre", "participating_seniors": "Participants", "tracked_seniors_due": "One-Year Due",
        "outcome_eligible_seniors": "Valid Outcomes", "improved_or_maintained_seniors": "Improved/Maintained",
        "official_outcome_rate": "Official Outcome Rate", "mmse_completed_annual": "MMSE", "gds_completed_annual": "GDS",
        "sppb_completed_annual": "SPPB", "complete_assessment_sets_annual": "Complete Sets", "unique_tracked_seniors_3_year": "3-Year Tracked",
    })
    st.dataframe(display.style.format({"Official Outcome Rate": "{:.1%}"}, na_rep="Data unavailable"), use_container_width=True, hide_index=True)

    outcome_breakdown = result.assessment_summary.attrs.get("outcome_breakdown", pd.DataFrame())
    if isinstance(outcome_breakdown, pd.DataFrame) and not outcome_breakdown.empty:
        st.markdown("## Approved physical and cognitive outcome breakdown")
        st.dataframe(outcome_breakdown, use_container_width=True, hide_index=True)
        fig = px.bar(outcome_breakdown, x="Centre", y="Seniors", color="Outcome", facet_col="Domain", barmode="group", title="Approved one-year outcomes by domain")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("## Annual assessment coverage")
    a1, a2, a3 = st.columns(3)
    with a1: _metric_card("MMSE completed", result.totals.get("mmse_completed_annual"))
    with a2: _metric_card("GDS completed", result.totals.get("gds_completed_annual"))
    with a3: _metric_card("SPPB completed", result.totals.get("sppb_completed_annual"))
    a4, _, _ = st.columns(3)
    with a4: _metric_card("All three completed", result.totals.get("complete_assessment_sets_annual"), 100)

    st.markdown("## Programme fidelity and continuity monitoring")
    sup_rows = []
    for key, value in result.supplementary.items():
        label = key.replace("_", " ").title()
        if isinstance(value, float) and 0 <= value <= 1 and "rate" in key:
            shown = f"{value:.1%}"
        elif isinstance(value, float):
            shown = f"{value:,.2f}"
        elif value is None:
            shown = "Data unavailable"
        else:
            shown = f"{int(value):,}"
        sup_rows.append({"Monitoring Measure": label, "Current Value": shown})
    if sup_rows:
        st.dataframe(pd.DataFrame(sup_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No source-backed track, session, transition or ICCP escalation fields were detected.")

    st.markdown("## Implementation milestones")
    st.dataframe(result.milestone_summary, use_container_width=True, hide_index=True)
    _messages(result, file_errors)
    _audit_tabs(result)

# -----------------------------------------------------------------------------
# L'Harmoni is the reporting name for the combined GLOW Bukit Batok and
# GLOW Nanyang KPI view. It is not treated as a separate project dataset.
# -----------------------------------------------------------------------------
def render_lharmoni_page(template_path: Path | None = None) -> None:
    _inject_metric_card_css()
    _header(
        "L’Harmoni — Combined GLOW Centre KPIs",
        "Combined reporting view for GLOW Bukit Batok and GLOW Nanyang. L’Harmoni is a reporting name, not a separate project.",
    )
    st.info(
        "Upload attendance/export files for the two GLOW centres. Total participants and unique seniors tracked are "
        "calculated from cleaned participant names. Centre totals are read from the Centres field: values containing "
        "'Bukit Batok' are assigned to GLOW Bukit Batok, while values containing 'Nanyang' are assigned to GLOW Nanyang."
    )

    files = _upload_files(
        "Upload GLOW Bukit Batok and GLOW Nanyang source file(s)",
        "lharmoni_combined_glow_upload",
    )
    if not files:
        st.caption("Upload Excel, CSV or other supported structured attendance files to build the combined L’Harmoni view.")
        return

    tables, file_errors = read_project_files(files)
    if not tables:
        st.error("No readable tables were found in the uploaded files.")
        return

    frames = []
    for t in tables:
        frame = t.data.copy()
        frame["_source_file"] = t.source_file
        frame["_source_sheet"] = t.source_sheet
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True, sort=False)

    def _normalise_header(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()

    norm = {_normalise_header(c): c for c in df.columns}

    def find(*names: str):
        wanted = [_normalise_header(n) for n in names]
        for n in wanted:
            for k, c in norm.items():
                if k == n:
                    return c
        for n in wanted:
            for k, c in norm.items():
                if n in k or k in n:
                    return c
        return None

    # Organisation-specific centre logic:
    # 1. Prefer the exact field named "Centres" whenever it exists.
    # 2. Only fall back to recognised centre aliases when "Centres" is absent.
    exact_centres_col = next(
        (column for column in df.columns if _normalise_header(column) == "centres"),
        None,
    )
    centre_col = exact_centres_col or find(
        "centre", "centers", "center",
        "service centres", "service centre", "service centers", "service center",
        "centre name", "center name", "location", "site",
    )
    status_col = find("status", "attendance status", "attended")
    id_col = find("nric", "senior id", "client id", "member id", "participant id", "person id")
    name_col = find("display name", "member name", "participant name", "senior name", "name")
    activity_col = find("activity name", "programme name", "program name", "activity", "event name")
    session_col = find("session detail", "session date", "activity date", "programme date", "event date", "date")
    gender_col = find("gender", "sex")
    client_col = find("is client", "client status", "client type")
    boundary_col = find("within boundary", "boundary")
    cfs_col = find("cfs from", "cfs")
    domain_col = find("aap domain", "domain")

    # Keep only genuine attended rows when an attendance/status field is present.
    if status_col is not None:
        status_text = df[status_col].astype(str).str.strip().str.lower()
        attended_mask = status_text.isin(["attended", "present", "yes", "y", "1", "true"])
        if attended_mask.any():
            df = df.loc[attended_mask].copy()

    # The supplied L'Harmoni attendance export has no NRIC field, so names are
    # the official participant identifier for this page. Clean spacing and case
    # before deduplication so minor formatting differences do not inflate counts.
    if name_col is not None:
        names = df[name_col].astype(str).str.strip()
        names = names.str.replace(r"\s+", " ", regex=True)
        names = names.mask(names.str.lower().isin(["", "nan", "none", "null"]))
        df["_senior_identity"] = names.str.casefold()
        df["_senior_display_name"] = names
    elif id_col is not None:
        # Safety fallback for future files that unexpectedly contain an ID but no name.
        ids = df[id_col].astype(str).str.strip()
        ids = ids.mask(ids.str.lower().isin(["", "nan", "none", "null"]))
        df["_senior_identity"] = ids
        df["_senior_display_name"] = ids
    else:
        df["_senior_identity"] = np.nan
        df["_senior_display_name"] = np.nan

    # Centre assignment. Prefer explicit row-level centre values. When none exist,
    # allow the user to assign each uploaded file to a centre. This supports exports
    # that omit a centre column but are supplied as separate BB and Nanyang files.
    df["_lh_centre"] = np.nan
    if centre_col is not None:
        # Organisation rule: use the row-level Centres field. Any value containing
        # "Bukit Batok" belongs to GLOW Bukit Batok; any value containing
        # "Nanyang" belongs to GLOW Nanyang. Matching is case-insensitive and
        # tolerates extra words such as "GLOW", "Tzu Chi" or location details.
        centre_text = (
            df[centre_col]
            .astype(str)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
            .str.casefold()
        )
        # Exact organisation rule: any Centres value containing the words
        # "Bukit Batok" is Bukit Batok; any value containing "Nanyang" is Nanyang.
        # Use literal, case-insensitive matching after whitespace normalisation so
        # values such as "Tzu Chi SEEN @ Bukit Batok" classify correctly.
        bb_mask = centre_text.str.contains("bukit batok", regex=False, na=False)
        ny_mask = centre_text.str.contains("nanyang", regex=False, na=False)
        df.loc[bb_mask, "_lh_centre"] = "GLOW Bukit Batok"
        df.loc[ny_mask, "_lh_centre"] = "GLOW Nanyang"

        # Flag ambiguous rows rather than silently assigning them.
        ambiguous_mask = bb_mask & ny_mask
        if ambiguous_mask.any():
            df.loc[ambiguous_mask, "_lh_centre"] = np.nan
            st.warning(
                f"{int(ambiguous_mask.sum()):,} row(s) contained both 'Bukit Batok' and 'Nanyang' in "
                f"the {centre_col!r} field and were left unassigned for review."
            )

        unassigned_rows = int(df["_lh_centre"].isna().sum())
        if unassigned_rows:
            st.warning(
                f"{unassigned_rows:,} row(s) in the {centre_col!r} field contained neither "
                "'Bukit Batok' nor 'Nanyang' and were left unassigned."
            )

    unresolved_files = sorted(df.loc[df["_lh_centre"].isna(), "_source_file"].dropna().astype(str).unique())
    if unresolved_files:
        with st.expander("Centre assignment for files without a centre field", expanded=True):
            st.caption(
                "Assign a file only when the entire file belongs to one centre. Do not use Is Client, Within Boundary, "
                "AAP Domain or another unrelated field as a substitute for centre."
            )
            assignments = {}
            for idx, filename in enumerate(unresolved_files):
                assignments[filename] = st.selectbox(
                    f"Centre for {filename}",
                    ["Unassigned", "GLOW Bukit Batok", "GLOW Nanyang"],
                    key=f"lh_file_centre_{idx}_{filename}",
                )
            for filename, assigned in assignments.items():
                if assigned != "Unassigned":
                    mask = df["_lh_centre"].isna() & (df["_source_file"].astype(str) == filename)
                    df.loc[mask, "_lh_centre"] = assigned

    total_attendances = int(len(df))
    total_unique = int(df["_senior_identity"].dropna().nunique()) if df["_senior_identity"].notna().any() else None
    # In this operational interpretation, unique seniors tracked is the deduplicated
    # number of seniors represented in the attendance source across the available period.
    unique_tracked = total_unique

    centre_rows = []
    for centre in ["GLOW Bukit Batok", "GLOW Nanyang"]:
        part = df[df["_lh_centre"] == centre].copy()
        centre_rows.append({
            "Centre": centre,
            "Attendances": int(len(part)),
            "Participants": int(part["_senior_identity"].dropna().nunique()) if not part.empty else None,
        })
    centre_df = pd.DataFrame(centre_rows)
    bb_value = centre_df.loc[centre_df["Centre"] == "GLOW Bukit Batok", "Participants"].iloc[0]
    ny_value = centre_df.loc[centre_df["Centre"] == "GLOW Nanyang", "Participants"].iloc[0]
    bb_value = None if pd.isna(bb_value) else int(bb_value)
    ny_value = None if pd.isna(ny_value) else int(ny_value)

    st.markdown("## AIC/CST numerical indicators available from the attendance source")
    card_items = [
        ("Total participating seniors", total_unique, 1000),
        ("GLOW Bukit Batok participants", bb_value, 500),
        ("GLOW Nanyang participants", ny_value, 500),
        ("Unique seniors tracked", unique_tracked, 300),
    ]
    card_html = []
    for label, value, target in card_items:
        shown = "Data unavailable" if value is None else f"{value:,}"
        card_html.append(
            '<div class="aic-kpi-card">'
            f'<div class="aic-kpi-label">{html.escape(label)}</div>'
            f'<div class="aic-kpi-value">{html.escape(shown)}</div>'
            f'<div class="aic-kpi-target">Target: {target:,}</div>'
            '</div>'
        )
    st.markdown('<div class="aic-kpi-grid">' + ''.join(card_html) + '</div>', unsafe_allow_html=True)

    chart_rows = []
    for label, value, target in card_items:
        if value is not None:
            chart_rows.append({"KPI": label, "Current": value, "Target": target})
    if chart_rows:
        chart_df = pd.DataFrame(chart_rows)
        fig = px.bar(
            chart_df,
            y="KPI",
            x=["Current", "Target"],
            orientation="h",
            barmode="group",
            text_auto=True,
            title="Current result compared with target",
        )
        fig.update_layout(
            xaxis_title="Seniors",
            yaxis_title=None,
            legend_title=None,
            margin=dict(l=20, r=20, t=60, b=30),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=max(360, 95 * len(chart_df)),
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("## Combined operational overview")
    activities = df[activity_col].astype(str).str.strip().replace("", np.nan).nunique() if activity_col else None
    if session_col and activity_col:
        sessions = df[[activity_col, session_col]].astype(str).drop_duplicates().shape[0]
    elif session_col:
        sessions = df[session_col].astype(str).nunique()
    else:
        sessions = None
    average = total_attendances / sessions if sessions else None
    overview_cards = [
        ("Total attendances", f"{total_attendances:,}"),
        ("Unique seniors", f"{total_unique:,}" if total_unique is not None else "Data unavailable"),
        ("Activities", f"{activities:,}" if activities is not None else "Data unavailable"),
        ("Programme sessions", f"{sessions:,}" if sessions is not None else "Data unavailable"),
        ("Average attendance per session", f"{average:,.1f}" if average is not None else "Data unavailable"),
    ]
    overview_html = '<div class="aic-kpi-grid">' + ''.join(
        f'<div class="aic-kpi-card"><div class="aic-kpi-label">{html.escape(a)}</div>'
        f'<div class="aic-kpi-value">{html.escape(b)}</div></div>' for a, b in overview_cards
    ) + '</div>'
    st.markdown(overview_html, unsafe_allow_html=True)

    st.markdown("## Centre comparison")
    if centre_df["Participants"].notna().any():
        display_centre = centre_df.copy()
        display_centre["Participants"] = display_centre["Participants"].apply(
            lambda x: "Data unavailable" if pd.isna(x) else f"{int(x):,}"
        )
        st.dataframe(display_centre, use_container_width=True, hide_index=True)
    else:
        st.warning(
            "The uploaded source has no centre field and has not been assigned by file, so the dashboard cannot safely "
            "split participants between GLOW Bukit Batok and GLOW Nanyang. The combined total is calculated from cleaned participant names."
        )

    if activity_col is not None:
        grouped = df.groupby(activity_col, dropna=False)
        act = grouped.size().rename("Attendances").to_frame()
        if df["_senior_identity"].notna().any():
            act["Unique seniors"] = grouped["_senior_identity"].nunique()
        act = act.reset_index().sort_values("Attendances", ascending=False).head(20)
        st.markdown("## Top activities")
        st.dataframe(act, use_container_width=True, hide_index=True)
        fig = px.bar(
            act.sort_values("Attendances"),
            x="Attendances",
            y=activity_col,
            orientation="h",
            title="Top activities by attendance",
            text_auto=True,
        )
        fig.update_layout(height=650, yaxis_title=None, xaxis_title="Attendances")
        st.plotly_chart(fig, use_container_width=True)

    for col, title in [
        (domain_col, "AAP domain distribution"),
        (cfs_col, "CFS distribution"),
        (gender_col, "Gender distribution"),
        (client_col, "Client / non-client split"),
        (boundary_col, "Boundary participation"),
    ]:
        if col is not None:
            vc = df[col].fillna("Unknown").astype(str).value_counts().reset_index()
            vc.columns = [title, "Count"]
            st.markdown(f"## {title}")
            st.dataframe(vc, use_container_width=True, hide_index=True)
            st.plotly_chart(px.bar(vc, x=title, y="Count", title=title, text_auto=True), use_container_width=True)

    st.markdown("## Source and field audit")
    audit = pd.DataFrame({
        "Required concept": [
            "Centre", "Attendance status", "Senior identifier", "Activity", "Session/date",
            "Gender", "Client status", "Boundary", "CFS", "AAP domain",
        ],
        "Matched field": [
            centre_col, status_col, id_col or name_col, activity_col, session_col,
            gender_col, client_col, boundary_col, cfs_col, domain_col,
        ],
    })
    audit["Status"] = audit["Matched field"].apply(lambda x: "Matched" if x else "Data unavailable")
    st.dataframe(audit, use_container_width=True, hide_index=True)

    if centre_col is None:
        st.caption(
            "This source contains participant data but no explicit centre column. Total participants and unique tracked seniors "
            "are therefore available using cleaned participant names; centre-specific participant figures require separate centre files or a genuine centre field."
        )
    for error in file_errors:
        st.warning(error)

