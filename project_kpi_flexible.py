"""Flexible, auditable extraction for Project APRIL and Project L'Harmoni.

The module reads common structured file formats, scans every table/sheet, maps
recognised aliases to controlled KPI fields, and calculates only figures that
are supported by explicit source fields. It deliberately does not infer project
participation from ordinary centre attendance alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Iterable
import json
import re
import zipfile

import numpy as np
import pandas as pd

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".txt", ".json", ".zip"}

APRIL_CENTRES = [
    "GLOW Bukit Batok",
    "Tzu Chi SEEN @ Bukit Batok",
    "GLOW Nanyang",
    "Tzu Chi SEEN @ Nanyang",
]
LHARMONI_CENTRES = ["GLOW Bukit Batok", "GLOW Nanyang"]

APRIL_METRICS = [
    "seniors_onboarded",
    "risk_flags_reviewed",
    "risk_flags_validated",
    "complete_assessment_sets_annual",
    "unique_tracked_seniors_3_year",
    "aac_clients_reached_annual",
    "volunteers_reached_annual",
    "caregivers_reached_annual",
]
LHARMONI_METRICS = [
    "participating_seniors",
    "outcome_eligible_seniors",
    "improved_or_maintained_seniors",
    "complete_assessment_sets_annual",
    "unique_tracked_seniors_3_year",
]


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


ALIASES: dict[str, list[str]] = {
    "centre": ["centre", "center", "centre name", "center name", "site", "location", "branch", "aac centre", "service centre"],
    "project": ["project", "project name", "initiative", "programme", "program", "programme name", "program name", "activity", "activity name", "event", "event name"],
    "reporting_date": ["reporting date", "as at date", "as of date", "data cut off date", "data cutoff date", "cut off date", "cutoff date", "report date"],
    "record_date": ["date", "record date", "activity date", "session date", "engagement date", "created on", "created date"],
    "senior_id": ["senior id", "client id", "member id", "participant id", "beneficiary id", "user id", "person id", "resident id", "case id", "id number", "masked nric"],
    "senior_name": ["senior name", "client name", "member name", "participant name", "beneficiary name", "resident name", "full name", "name"],
    "beneficiary_type": ["beneficiary type", "participant type", "person type", "client type", "role", "stakeholder type", "category"],
    "source_reference": ["source reference", "source", "evidence", "evidence reference", "file reference", "record source"],
    "prepared_by": ["prepared by", "preparedby", "data prepared by"],
    "reviewed_by": ["reviewed by", "reviewedby", "verified by", "approved by"],
    # Direct APRIL aggregate fields
    "seniors_onboarded": ["seniors onboarded", "senior onboarded", "april seniors onboarded", "onboarded seniors", "number onboarded", "clients onboarded"],
    "risk_flags_reviewed": ["risk flags reviewed", "flags reviewed", "reviewed risk flags", "at risk seniors reviewed", "flagged seniors reviewed"],
    "risk_flags_validated": ["risk flags validated", "validated risk flags", "validated flags", "at risk seniors validated", "flagged seniors validated"],
    "complete_assessment_sets_annual": ["complete assessment sets annual", "annual complete assessment sets", "complete mmse gds sppb sets", "mmse gds sppb completed", "complete assessments annual", "annual assessment cohort"],
    "unique_tracked_seniors_3_year": ["unique tracked seniors 3 year", "unique seniors tracked 3 years", "three year tracked seniors", "3 year tracked seniors", "unique tracked seniors"],
    "aac_clients_reached_annual": ["aac clients reached annual", "annual aac clients reached", "aac clients reached", "annual clients reached"],
    "volunteers_reached_annual": ["volunteers reached annual", "annual volunteers reached", "volunteers reached", "annual volunteers"],
    "caregivers_reached_annual": ["caregivers reached annual", "annual caregivers reached", "caregivers reached", "annual caregivers"],
    # APRIL raw fields
    "onboarded": ["onboarded", "onboarding status", "april onboarded", "registered for april", "april user", "april registration status"],
    "onboarding_date": ["onboarding date", "onboarded date", "april onboarding date", "registration date", "april registration date"],
    "risk_flag_id": ["risk flag id", "flag id", "alert id", "risk id"],
    "risk_flagged": ["risk flagged", "at risk", "risk flag", "flagged", "april risk flag", "risk status"],
    "risk_reviewed": ["reviewed by staff", "staff reviewed", "risk reviewed", "review status", "flag reviewed"],
    "risk_validated": ["validated as risk", "validated", "risk validated", "staff validation", "validated by staff"],
    "validation_outcome": ["validation outcome", "review outcome", "risk outcome", "staff assessment outcome", "validation status"],
    "review_date": ["review date", "staff review date", "validation date"],
    # Assessment fields
    "assessment_type": ["assessment type", "test type", "instrument", "assessment", "tool"],
    "assessment_date": ["assessment date", "test date", "screening date", "evaluation date"],
    "assessment_point": ["assessment point", "assessment stage", "timepoint", "baseline follow up", "pre post", "visit type"],
    "mmse": ["mmse", "mini mental state examination", "mini state mental examination", "mmse score"],
    "gds": ["gds", "geriatric depression scale", "gds score"],
    "sppb": ["sppb", "short physical performance battery", "sppb score", "overall sppb score"],
    # Direct L'Harmoni aggregate fields
    "participating_seniors": ["participating seniors", "seniors participated", "lharmoni participants", "l harmoni participants", "participants enrolled", "unique participants", "total participants"],
    "outcome_eligible_seniors": ["outcome eligible seniors", "eligible seniors", "valid paired assessments", "paired assessment seniors", "eligible for outcome"],
    "improved_or_maintained_seniors": ["improved or maintained seniors", "improved maintained seniors", "seniors improved or maintained", "positive outcome seniors", "improved maintained participants"],
    # L'Harmoni raw fields
    "enrolment_date": ["enrolment date", "enrollment date", "joined date", "programme joining date", "program joining date", "lharmoni enrolment date", "l harmoni enrolment date"],
    "participant_status": ["participant status", "enrolment status", "enrollment status", "programme status", "program status", "active status"],
    "baseline_date": ["baseline date", "pre assessment date", "pre assessment", "baseline assessment date"],
    "followup_date": ["follow up date", "followup date", "post assessment date", "one year follow up date", "1 year follow up date"],
    "outcome_classification": ["outcome classification", "overall outcome", "outcome", "change category", "result classification", "wellbeing outcome"],
    "physical_outcome": ["physical outcome", "physical wellbeing outcome", "sppb outcome", "physical change"],
    "cognitive_outcome": ["cognitive outcome", "cognitive wellbeing outcome", "mmse outcome", "cognitive change"],
    "outcome_approved": ["outcome approved", "approved outcome", "classification approved", "reviewed outcome", "approved"],
    "outcome_rule_version": ["outcome rule version", "rule version", "classification rule", "outcome definition version"],
}

ALIAS_KEYS = {canonical: {_compact(x) for x in values + [canonical]} for canonical, values in ALIASES.items()}
ALL_ALIAS_COMPACT = set().union(*ALIAS_KEYS.values())


@dataclass
class SourceTable:
    source_file: str
    source_sheet: str
    frame: pd.DataFrame
    original_columns: list[str] = field(default_factory=list)


@dataclass
class ProjectResult:
    project: str
    reporting_year: int | None
    centre_summary: pd.DataFrame
    totals: dict[str, float | None]
    available_years: list[int]
    source_register: pd.DataFrame
    field_register: pd.DataFrame
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)


def _match_column(columns: Iterable[Any], canonical: str) -> str | None:
    exact = ALIAS_KEYS.get(canonical, {_compact(canonical)})
    normalized = {str(col): _compact(col) for col in columns}
    for col, value in normalized.items():
        if value in exact:
            return col
    # Conservative partial matching: only long aliases and one containment direction.
    for col, value in normalized.items():
        if len(value) < 5:
            continue
        for alias in exact:
            if len(alias) >= 7 and (value.startswith(alias) or alias.startswith(value)):
                return col
    return None


def detect_fields(frame: pd.DataFrame) -> dict[str, str]:
    found: dict[str, str] = {}
    for canonical in ALIASES:
        col = _match_column(frame.columns, canonical)
        if col is not None:
            found[canonical] = col
    return found


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
    best_row = None
    best_score = -1
    for idx in range(min(35, len(raw))):
        score = _header_score(raw.iloc[idx].tolist())
        if score > best_score:
            best_score = score
            best_row = idx
    # At least two controlled fields should be present. Otherwise use the first
    # non-empty row as the header, but later extraction remains conservative.
    header_idx = best_row if best_score >= 4 else 0
    headers = []
    seen: dict[str, int] = {}
    for i, value in enumerate(raw.iloc[header_idx].tolist()):
        base = str(value).strip() if pd.notna(value) and str(value).strip() else f"column_{i+1}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        headers.append(base if count == 0 else f"{base}_{count+1}")
    data = raw.iloc[header_idx + 1 :].copy()
    data.columns = headers
    data = data.dropna(how="all").dropna(axis=1, how="all")
    return data.reset_index(drop=True)


def _read_csv_bytes(data: bytes, sep: str | None = None) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            text = data.decode(encoding)
            if sep is None:
                return pd.read_csv(StringIO(text), header=None, sep=None, engine="python", dtype=object)
            return pd.read_csv(StringIO(text), header=None, sep=sep, engine="python", dtype=object)
        except Exception:
            continue
    return pd.DataFrame()


def _read_json_bytes(data: bytes) -> list[tuple[str, pd.DataFrame]]:
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except Exception:
        return []
    tables: list[tuple[str, pd.DataFrame]] = []
    if isinstance(obj, list):
        tables.append(("JSON", pd.json_normalize(obj)))
    elif isinstance(obj, dict):
        scalar_part = {k: v for k, v in obj.items() if not isinstance(v, (list, dict))}
        if scalar_part:
            tables.append(("JSON summary", pd.DataFrame([scalar_part])))
        for key, value in obj.items():
            if isinstance(value, list):
                try:
                    tables.append((str(key), pd.json_normalize(value)))
                except Exception:
                    pass
            elif isinstance(value, dict):
                try:
                    tables.append((str(key), pd.json_normalize(value)))
                except Exception:
                    pass
    return [(name, df) for name, df in tables if isinstance(df, pd.DataFrame) and not df.empty]


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
            frame = _table_from_raw(raw)
            if not frame.empty:
                tables.append(SourceTable(source_name, str(sheet), frame, [str(c) for c in frame.columns]))
    elif ext == ".csv":
        raw = _read_csv_bytes(data)
        frame = _table_from_raw(raw)
        if not frame.empty:
            tables.append(SourceTable(source_name, "CSV", frame, [str(c) for c in frame.columns]))
    elif ext in {".tsv", ".txt"}:
        raw = _read_csv_bytes(data, sep="\t" if ext == ".tsv" else None)
        frame = _table_from_raw(raw)
        if not frame.empty:
            tables.append(SourceTable(source_name, ext.lstrip(".").upper(), frame, [str(c) for c in frame.columns]))
    elif ext == ".json":
        for sheet, frame in _read_json_bytes(data):
            tables.append(SourceTable(source_name, sheet, frame, [str(c) for c in frame.columns]))
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
            pass
    return tables


def read_project_files(uploaded_files: Iterable[Any]) -> tuple[list[SourceTable], list[str]]:
    tables: list[SourceTable] = []
    errors: list[str] = []
    for uploaded in uploaded_files:
        try:
            data = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
            name = getattr(uploaded, "name", "uploaded_file")
            ext = Path(name).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                errors.append(f"{name}: unsupported format. Use XLSX, XLS, XLSM, CSV, TSV, TXT, JSON or ZIP.")
                continue
            found = _read_bytes(name, data)
            if not found:
                errors.append(f"{name}: no readable structured table was found.")
            tables.extend(found)
        except Exception as exc:
            errors.append(f"{getattr(uploaded, 'name', 'file')}: {exc}")
    return tables, errors


def _truthy(value: Any) -> bool:
    if pd.isna(value):
        return False
    text = _key(value)
    return text in {"yes", "y", "true", "1", "onboarded", "registered", "active", "completed", "reviewed", "validated", "approved", "at risk", "risk"}


def _falsey(value: Any) -> bool:
    if pd.isna(value):
        return False
    return _key(value) in {"no", "n", "false", "0", "not validated", "not approved", "not reviewed", "inactive", "cancelled"}


def canonical_centre(value: Any, source_hint: str = "") -> str | None:
    text = _key(value)
    hint = _key(source_hint)
    # Explicit row values take priority. The filename/sheet hint is used only
    # when the row does not identify GLOW versus SEEN or the location.
    row_has_service = "glow" in text or "seen" in text
    row_has_location = "bukit batok" in text or "nanyang" in text or re.search(r"\b(?:bb|ny)\b", text) is not None
    combined = text if row_has_service and row_has_location else f"{text} {hint}".strip()
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


def _entity_series(frame: pd.DataFrame, fields: dict[str, str]) -> pd.Series:
    if "senior_id" in fields:
        values = frame[fields["senior_id"]].fillna("").astype(str).str.strip()
        values = values.where(~values.str.lower().isin({"", "nan", "none"}))
        return values
    if "senior_name" in fields:
        values = frame[fields["senior_name"]].fillna("").astype(str).str.strip().str.lower()
        values = values.str.replace(r"\s+", " ", regex=True)
        values = values.where(~values.isin({"", "nan", "none"}))
        return values
    return pd.Series(pd.NA, index=frame.index, dtype="object")


def _date_series(frame: pd.DataFrame, fields: dict[str, str], preferred: list[str]) -> pd.Series:
    for canonical in preferred:
        col = fields.get(canonical)
        if col:
            parsed = pd.to_datetime(frame[col], errors="coerce")
            if parsed.notna().any():
                return parsed
    return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")


def _project_mask(table: SourceTable, fields: dict[str, str], project: str) -> tuple[pd.Series, bool]:
    frame = table.frame
    token = "april" if project == "APRIL" else "lharmoni"
    source_compact = _compact(f"{table.source_file} {table.source_sheet}")
    source_match = token in source_compact or (project != "APRIL" and "lharmoni" in source_compact)
    candidates = []
    for canonical in ("project",):
        col = fields.get(canonical)
        if col:
            values = frame[col].fillna("").astype(str).map(_compact)
            candidates.append(values.str.contains(token, regex=False))
            if project != "APRIL":
                candidates.append(values.str.contains("lharmoni", regex=False))
    if candidates:
        mask = candidates[0].copy()
        for other in candidates[1:]:
            mask = mask | other
        return mask, bool(mask.any())
    return pd.Series(source_match, index=frame.index), source_match


def _centre_series(table: SourceTable, fields: dict[str, str]) -> pd.Series:
    if "centre" in fields:
        return table.frame[fields["centre"]].apply(lambda x: canonical_centre(x, f"{table.source_file} {table.source_sheet}"))
    inferred = canonical_centre(None, f"{table.source_file} {table.source_sheet}")
    return pd.Series(inferred, index=table.frame.index, dtype="object")


def _numeric(frame: pd.DataFrame, col: str | None) -> pd.Series:
    if not col:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    values = frame[col].astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False)
    return pd.to_numeric(values, errors="coerce")


def _source_register(tables: list[SourceTable]) -> pd.DataFrame:
    rows = []
    for table in tables:
        fields = detect_fields(table.frame)
        rows.append({
            "Source File": table.source_file,
            "Sheet / Table": table.source_sheet,
            "Rows": len(table.frame),
            "Detected Fields": ", ".join(sorted(fields.keys())) if fields else "None",
        })
    return pd.DataFrame(rows)


def _field_register(tables: list[SourceTable]) -> pd.DataFrame:
    rows = []
    for table in tables:
        fields = detect_fields(table.frame)
        for canonical, original in fields.items():
            rows.append({
                "Source File": table.source_file,
                "Sheet / Table": table.source_sheet,
                "KPI Field": canonical,
                "Matched Source Column": str(original),
            })
    return pd.DataFrame(rows)


def discover_years(tables: list[SourceTable]) -> list[int]:
    years: set[int] = set()
    for table in tables:
        fields = detect_fields(table.frame)
        for canonical in ("reporting_date", "record_date", "onboarding_date", "assessment_date", "enrolment_date", "followup_date", "baseline_date"):
            col = fields.get(canonical)
            if col:
                parsed = pd.to_datetime(table.frame[col], errors="coerce")
                years.update(int(y) for y in parsed.dt.year.dropna().unique() if 2000 <= int(y) <= 2100)
    return sorted(years, reverse=True)


def _aggregate_rows(tables: list[SourceTable], metrics: list[str], project: str, year: int | None) -> tuple[pd.DataFrame, list[str]]:
    rows = []
    warnings = []
    for table in tables:
        fields = detect_fields(table.frame)
        metric_fields = {m: fields[m] for m in metrics if m in fields}
        if not metric_fields:
            continue
        project_mask, explicit = _project_mask(table, fields, project)
        # Direct project-specific KPI columns are sufficient evidence even when
        # there is no separate Project column.
        relevant = table.frame.loc[project_mask if explicit else pd.Series(True, index=table.frame.index)].copy()
        if relevant.empty:
            continue
        centres = _centre_series(table, fields).loc[relevant.index]
        report_dates = _date_series(table.frame, fields, ["reporting_date", "record_date"]).loc[relevant.index]
        if year is not None and report_dates.notna().any():
            keep = report_dates.dt.year.eq(year)
            relevant = relevant.loc[keep]
            centres = centres.loc[keep]
            report_dates = report_dates.loc[keep]
        for idx in relevant.index:
            row = {
                "centre": centres.loc[idx],
                "reporting_date": report_dates.loc[idx] if idx in report_dates.index else pd.NaT,
                "source": f"{table.source_file} / {table.source_sheet}",
            }
            any_value = False
            for metric, col in metric_fields.items():
                value = _numeric(table.frame.loc[[idx]], col).iloc[0]
                row[metric] = value
                any_value = any_value or pd.notna(value)
            if any_value:
                rows.append(row)
    if not rows:
        return pd.DataFrame(), warnings
    data = pd.DataFrame(rows)
    # Same-centre/date duplicate summaries are not added together. Taking the
    # maximum per KPI supports partial summary sheets without double counting
    # copied totals; the duplicate is disclosed for review.
    group_cols = ["centre"]
    if data["reporting_date"].notna().any():
        group_cols.append("reporting_date")
    if data.duplicated(subset=group_cols, keep=False).any():
        warnings.append("Duplicate aggregate rows were detected for the same centre/reporting period. The maximum source-backed value per KPI was used to avoid double counting copied totals.")
    agg_map = {metric: "max" for metric in metrics if metric in data.columns}
    agg_map["source"] = lambda s: "; ".join(sorted(set(str(x) for x in s if pd.notna(x))))
    data = data.groupby(group_cols, dropna=False, as_index=False).agg(agg_map)
    return data, warnings


def _assessment_sets(tables: list[SourceTable], project: str, year: int | None, allowed_centres: set[str]) -> tuple[pd.DataFrame, set[str], list[str]]:
    complete_entities: dict[str, set[str]] = {}
    tracked_entities: dict[str, set[str]] = {}
    warnings: list[str] = []
    long_rows = []
    wide_rows = []
    for table in tables:
        fields = detect_fields(table.frame)
        entity = _entity_series(table.frame, fields)
        if entity.notna().sum() == 0:
            continue
        project_mask, explicit = _project_mask(table, fields, project)
        has_assessment_fields = any(k in fields for k in ("assessment_type", "mmse", "gds", "sppb"))
        if not has_assessment_fields or not explicit:
            continue
        centres = _centre_series(table, fields)
        dates = _date_series(table.frame, fields, ["assessment_date", "record_date", "reporting_date"])
        mask = project_mask & entity.notna() & centres.isin(allowed_centres)
        if year is not None and dates.notna().any():
            mask &= dates.dt.year.eq(year)
        subset = table.frame.loc[mask]
        if subset.empty:
            continue
        for idx in subset.index:
            centre = centres.loc[idx]
            ent = str(entity.loc[idx])
            tracked_entities.setdefault(centre, set()).add(ent)
            if "assessment_type" in fields:
                typ = _compact(table.frame.at[idx, fields["assessment_type"]])
                canonical_type = "MMSE" if "mmse" in typ or "minimental" in typ or "ministate" in typ else "GDS" if "gds" in typ or "geriatricdepression" in typ else "SPPB" if "sppb" in typ or "shortphysical" in typ else None
                if canonical_type:
                    score_col = None
                    for c in ("raw_score", "score", canonical_type.lower()):
                        if c in fields:
                            score_col = fields[c]
                            break
                    value_present = True if score_col is None else pd.notna(table.frame.at[idx, score_col])
                    if value_present:
                        long_rows.append((centre, ent, canonical_type))
            else:
                present = {typ for typ in ("mmse", "gds", "sppb") if typ in fields and pd.notna(table.frame.at[idx, fields[typ]])}
                if present:
                    wide_rows.append((centre, ent, present))
    long_map: dict[tuple[str, str], set[str]] = {}
    for centre, ent, typ in long_rows:
        long_map.setdefault((centre, ent), set()).add(typ)
    for (centre, ent), types in long_map.items():
        if {"MMSE", "GDS", "SPPB"}.issubset(types):
            complete_entities.setdefault(centre, set()).add(ent)
    for centre, ent, types in wide_rows:
        mapped = {x.upper() for x in types}
        if {"MMSE", "GDS", "SPPB"}.issubset(mapped):
            complete_entities.setdefault(centre, set()).add(ent)
    rows = []
    all_centres = sorted(set(complete_entities) | set(tracked_entities))
    for centre in all_centres:
        rows.append({
            "centre": centre,
            "complete_assessment_sets_annual": len(complete_entities.get(centre, set())),
            "unique_tracked_seniors_3_year": len(tracked_entities.get(centre, set())),
        })
    all_tracked = set().union(*tracked_entities.values()) if tracked_entities else set()
    if tracked_entities and any(set_a & set_b for i, set_a in enumerate(tracked_entities.values()) for set_b in list(tracked_entities.values())[i+1:]):
        warnings.append("Some assessed seniors appear under more than one centre. Project-wide unique tracked counts were de-duplicated by Senior_ID/Name.")
    return pd.DataFrame(rows), all_tracked, warnings


def _april_raw(tables: list[SourceTable], year: int | None) -> tuple[pd.DataFrame, dict[str, set[str]], list[str], dict[str, str]]:
    centre_sets: dict[str, dict[str, set[str]]] = {}
    risk_reviewed: dict[str, set[str]] = {}
    risk_validated: dict[str, set[str]] = {}
    warnings: list[str] = []
    notes: dict[str, str] = {}
    evidence_metrics: set[str] = set()
    allowed = set(APRIL_CENTRES) | {"Bukit Batok (service unspecified)", "Nanyang (service unspecified)"}
    for table in tables:
        fields = detect_fields(table.frame)
        project_mask, explicit = _project_mask(table, fields, "APRIL")
        explicit = explicit or any(k in fields for k in ("onboarded", "onboarding_date", "risk_flagged", "risk_reviewed", "risk_validated", "validation_outcome"))
        if not explicit:
            continue
        if not project_mask.any():
            project_mask = pd.Series(True, index=table.frame.index)
        entity = _entity_series(table.frame, fields)
        centres = _centre_series(table, fields)
        dates = _date_series(table.frame, fields, ["onboarding_date", "record_date", "reporting_date"])
        base_mask = project_mask & centres.isin(allowed)
        if year is not None and dates.notna().any():
            year_mask = dates.dt.year.eq(year)
        else:
            year_mask = pd.Series(True, index=table.frame.index)

        # Onboarding
        if "onboarded" in fields or "onboarding_date" in fields:
            evidence_metrics.add("seniors_onboarded")
            onboard_mask = base_mask & entity.notna()
            if "onboarded" in fields:
                onboard_mask &= table.frame[fields["onboarded"]].apply(_truthy)
            elif "onboarding_date" in fields:
                onboard_mask &= pd.to_datetime(table.frame[fields["onboarding_date"]], errors="coerce").notna()
            for idx in table.frame.index[onboard_mask]:
                centre_sets.setdefault(centres.loc[idx], {}).setdefault("seniors_onboarded", set()).add(str(entity.loc[idx]))

        # Risk validation: official wording refers to seniors, so person-level
        # de-duplication is used when an identifier is available.
        if any(k in fields for k in ("risk_flagged", "risk_reviewed", "risk_validated", "validation_outcome", "risk_flag_id")):
            evidence_metrics.update({"risk_flags_reviewed", "risk_flags_validated"})
            for idx in table.frame.index[base_mask]:
                centre = centres.loc[idx]
                ent = entity.loc[idx]
                flag_id = table.frame.at[idx, fields["risk_flag_id"]] if "risk_flag_id" in fields else None
                record_key = str(ent) if pd.notna(ent) else f"{table.source_file}:{table.source_sheet}:{idx}:{flag_id}"
                reviewed = False
                validated = False
                if "risk_reviewed" in fields:
                    reviewed = _truthy(table.frame.at[idx, fields["risk_reviewed"]])
                if "validation_outcome" in fields:
                    outcome = _key(table.frame.at[idx, fields["validation_outcome"]])
                    if outcome:
                        reviewed = True
                        validated = outcome in {"validated", "confirmed", "at risk", "true risk", "risk confirmed"}
                        if "not validated" in outcome or "false positive" in outcome:
                            validated = False
                if "risk_validated" in fields:
                    raw = table.frame.at[idx, fields["risk_validated"]]
                    validated = _truthy(raw) and not _falsey(raw)
                    reviewed = reviewed or validated or _falsey(raw)
                if "review_date" in fields and pd.notna(table.frame.at[idx, fields["review_date"]]):
                    reviewed = True
                if reviewed:
                    risk_reviewed.setdefault(centre, set()).add(record_key)
                if validated:
                    risk_validated.setdefault(centre, set()).add(record_key)

        # Beneficiaries, only when type/role is explicit.
        if "beneficiary_type" in fields and entity.notna().any():
            types = table.frame[fields["beneficiary_type"]].fillna("").astype(str).map(_key)
            role_text = " ".join(types.tolist())
            if any(x in role_text for x in ("aac client", "senior", "client", "participant")):
                evidence_metrics.add("aac_clients_reached_annual")
            if "volunteer" in role_text:
                evidence_metrics.add("volunteers_reached_annual")
            if "caregiver" in role_text or "carer" in role_text:
                evidence_metrics.add("caregivers_reached_annual")
            for idx in table.frame.index[base_mask & year_mask & entity.notna()]:
                role = types.loc[idx]
                metric = None
                if any(x in role for x in ("aac client", "senior", "client", "participant")):
                    metric = "aac_clients_reached_annual"
                elif "volunteer" in role:
                    metric = "volunteers_reached_annual"
                elif "caregiver" in role or "carer" in role:
                    metric = "caregivers_reached_annual"
                if metric:
                    centre_sets.setdefault(centres.loc[idx], {}).setdefault(metric, set()).add(str(entity.loc[idx]))
    rows = []
    centres = sorted(set(centre_sets) | set(risk_reviewed) | set(risk_validated))
    for centre in centres:
        row = {"centre": centre}
        for metric in ("seniors_onboarded", "aac_clients_reached_annual", "volunteers_reached_annual", "caregivers_reached_annual"):
            row[metric] = len(centre_sets.get(centre, {}).get(metric, set())) if metric in evidence_metrics else np.nan
        row["risk_flags_reviewed"] = len(risk_reviewed.get(centre, set())) if "risk_flags_reviewed" in evidence_metrics else np.nan
        row["risk_flags_validated"] = len(risk_validated.get(centre, set())) if "risk_flags_validated" in evidence_metrics else np.nan
        rows.append(row)
    if any(c.endswith("service unspecified)") for c in centres):
        warnings.append("Some APRIL records identify only Bukit Batok or Nanyang, not GLOW versus SEEN. They are included in the project-wide total but kept in an 'unspecified service' row for centre comparison.")
    notes["risk_basis"] = "Unique flagged seniors where Senior_ID/Name was available; otherwise unique source risk records."
    raw_sets = {
        "onboarded": set().union(*(v.get("seniors_onboarded", set()) for v in centre_sets.values())) if centre_sets else set(),
        "clients": set().union(*(v.get("aac_clients_reached_annual", set()) for v in centre_sets.values())) if centre_sets else set(),
        "volunteers": set().union(*(v.get("volunteers_reached_annual", set()) for v in centre_sets.values())) if centre_sets else set(),
        "caregivers": set().union(*(v.get("caregivers_reached_annual", set()) for v in centre_sets.values())) if centre_sets else set(),
        "risk_reviewed": set().union(*risk_reviewed.values()) if risk_reviewed else set(),
        "risk_validated": set().union(*risk_validated.values()) if risk_validated else set(),
    }
    return pd.DataFrame(rows), raw_sets, warnings, notes


def _lharmoni_raw(tables: list[SourceTable], year: int | None) -> tuple[pd.DataFrame, dict[str, set[str]], list[str], dict[str, str]]:
    participants: dict[str, set[str]] = {}
    eligible: dict[str, set[str]] = {}
    success: dict[str, set[str]] = {}
    warnings: list[str] = []
    participant_evidence = False
    outcome_evidence = False
    notes = {"outcome_basis": "Approved, explicit one-year outcome classifications only."}
    for table in tables:
        fields = detect_fields(table.frame)
        project_mask, explicit = _project_mask(table, fields, "LHARMONI")
        explicit = explicit or any(k in fields for k in ("enrolment_date", "outcome_classification", "physical_outcome", "cognitive_outcome", "outcome_rule_version"))
        if not explicit:
            continue
        if not project_mask.any():
            project_mask = pd.Series(True, index=table.frame.index)
        entity = _entity_series(table.frame, fields)
        centres = _centre_series(table, fields)
        base_mask = project_mask & entity.notna()
        # L'Harmoni requires explicit GLOW centre evidence. Generic location and
        # SEEN records are excluded rather than silently reassigned.
        invalid_mask = base_mask & ~centres.isin(LHARMONI_CENTRES)
        if invalid_mask.any():
            warnings.append(f"{table.source_file} / {table.source_sheet}: {int(invalid_mask.sum())} L’Harmoni row(s) were excluded because the centre was not explicitly GLOW Bukit Batok or GLOW Nanyang.")
        base_mask &= centres.isin(LHARMONI_CENTRES)
        enrol_dates = _date_series(table.frame, fields, ["enrolment_date", "record_date", "reporting_date"])
        annual_mask = pd.Series(True, index=table.frame.index)
        if year is not None and enrol_dates.notna().any():
            annual_mask &= enrol_dates.dt.year.eq(year)

        has_participant_evidence = any(k in fields for k in ("enrolment_date", "participant_status")) or "project" in fields
        if has_participant_evidence:
            participant_evidence = True
            part_mask = base_mask & annual_mask
            if "participant_status" in fields:
                status = table.frame[fields["participant_status"]].fillna("").astype(str).map(_key)
                part_mask &= ~status.isin({"cancelled", "withdrawn before joining", "not enrolled", "rejected"})
            for idx in table.frame.index[part_mask]:
                participants.setdefault(centres.loc[idx], set()).add(str(entity.loc[idx]))

        outcome_cols = [k for k in ("outcome_classification", "physical_outcome", "cognitive_outcome") if k in fields]
        if outcome_cols:
            outcome_evidence = True
            for idx in table.frame.index[base_mask]:
                ent = str(entity.loc[idx])
                approved = True
                if "outcome_approved" in fields:
                    approved = _truthy(table.frame.at[idx, fields["outcome_approved"]])
                rule_present = "outcome_rule_version" in fields and bool(str(table.frame.at[idx, fields["outcome_rule_version"]]).strip())
                followup_present = "followup_date" in fields and pd.notna(pd.to_datetime(table.frame.at[idx, fields["followup_date"]], errors="coerce"))
                classifications = [_key(table.frame.at[idx, fields[c]]) for c in outcome_cols]
                classifications = [x for x in classifications if x and x not in {"nan", "none"}]
                recognised = any(any(token in x for token in ("improved", "maintained", "no change", "declined", "deteriorated")) for x in classifications)
                if not (approved and rule_present and followup_present and recognised):
                    continue
                centre = centres.loc[idx]
                eligible.setdefault(centre, set()).add(ent)
                is_success = any(("improved" in x or "maintained" in x or "no change" in x) and "declined" not in x for x in classifications)
                if is_success:
                    success.setdefault(centre, set()).add(ent)
    rows = []
    centres = sorted(set(participants) | set(eligible) | set(success))
    for centre in centres:
        rows.append({
            "centre": centre,
            "participating_seniors": len(participants.get(centre, set())) if participant_evidence else np.nan,
            "outcome_eligible_seniors": len(eligible.get(centre, set())) if outcome_evidence else np.nan,
            "improved_or_maintained_seniors": len(success.get(centre, set())) if outcome_evidence else np.nan,
        })
    raw_sets = {
        "participants": set().union(*participants.values()) if participants else set(),
        "eligible": set().union(*eligible.values()) if eligible else set(),
        "success": set().union(*success.values()) if success else set(),
    }
    return pd.DataFrame(rows), raw_sets, warnings, notes


def _merge_metric_sources(raw: pd.DataFrame, assessments: pd.DataFrame, aggregate: pd.DataFrame, metrics: list[str]) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    centre_values: dict[str, dict[str, float]] = {}
    source_by_metric: dict[tuple[str, str], str] = {}

    def apply(frame: pd.DataFrame, source_label: str, overwrite: bool):
        if frame is None or frame.empty or "centre" not in frame.columns:
            return
        for _, row in frame.iterrows():
            centre = row.get("centre")
            if pd.isna(centre) or not centre:
                centre = "Project total (centre not stated)"
            centre_values.setdefault(str(centre), {})
            for metric in metrics:
                if metric not in frame.columns or pd.isna(row.get(metric)):
                    continue
                value = float(row.get(metric))
                key = (str(centre), metric)
                if overwrite or metric not in centre_values[str(centre)]:
                    if key in source_by_metric and abs(centre_values[str(centre)][metric] - value) > 0.000001:
                        warnings.append(f"{metric.replace('_', ' ').title()} differs between {source_by_metric[key]} and {source_label} for {centre}. The record-level value was preferred.")
                    centre_values[str(centre)][metric] = value
                    source_by_metric[key] = source_label
                elif abs(centre_values[str(centre)][metric] - value) > 0.000001:
                    warnings.append(f"{metric.replace('_', ' ').title()} differs between source files for {centre}. The higher-priority source was retained.")

    # Aggregate first, then raw/assessment records overwrite it when available.
    apply(aggregate, "aggregate summary", overwrite=False)
    apply(raw, "record-level project data", overwrite=True)
    apply(assessments, "record-level assessments", overwrite=True)
    rows = []
    for centre, values in centre_values.items():
        row = {"centre": centre}
        row.update({metric: values.get(metric, np.nan) for metric in metrics})
        rows.append(row)
    return pd.DataFrame(rows), warnings


def _totals_from_summary(summary: pd.DataFrame, metrics: list[str], project_total_sets: dict[str, set[str]] | None = None) -> dict[str, float | None]:
    totals: dict[str, float | None] = {}
    if summary is None or summary.empty:
        return {m: None for m in metrics}
    centre_rows = summary[summary["centre"] != "Project total (centre not stated)"] if "centre" in summary.columns else summary
    project_rows = summary[summary["centre"] == "Project total (centre not stated)"] if "centre" in summary.columns else pd.DataFrame()
    for metric in metrics:
        value = None
        if project_total_sets:
            mapping = {
                "seniors_onboarded": "onboarded",
                "aac_clients_reached_annual": "clients",
                "volunteers_reached_annual": "volunteers",
                "caregivers_reached_annual": "caregivers",
                "risk_flags_reviewed": "risk_reviewed",
                "risk_flags_validated": "risk_validated",
                "participating_seniors": "participants",
                "outcome_eligible_seniors": "eligible",
                "improved_or_maintained_seniors": "success",
            }
            set_name = mapping.get(metric)
            if set_name and project_total_sets.get(set_name):
                value = float(len(project_total_sets[set_name]))
        if value is None and metric in centre_rows.columns and centre_rows[metric].notna().any():
            value = float(centre_rows[metric].fillna(0).sum())
        if value is None and metric in project_rows.columns and project_rows[metric].notna().any():
            value = float(project_rows[metric].dropna().max())
        totals[metric] = value
    return totals


def analyse_april(tables: list[SourceTable], reporting_year: int | None = None) -> ProjectResult:
    errors: list[str] = []
    warnings: list[str] = []
    years = discover_years(tables)
    if reporting_year is None and years:
        reporting_year = years[0]
    aggregate, agg_warnings = _aggregate_rows(tables, APRIL_METRICS, "APRIL", reporting_year)
    raw, raw_sets, raw_warnings, notes = _april_raw(tables, reporting_year)
    assessments, tracked_set, assess_warnings = _assessment_sets(tables, "APRIL", reporting_year, set(APRIL_CENTRES) | {"Bukit Batok (service unspecified)", "Nanyang (service unspecified)"})
    summary, merge_warnings = _merge_metric_sources(raw, assessments, aggregate, APRIL_METRICS)
    warnings.extend(agg_warnings + raw_warnings + assess_warnings + merge_warnings)
    totals = _totals_from_summary(summary, APRIL_METRICS, raw_sets)
    if tracked_set:
        totals["unique_tracked_seniors_3_year"] = float(len(tracked_set))
    reviewed = totals.get("risk_flags_reviewed")
    validated = totals.get("risk_flags_validated")
    totals["risk_validation_rate"] = validated / reviewed if reviewed is not None and reviewed > 0 and validated is not None else None
    if not tables:
        errors.append("No readable structured tables were found.")
    if summary.empty:
        warnings.append("No source-backed APRIL KPI fields were detected. Ordinary attendance records are not treated as APRIL records unless the project is explicitly identified.")
    missing = [m for m in APRIL_METRICS if totals.get(m) is None]
    if missing:
        warnings.append("Data unavailable for: " + ", ".join(m.replace("_", " ") for m in missing) + ".")
    return ProjectResult("APRIL", reporting_year, summary, totals, years, _source_register(tables), _field_register(tables), errors, list(dict.fromkeys(warnings)), notes)


def analyse_lharmoni(tables: list[SourceTable], reporting_year: int | None = None) -> ProjectResult:
    errors: list[str] = []
    warnings: list[str] = []
    years = discover_years(tables)
    if reporting_year is None and years:
        reporting_year = years[0]
    aggregate, agg_warnings = _aggregate_rows(tables, LHARMONI_METRICS, "LHARMONI", reporting_year)
    if not aggregate.empty:
        aggregate = aggregate[aggregate["centre"].isin(LHARMONI_CENTRES) | aggregate["centre"].isna()].copy()
    raw, raw_sets, raw_warnings, notes = _lharmoni_raw(tables, reporting_year)
    assessments, tracked_set, assess_warnings = _assessment_sets(tables, "LHARMONI", reporting_year, set(LHARMONI_CENTRES))
    summary, merge_warnings = _merge_metric_sources(raw, assessments, aggregate, LHARMONI_METRICS)
    if not summary.empty:
        summary = summary[summary["centre"].isin(LHARMONI_CENTRES) | summary["centre"].eq("Project total (centre not stated)")].copy()
    warnings.extend(agg_warnings + raw_warnings + assess_warnings + merge_warnings)
    totals = _totals_from_summary(summary, LHARMONI_METRICS, raw_sets)
    if tracked_set:
        totals["unique_tracked_seniors_3_year"] = float(len(tracked_set))
    eligible = totals.get("outcome_eligible_seniors")
    success = totals.get("improved_or_maintained_seniors")
    totals["outcome_rate"] = success / eligible if eligible is not None and eligible > 0 and success is not None else None
    if not tables:
        errors.append("No readable structured tables were found.")
    if summary.empty:
        warnings.append("No source-backed L’Harmoni KPI fields were detected. Normal GLOW attendance is not treated as L’Harmoni participation unless the project is explicitly identified.")
    missing = [m for m in LHARMONI_METRICS if totals.get(m) is None]
    if missing:
        warnings.append("Data unavailable for: " + ", ".join(m.replace("_", " ") for m in missing) + ".")
    return ProjectResult("L’Harmoni", reporting_year, summary, totals, years, _source_register(tables), _field_register(tables), errors, list(dict.fromkeys(warnings)), notes)
