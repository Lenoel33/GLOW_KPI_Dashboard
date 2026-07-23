"""CST/AIC KPI calculation and validation helpers.

This module is deliberately conservative:
- it never guesses an unknown centre;
- it never derives clinical outcome classifications from raw scores;
- it separates project indicators from beneficiary-table counts;
- it keeps excluded records visible in an exception log;
- it blocks an official export when critical validation or approval checks fail.

Source basis:
- CST FY2025 application, Project APRIL, pages 2-3.
- CST FY2025 application, Project L'Harmoni, pages 7-8.
- Operational centre mapping supplied by Tzu Chi staff for dashboard use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Any, Iterable

import numpy as np
import pandas as pd


ALL_CENTRES = [
    "GLOW Bukit Batok",
    "SEEN Bukit Batok",
    "GLOW Nanyang",
    "SEEN Nanyang",
]

PROJECT_CENTRES = {
    "APRIL": set(ALL_CENTRES),
    "L'Harmoni": {"GLOW Bukit Batok", "GLOW Nanyang"},
}

OFFICIAL_TARGETS = {
    "APRIL": {
        "unique_seniors_onboarded": 1000,
        "risk_validation_rate": 0.80,
        "annual_complete_assessment_sets": 100,
        "three_year_unique_tracked_seniors": 300,
        # These are shown separately because the application beneficiary table
        # is not necessarily the same as the 1,000-senior onboarding indicator.
        "annual_aac_clients": 1000,
        "annual_volunteers": 100,
        "annual_caregivers": 200,
    },
    "L'Harmoni": {
        "total_unique_participants": 1000,
        "centre_targets": {
            "GLOW Bukit Batok": 500,
            "GLOW Nanyang": 500,
        },
        "improved_or_maintained_rate": 0.60,
        "annual_complete_assessment_sets": 100,
        "three_year_unique_tracked_seniors": 300,
    },
}

SOURCE_NOTES = {
    "APRIL": (
        "CST application: 1,000 seniors onboarded; 80% of at-risk seniors flagged "
        "by APRIL validated through staff assessments; study of 100 seniors per year "
        "and 300 unique seniors over three years using MMSE, GDS and SPPB. The "
        "beneficiary table separately lists 1,000 AAC clients, 100 volunteers and "
        "200 caregivers annually."
    ),
    "L'Harmoni": (
        "CST application: 1,000 participating seniors; 500 per location; 60% of "
        "tracked seniors improve or maintain physical and/or cognitive wellbeing "
        "one year after joining; study of 100 seniors per year and 300 unique seniors "
        "over three years using MMSE, GDS and SPPB."
    ),
    "CENTRE_MAPPING": (
        "Operational dashboard mapping: APRIL applies to all four centres; "
        "L'Harmoni applies only to GLOW Bukit Batok and GLOW Nanyang. The submitted "
        "application names SEEN locations in its beneficiary tables, so written "
        "approval of this operational mapping is required before official export."
    ),
}

YES_VALUES = {"yes", "y", "true", "1", "approved", "complete", "completed"}
NO_VALUES = {"no", "n", "false", "0", "not approved", "incomplete"}

CENTRE_ALIASES = {
    "glow bukit batok": "GLOW Bukit Batok",
    "glow bb": "GLOW Bukit Batok",
    "glow @ bukit batok": "GLOW Bukit Batok",
    "glow bukit batok @ block 212": "GLOW Bukit Batok",
    "glow bukit batok blk 212": "GLOW Bukit Batok",
    "seen bukit batok": "SEEN Bukit Batok",
    "tzu chi seen @ bukit batok": "SEEN Bukit Batok",
    "seen bb": "SEEN Bukit Batok",
    "glow nanyang": "GLOW Nanyang",
    "glow ny": "GLOW Nanyang",
    "seen nanyang": "SEEN Nanyang",
    "tzu chi seen @ nanyang": "SEEN Nanyang",
    "seen ny": "SEEN Nanyang",
}

SHEET_ALIASES = {
    "april_onboarding": "APRIL_Onboarding",
    "april onboarding": "APRIL_Onboarding",
    "april_risk_flags": "APRIL_Risk_Flags",
    "april risk flags": "APRIL_Risk_Flags",
    "assessments": "Assessments",
    "lharmoni_enrolment": "LHarmoni_Enrolment",
    "l'harmoni enrolment": "LHarmoni_Enrolment",
    "lharmoni enrolment": "LHarmoni_Enrolment",
    "lharmoni_outcomes": "LHarmoni_Outcomes",
    "l'harmoni outcomes": "LHarmoni_Outcomes",
    "lharmoni outcomes": "LHarmoni_Outcomes",
    "april_beneficiaries": "APRIL_Beneficiaries",
    "april beneficiaries": "APRIL_Beneficiaries",
}

REQUIRED_COLUMNS = {
    "APRIL_Onboarding": [
        "Senior_ID",
        "Centre",
        "Onboarding_Date",
        "Onboarded",
        "Source_Record_ID",
    ],
    "APRIL_Risk_Flags": [
        "Risk_Flag_ID",
        "Senior_ID",
        "Centre",
        "Flag_Date",
        "Reviewed_By_Staff",
        "Validation_Outcome",
        "Reviewer",
    ],
    "Assessments": [
        "Assessment_Record_ID",
        "Senior_ID",
        "Centre",
        "Project",
        "Assessment_Type",
        "Assessment_Date",
        "Assessment_Point",
    ],
    "LHarmoni_Enrolment": [
        "Senior_ID",
        "Centre",
        "Enrolment_Date",
        "Active_Status",
        "Source_Record_ID",
    ],
    "LHarmoni_Outcomes": [
        "Outcome_Record_ID",
        "Senior_ID",
        "Centre",
        "Enrolment_Date",
        "Baseline_Date",
        "Followup_Date",
        "Physical_Outcome",
        "Cognitive_Outcome",
        "Outcome_Approved",
        "Rule_Version",
        "Reviewer",
    ],
    "APRIL_Beneficiaries": [
        "Beneficiary_Record_ID",
        "Beneficiary_ID",
        "Beneficiary_Type",
        "Centre",
        "Engagement_Date",
    ],
}

DATE_COLUMNS = {
    "APRIL_Onboarding": ["Onboarding_Date"],
    "APRIL_Risk_Flags": ["Flag_Date", "Review_Date", "Follow_Up_Date"],
    "Assessments": ["Assessment_Date"],
    "LHarmoni_Enrolment": ["Enrolment_Date"],
    "LHarmoni_Outcomes": ["Enrolment_Date", "Baseline_Date", "Followup_Date"],
    "APRIL_Beneficiaries": ["Engagement_Date"],
}

ID_COLUMNS = {
    "APRIL_Onboarding": ["Senior_ID", "Source_Record_ID"],
    "APRIL_Risk_Flags": ["Risk_Flag_ID", "Senior_ID"],
    "Assessments": ["Assessment_Record_ID", "Senior_ID"],
    "LHarmoni_Enrolment": ["Senior_ID", "Source_Record_ID"],
    "LHarmoni_Outcomes": ["Outcome_Record_ID", "Senior_ID"],
    "APRIL_Beneficiaries": ["Beneficiary_Record_ID", "Beneficiary_ID"],
}

UNIQUE_KEYS = {
    "APRIL_Onboarding": ["Source_Record_ID"],
    "APRIL_Risk_Flags": ["Risk_Flag_ID"],
    "Assessments": ["Assessment_Record_ID"],
    "LHarmoni_Enrolment": ["Source_Record_ID"],
    "LHarmoni_Outcomes": ["Outcome_Record_ID"],
    "APRIL_Beneficiaries": ["Beneficiary_Record_ID"],
}

VALID_ASSESSMENT_TYPES = {"MMSE", "GDS", "SPPB"}
VALID_PROJECTS = {"APRIL", "L'HARMONI", "L'HARMONI"}
VALID_OUTCOMES = {
    "IMPROVED",
    "MAINTAINED",
    "DECLINED",
    "NO CHANGE",
    "MIXED",
    "INSUFFICIENT DATA",
    "NOT ASSESSED",
}


@dataclass
class ValidationBundle:
    frames: dict[str, pd.DataFrame]
    issues: pd.DataFrame
    source_register: pd.DataFrame
    present_sheets: set[str]

    @property
    def critical_count(self) -> int:
        if self.issues.empty:
            return 0
        return int((self.issues["Severity"] == "Critical").sum())

    @property
    def warning_count(self) -> int:
        if self.issues.empty:
            return 0
        return int((self.issues["Severity"] == "Warning").sum())


@dataclass
class KpiBundle:
    summary: pd.DataFrame
    centre_breakdown: pd.DataFrame
    detail: pd.DataFrame
    calculations: dict[str, Any]


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def normalize_yes_no(value: Any) -> bool | None:
    text = _clean_text(value).lower()
    if text in YES_VALUES:
        return True
    if text in NO_VALUES:
        return False
    return None


def canonical_centre(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if text in ALL_CENTRES:
        return text
    return CENTRE_ALIASES.get(text.lower())


def canonical_project(value: Any) -> str | None:
    text = _clean_text(value).upper().replace("’", "'")
    if text == "APRIL":
        return "APRIL"
    if text in {"L'HARMONI", "LHARMONI", "L HARMONI"}:
        return "L'Harmoni"
    return None


def canonical_sheet_name(value: Any) -> str:
    text = _clean_text(value)
    return SHEET_ALIASES.get(text.lower(), text)


def _extract_sheet_table(raw_frame: pd.DataFrame, recognised_name: str) -> tuple[pd.DataFrame, int | None]:
    """Find the controlled header row and return the table below it.

    The provided template places explanatory text above row 4, while some users may
    supply a plain export with headers in row 1. Searching for the required column
    names supports both layouts without guessing field meanings.
    """
    required = set(REQUIRED_COLUMNS.get(recognised_name, []))
    best_index: int | None = None
    best_matches = -1
    scan_limit = min(len(raw_frame), 30)
    for idx in range(scan_limit):
        values = {_clean_text(v) for v in raw_frame.iloc[idx].tolist() if _clean_text(v)}
        matches = len(required.intersection(values))
        if required and required.issubset(values):
            best_index = idx
            best_matches = matches
            break
        if matches > best_matches:
            best_matches = matches
            best_index = idx

    # Require a meaningful header match. Otherwise retain the first row as a
    # provisional header so validation can report the missing mandatory columns.
    minimum_match = min(3, len(required)) if required else 1
    if best_index is None or best_matches < minimum_match:
        best_index = 0

    header_values = [_clean_text(v) for v in raw_frame.iloc[best_index].tolist()]
    keep_positions = [i for i, value in enumerate(header_values) if value]
    if not keep_positions:
        return pd.DataFrame(), best_index

    headers = [header_values[i] for i in keep_positions]
    data = raw_frame.iloc[best_index + 1 :, keep_positions].copy()
    data.columns = headers
    data = data.replace(r"^\s*$", pd.NA, regex=True).dropna(how="all").reset_index(drop=True)
    return data, best_index


def read_project_workbook(uploaded_file: Any) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Read one Excel workbook without persisting its contents.

    Returns raw sheets and a source register. The caller supplies a Streamlit
    UploadedFile, a path, or any file-like object accepted by pandas.
    """
    if isinstance(uploaded_file, (str, bytes)):
        file_name = str(uploaded_file).replace("\\", "/").split("/")[-1]
    else:
        file_name = getattr(uploaded_file, "name", None) or "uploaded_workbook.xlsx"
    raw_sheets = pd.read_excel(uploaded_file, sheet_name=None, header=None, dtype=object, engine="openpyxl")
    sheets: dict[str, pd.DataFrame] = {}
    source_rows = []
    for raw_name, raw_frame in raw_sheets.items():
        name = canonical_sheet_name(raw_name)
        if name in REQUIRED_COLUMNS:
            clean, header_index = _extract_sheet_table(raw_frame, name)
            # Trace back to the source worksheet row. Excel rows are 1-based and
            # the first data row follows the detected header row.
            first_data_row = int(header_index or 0) + 2
            clean["__Source_File"] = str(file_name)
            clean["__Source_Sheet"] = raw_name
            clean["__Source_Row"] = np.arange(first_data_row, first_data_row + len(clean))
            if name in sheets and not sheets[name].empty:
                sheets[name] = pd.concat([sheets[name], clean], ignore_index=True, sort=False)
            else:
                sheets[name] = clean
            recognised = name
            rows_read = int(len(clean))
        else:
            # Non-data guidance/category sheets are recorded but never treated as
            # project source data.
            sheets[name] = pd.DataFrame()
            recognised = "Unrecognised"
            rows_read = int(raw_frame.dropna(how="all").shape[0])

        source_rows.append(
            {
                "Source File": str(file_name),
                "Original Sheet": str(raw_name),
                "Recognised Sheet": recognised,
                "Rows Read": rows_read,
            }
        )
    return sheets, pd.DataFrame(source_rows)


def _issue(
    issues: list[dict[str, Any]],
    severity: str,
    sheet: str,
    row: Any,
    field: str,
    issue: str,
    value: Any = "",
    record_id: Any = "",
) -> None:
    issues.append(
        {
            "Severity": severity,
            "Sheet": sheet,
            "Source Row": row,
            "Record ID": _clean_text(record_id),
            "Field": field,
            "Issue": issue,
            "Original Value": _clean_text(value),
        }
    )


def _record_id_for_row(sheet: str, row: pd.Series) -> str:
    for candidate in UNIQUE_KEYS.get(sheet, []):
        if candidate in row.index and _clean_text(row.get(candidate)):
            return _clean_text(row.get(candidate))
    for candidate in ["Senior_ID", "Beneficiary_ID"]:
        if candidate in row.index and _clean_text(row.get(candidate)):
            return _clean_text(row.get(candidate))
    return ""


def validate_workbook(raw_sheets: dict[str, pd.DataFrame], source_register: pd.DataFrame) -> ValidationBundle:
    issues: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    present_sheets = {name for name in raw_sheets if name in REQUIRED_COLUMNS}

    for sheet, required in REQUIRED_COLUMNS.items():
        if sheet not in raw_sheets:
            _issue(
                issues,
                "Warning",
                sheet,
                "",
                "Sheet",
                "Optional or required-for-this-KPI sheet is missing; related KPI will show as unavailable.",
            )
            frames[sheet] = pd.DataFrame(columns=required)
            continue

        frame = raw_sheets[sheet].copy()
        missing_cols = [col for col in required if col not in frame.columns]
        for col in missing_cols:
            _issue(issues, "Critical", sheet, "", col, "Required column is missing.")
            frame[col] = pd.NA

        # Standardise ID fields as text and reject blanks.
        for col in ID_COLUMNS.get(sheet, []):
            if col not in frame.columns:
                continue
            frame[col] = frame[col].apply(_clean_text)
            blank_mask = frame[col].eq("")
            for _, row in frame.loc[blank_mask].iterrows():
                _issue(
                    issues,
                    "Critical",
                    sheet,
                    row.get("__Source_Row", ""),
                    col,
                    "Mandatory identifier is blank.",
                    row.get(col, ""),
                    _record_id_for_row(sheet, row),
                )

        # Parse and validate dates.
        for col in DATE_COLUMNS.get(sheet, []):
            if col not in frame.columns:
                continue
            original = frame[col].copy()
            parsed = pd.to_datetime(frame[col], errors="coerce", dayfirst=False)
            invalid_mask = original.notna() & original.astype(str).str.strip().ne("") & parsed.isna()
            frame[col] = parsed
            for idx in frame.index[invalid_mask]:
                row = frame.loc[idx]
                _issue(
                    issues,
                    "Critical",
                    sheet,
                    row.get("__Source_Row", ""),
                    col,
                    "Date could not be parsed.",
                    original.loc[idx],
                    _record_id_for_row(sheet, row),
                )

        # Strict centre handling: aliases may be standardised; unknowns are never guessed.
        if "Centre" in frame.columns:
            original_centre = frame["Centre"].copy()
            frame["Centre_Canonical"] = frame["Centre"].apply(canonical_centre)
            unknown_mask = frame["Centre_Canonical"].isna()
            for idx in frame.index[unknown_mask]:
                row = frame.loc[idx]
                _issue(
                    issues,
                    "Critical",
                    sheet,
                    row.get("__Source_Row", ""),
                    "Centre",
                    "Centre is blank or not in the approved centre mapping; record excluded from official KPI calculations.",
                    original_centre.loc[idx],
                    _record_id_for_row(sheet, row),
                )
            alias_mask = (~unknown_mask) & original_centre.apply(_clean_text).ne(frame["Centre_Canonical"])
            for idx in frame.index[alias_mask]:
                row = frame.loc[idx]
                _issue(
                    issues,
                    "Info",
                    sheet,
                    row.get("__Source_Row", ""),
                    "Centre",
                    f"Centre alias standardised to {frame.loc[idx, 'Centre_Canonical']}.",
                    original_centre.loc[idx],
                    _record_id_for_row(sheet, row),
                )

        # Duplicate source IDs are critical; do not silently remove them.
        for key in UNIQUE_KEYS.get(sheet, []):
            if key not in frame.columns:
                continue
            valid_key = frame[key].apply(_clean_text)
            dup_mask = valid_key.ne("") & valid_key.duplicated(keep=False)
            for idx in frame.index[dup_mask]:
                row = frame.loc[idx]
                _issue(
                    issues,
                    "Critical",
                    sheet,
                    row.get("__Source_Row", ""),
                    key,
                    "Duplicate source record ID. Resolve before official submission.",
                    row.get(key, ""),
                    _record_id_for_row(sheet, row),
                )

        frames[sheet] = frame

    # Sheet-specific checks.
    onboarding = frames["APRIL_Onboarding"]
    if not onboarding.empty:
        onboarding["Onboarded_Bool"] = onboarding["Onboarded"].apply(normalize_yes_no)
        duplicate_seniors = onboarding["Senior_ID"].ne("") & onboarding["Senior_ID"].duplicated(keep=False)
        for idx in onboarding.index[duplicate_seniors]:
            row = onboarding.loc[idx]
            _issue(
                issues,
                "Critical",
                "APRIL_Onboarding",
                row.get("__Source_Row", ""),
                "Senior_ID",
                "Senior appears more than once in APRIL onboarding. Resolve rather than double-counting.",
                row.get("Senior_ID", ""),
                _record_id_for_row("APRIL_Onboarding", row),
            )
        bad = onboarding["Onboarded_Bool"].isna()
        for idx in onboarding.index[bad]:
            row = onboarding.loc[idx]
            _issue(
                issues,
                "Critical",
                "APRIL_Onboarding",
                row.get("__Source_Row", ""),
                "Onboarded",
                "Value must be an explicit Yes or No.",
                row.get("Onboarded", ""),
                _record_id_for_row("APRIL_Onboarding", row),
            )

    risk = frames["APRIL_Risk_Flags"]
    if not risk.empty:
        risk["Reviewed_Bool"] = risk["Reviewed_By_Staff"].apply(normalize_yes_no)
        risk["Validation_Clean"] = risk["Validation_Outcome"].apply(lambda x: _clean_text(x).upper())
        for idx, row in risk.iterrows():
            if row.get("Reviewed_Bool") is None:
                _issue(
                    issues,
                    "Critical",
                    "APRIL_Risk_Flags",
                    row.get("__Source_Row", ""),
                    "Reviewed_By_Staff",
                    "Value must be an explicit Yes or No.",
                    row.get("Reviewed_By_Staff", ""),
                    _record_id_for_row("APRIL_Risk_Flags", row),
                )
            if row.get("Reviewed_Bool") is True:
                outcome = row.get("Validation_Clean", "")
                if outcome not in {"VALIDATED", "NOT VALIDATED"}:
                    _issue(
                        issues,
                        "Critical",
                        "APRIL_Risk_Flags",
                        row.get("__Source_Row", ""),
                        "Validation_Outcome",
                        "Reviewed records must be 'Validated' or 'Not Validated'.",
                        row.get("Validation_Outcome", ""),
                        _record_id_for_row("APRIL_Risk_Flags", row),
                    )
                if not _clean_text(row.get("Reviewer")):
                    _issue(
                        issues,
                        "Critical",
                        "APRIL_Risk_Flags",
                        row.get("__Source_Row", ""),
                        "Reviewer",
                        "Reviewed flag has no named reviewer.",
                        "",
                        _record_id_for_row("APRIL_Risk_Flags", row),
                    )

    assessments = frames["Assessments"]
    if not assessments.empty:
        assessments["Project_Canonical"] = assessments["Project"].apply(canonical_project)
        assessments["Assessment_Type_Clean"] = assessments["Assessment_Type"].apply(
            lambda x: _clean_text(x).upper()
        )
        assessments["Assessment_Point_Clean"] = assessments["Assessment_Point"].apply(
            lambda x: _clean_text(x).upper()
        )
        duplicate_assessment = assessments.duplicated(
            subset=[
                "Senior_ID",
                "Project_Canonical",
                "Centre_Canonical",
                "Assessment_Type_Clean",
                "Assessment_Date",
                "Assessment_Point_Clean",
            ],
            keep=False,
        ) & assessments["Senior_ID"].ne("")
        for idx in assessments.index[duplicate_assessment]:
            row = assessments.loc[idx]
            _issue(
                issues,
                "Critical",
                "Assessments",
                row.get("__Source_Row", ""),
                "Assessment_Record_ID",
                "Duplicate senior/type/date/point assessment record.",
                row.get("Assessment_Record_ID", ""),
                _record_id_for_row("Assessments", row),
            )
        for idx, row in assessments.iterrows():
            if row.get("Project_Canonical") is None:
                _issue(
                    issues,
                    "Critical",
                    "Assessments",
                    row.get("__Source_Row", ""),
                    "Project",
                    "Project must be APRIL or L'Harmoni.",
                    row.get("Project", ""),
                    _record_id_for_row("Assessments", row),
                )
            if row.get("Assessment_Type_Clean") not in VALID_ASSESSMENT_TYPES:
                _issue(
                    issues,
                    "Critical",
                    "Assessments",
                    row.get("__Source_Row", ""),
                    "Assessment_Type",
                    "Assessment type must be MMSE, GDS or SPPB.",
                    row.get("Assessment_Type", ""),
                    _record_id_for_row("Assessments", row),
                )
            if row.get("Project_Canonical") in PROJECT_CENTRES and row.get("Centre_Canonical") not in PROJECT_CENTRES[row.get("Project_Canonical")]:
                _issue(
                    issues,
                    "Critical",
                    "Assessments",
                    row.get("__Source_Row", ""),
                    "Centre",
                    f"Centre is not applicable to {row.get('Project_Canonical')} under the approved operational mapping.",
                    row.get("Centre", ""),
                    _record_id_for_row("Assessments", row),
                )
            if row.get("Assessment_Point_Clean") not in {"BASELINE", "FOLLOW-UP", "FOLLOWUP", "ANNUAL"}:
                _issue(
                    issues,
                    "Warning",
                    "Assessments",
                    row.get("__Source_Row", ""),
                    "Assessment_Point",
                    "Expected Baseline, Follow-up or Annual.",
                    row.get("Assessment_Point", ""),
                    _record_id_for_row("Assessments", row),
                )

    enrolment = frames["LHarmoni_Enrolment"]
    if not enrolment.empty:
        enrolment["Active_Bool"] = enrolment["Active_Status"].apply(normalize_yes_no)
        duplicate_seniors = enrolment["Senior_ID"].ne("") & enrolment["Senior_ID"].duplicated(keep=False)
        for idx in enrolment.index[duplicate_seniors]:
            row = enrolment.loc[idx]
            _issue(
                issues,
                "Critical",
                "LHarmoni_Enrolment",
                row.get("__Source_Row", ""),
                "Senior_ID",
                "Senior appears more than once in L'Harmoni enrolment.",
                row.get("Senior_ID", ""),
                _record_id_for_row("LHarmoni_Enrolment", row),
            )
        invalid_centre = enrolment["Centre_Canonical"].notna() & ~enrolment["Centre_Canonical"].isin(
            PROJECT_CENTRES["L'Harmoni"]
        )
        for idx in enrolment.index[invalid_centre]:
            row = enrolment.loc[idx]
            _issue(
                issues,
                "Critical",
                "LHarmoni_Enrolment",
                row.get("__Source_Row", ""),
                "Centre",
                "L'Harmoni record belongs to a non-GLOW centre under the operational mapping.",
                row.get("Centre", ""),
                _record_id_for_row("LHarmoni_Enrolment", row),
            )

    outcomes = frames["LHarmoni_Outcomes"]
    if not outcomes.empty:
        outcomes["Outcome_Approved_Bool"] = outcomes["Outcome_Approved"].apply(normalize_yes_no)
        duplicate_seniors = outcomes["Senior_ID"].ne("") & outcomes["Senior_ID"].duplicated(keep=False)
        for idx in outcomes.index[duplicate_seniors]:
            row = outcomes.loc[idx]
            _issue(
                issues,
                "Critical",
                "LHarmoni_Outcomes",
                row.get("__Source_Row", ""),
                "Senior_ID",
                "More than one L'Harmoni outcome record exists for the senior.",
                row.get("Senior_ID", ""),
                _record_id_for_row("LHarmoni_Outcomes", row),
            )
        outcomes["Physical_Outcome_Clean"] = outcomes["Physical_Outcome"].apply(
            lambda x: _clean_text(x).upper()
        )
        outcomes["Cognitive_Outcome_Clean"] = outcomes["Cognitive_Outcome"].apply(
            lambda x: _clean_text(x).upper()
        )
        outcomes["Followup_Days"] = (
            outcomes["Followup_Date"] - outcomes["Enrolment_Date"]
        ).dt.days
        for idx, row in outcomes.iterrows():
            if row.get("Centre_Canonical") not in PROJECT_CENTRES["L'Harmoni"]:
                _issue(
                    issues,
                    "Critical",
                    "LHarmoni_Outcomes",
                    row.get("__Source_Row", ""),
                    "Centre",
                    "L'Harmoni outcome belongs to a non-GLOW centre under the operational mapping.",
                    row.get("Centre", ""),
                    _record_id_for_row("LHarmoni_Outcomes", row),
                )
            for col, clean_col in [
                ("Physical_Outcome", "Physical_Outcome_Clean"),
                ("Cognitive_Outcome", "Cognitive_Outcome_Clean"),
            ]:
                if row.get(clean_col) not in VALID_OUTCOMES:
                    _issue(
                        issues,
                        "Critical",
                        "LHarmoni_Outcomes",
                        row.get("__Source_Row", ""),
                        col,
                        "Outcome must use an approved category from the template.",
                        row.get(col, ""),
                        _record_id_for_row("LHarmoni_Outcomes", row),
                    )
            if row.get("Outcome_Approved_Bool") is not True:
                _issue(
                    issues,
                    "Critical",
                    "LHarmoni_Outcomes",
                    row.get("__Source_Row", ""),
                    "Outcome_Approved",
                    "Outcome classification has not been approved and cannot enter the official rate.",
                    row.get("Outcome_Approved", ""),
                    _record_id_for_row("LHarmoni_Outcomes", row),
                )
            measurable_outcomes = {"IMPROVED", "MAINTAINED", "DECLINED", "NO CHANGE", "MIXED"}
            if (
                row.get("Physical_Outcome_Clean") not in measurable_outcomes
                and row.get("Cognitive_Outcome_Clean") not in measurable_outcomes
            ):
                _issue(
                    issues,
                    "Warning",
                    "LHarmoni_Outcomes",
                    row.get("__Source_Row", ""),
                    "Physical_Outcome / Cognitive_Outcome",
                    "Neither domain has a measurable approved outcome; record is excluded from the official denominator.",
                    f"{row.get('Physical_Outcome', '')} / {row.get('Cognitive_Outcome', '')}",
                    _record_id_for_row("LHarmoni_Outcomes", row),
                )
            if not _clean_text(row.get("Rule_Version")):
                _issue(
                    issues,
                    "Critical",
                    "LHarmoni_Outcomes",
                    row.get("__Source_Row", ""),
                    "Rule_Version",
                    "Approved outcome rule version is missing.",
                    "",
                    _record_id_for_row("LHarmoni_Outcomes", row),
                )
            if not _clean_text(row.get("Reviewer")):
                _issue(
                    issues,
                    "Critical",
                    "LHarmoni_Outcomes",
                    row.get("__Source_Row", ""),
                    "Reviewer",
                    "Outcome classification reviewer is missing.",
                    "",
                    _record_id_for_row("LHarmoni_Outcomes", row),
                )
            if pd.notna(row.get("Baseline_Date")) and pd.notna(row.get("Enrolment_Date")):
                if row.get("Baseline_Date") < row.get("Enrolment_Date") - pd.Timedelta(days=90):
                    _issue(
                        issues,
                        "Warning",
                        "LHarmoni_Outcomes",
                        row.get("__Source_Row", ""),
                        "Baseline_Date",
                        "Baseline is more than 90 days before enrolment; verify source record.",
                        row.get("Baseline_Date", ""),
                        _record_id_for_row("LHarmoni_Outcomes", row),
                    )
            if pd.notna(row.get("Followup_Date")) and pd.notna(row.get("Baseline_Date")):
                if row.get("Followup_Date") <= row.get("Baseline_Date"):
                    _issue(
                        issues,
                        "Critical",
                        "LHarmoni_Outcomes",
                        row.get("__Source_Row", ""),
                        "Followup_Date",
                        "Follow-up date must be after baseline date.",
                        row.get("Followup_Date", ""),
                        _record_id_for_row("LHarmoni_Outcomes", row),
                    )

    beneficiaries = frames["APRIL_Beneficiaries"]
    if not beneficiaries.empty:
        beneficiaries["Beneficiary_Type_Clean"] = beneficiaries["Beneficiary_Type"].apply(
            lambda x: _clean_text(x).upper()
        )
        allowed = {"AAC CLIENT", "VOLUNTEER", "CAREGIVER"}
        for idx, row in beneficiaries.iterrows():
            if row.get("Beneficiary_Type_Clean") not in allowed:
                _issue(
                    issues,
                    "Critical",
                    "APRIL_Beneficiaries",
                    row.get("__Source_Row", ""),
                    "Beneficiary_Type",
                    "Type must be AAC Client, Volunteer or Caregiver.",
                    row.get("Beneficiary_Type", ""),
                    _record_id_for_row("APRIL_Beneficiaries", row),
                )

    issues_df = pd.DataFrame(issues)
    if issues_df.empty:
        issues_df = pd.DataFrame(
            columns=["Severity", "Sheet", "Source Row", "Record ID", "Field", "Issue", "Original Value"]
        )
    else:
        severity_order = pd.CategoricalDtype(["Critical", "Warning", "Info"], ordered=True)
        issues_df["Severity"] = issues_df["Severity"].astype(severity_order)
        issues_df = issues_df.sort_values(["Severity", "Sheet", "Source Row"], kind="mergesort").reset_index(drop=True)
        issues_df["Severity"] = issues_df["Severity"].astype(str)

    return ValidationBundle(
        frames=frames,
        issues=issues_df,
        source_register=source_register,
        present_sheets=present_sheets,
    )


def _valid_centre_mask(frame: pd.DataFrame, project: str) -> pd.Series:
    if frame.empty or "Centre_Canonical" not in frame.columns:
        return pd.Series(False, index=frame.index, dtype=bool)
    return frame["Centre_Canonical"].isin(PROJECT_CENTRES[project])


def _within_reporting_period(
    series: pd.Series,
    start_date: date | datetime | pd.Timestamp,
    end_date: date | datetime | pd.Timestamp,
) -> pd.Series:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    return series.notna() & series.between(start, end, inclusive="both")


def _assessment_completion_table(
    assessments: pd.DataFrame,
    project: str,
    start_date: date | datetime | pd.Timestamp,
    end_date: date | datetime | pd.Timestamp,
) -> pd.DataFrame:
    if assessments.empty:
        return pd.DataFrame(columns=["Senior_ID", "Centre", "Year", "Complete_Set"])
    temp = assessments.copy()
    mask = (
        temp["Project_Canonical"].eq(project)
        & _valid_centre_mask(temp, project)
        & _within_reporting_period(temp["Assessment_Date"], start_date, end_date)
        & temp["Senior_ID"].apply(_clean_text).ne("")
        & temp["Assessment_Type_Clean"].isin(VALID_ASSESSMENT_TYPES)
    )
    temp = temp.loc[mask].copy()
    if temp.empty:
        return pd.DataFrame(columns=["Senior_ID", "Centre", "Year", "Complete_Set"])
    temp["Year"] = temp["Assessment_Date"].dt.year
    grouped = (
        temp.groupby(["Senior_ID", "Centre_Canonical", "Year"])["Assessment_Type_Clean"]
        .agg(lambda values: sorted(set(values)))
        .reset_index()
        .rename(columns={"Centre_Canonical": "Centre", "Assessment_Type_Clean": "Assessment_Types"})
    )
    grouped["Complete_Set"] = grouped["Assessment_Types"].apply(
        lambda values: VALID_ASSESSMENT_TYPES.issubset(set(values))
    )
    return grouped


def calculate_kpis(
    bundle: ValidationBundle,
    reporting_start: date | datetime | pd.Timestamp,
    reporting_end: date | datetime | pd.Timestamp,
    risk_denominator_mode: str = "Unique seniors",
    followup_min_days: int = 365,
    followup_max_days: int = 365,
) -> KpiBundle:
    frames = bundle.frames
    summary_rows: list[dict[str, Any]] = []
    centre_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    calc: dict[str, Any] = {}

    def sheet_status(sheet_name: str, denominator: int | None = None) -> str:
        if sheet_name not in bundle.present_sheets:
            return "Data unavailable"
        if denominator is not None and denominator == 0:
            return "Not calculable – zero eligible denominator"
        return "Available"

    # APRIL onboarding: unique seniors, once each, within the selected period.
    onboarding = frames["APRIL_Onboarding"].copy()
    if not onboarding.empty:
        valid = onboarding.loc[
            onboarding["Onboarded_Bool"].eq(True)
            & _valid_centre_mask(onboarding, "APRIL")
            & _within_reporting_period(onboarding["Onboarding_Date"], reporting_start, reporting_end)
            & onboarding["Senior_ID"].apply(_clean_text).ne("")
        ].copy()
    else:
        valid = onboarding
    april_onboarded = int(valid["Senior_ID"].nunique()) if not valid.empty else 0
    calc["april_unique_onboarded"] = april_onboarded
    summary_rows.append(
        {
            "Project": "APRIL",
            "KPI": "Unique seniors onboarded",
            "Actual": april_onboarded,
            "Target": OFFICIAL_TARGETS["APRIL"]["unique_seniors_onboarded"],
            "Unit": "Unique seniors",
            "Status": sheet_status("APRIL_Onboarding"),
        }
    )
    for centre in ALL_CENTRES:
        actual = int(valid.loc[valid["Centre_Canonical"].eq(centre), "Senior_ID"].nunique()) if not valid.empty else 0
        centre_rows.append(
            {"Project": "APRIL", "Centre": centre, "KPI": "Unique seniors onboarded", "Actual": actual, "Target": pd.NA}
        )

    # APRIL risk validation: show both unique-senior and flag-level calculations.
    risk = frames["APRIL_Risk_Flags"].copy()
    if not risk.empty:
        reviewed = risk.loc[
            risk["Reviewed_Bool"].eq(True)
            & _valid_centre_mask(risk, "APRIL")
            & _within_reporting_period(risk["Flag_Date"], reporting_start, reporting_end)
            & risk["Senior_ID"].apply(_clean_text).ne("")
            & risk["Validation_Clean"].isin({"VALIDATED", "NOT VALIDATED"})
        ].copy()
    else:
        reviewed = risk
    flag_den = int(len(reviewed)) if not reviewed.empty else 0
    flag_num = int(reviewed["Validation_Clean"].eq("VALIDATED").sum()) if not reviewed.empty else 0
    flag_rate = flag_num / flag_den if flag_den else np.nan
    senior_den = int(reviewed["Senior_ID"].nunique()) if not reviewed.empty else 0
    senior_num = int(
        reviewed.loc[reviewed["Validation_Clean"].eq("VALIDATED"), "Senior_ID"].nunique()
    ) if not reviewed.empty else 0
    senior_rate = senior_num / senior_den if senior_den else np.nan
    use_seniors = risk_denominator_mode.strip().lower().startswith("unique")
    risk_num = senior_num if use_seniors else flag_num
    risk_den = senior_den if use_seniors else flag_den
    risk_rate = senior_rate if use_seniors else flag_rate
    calc.update(
        {
            "april_risk_mode": risk_denominator_mode,
            "april_risk_numerator": risk_num,
            "april_risk_denominator": risk_den,
            "april_risk_rate": risk_rate,
            "april_risk_unique_senior_numerator": senior_num,
            "april_risk_unique_senior_denominator": senior_den,
            "april_risk_flag_numerator": flag_num,
            "april_risk_flag_denominator": flag_den,
            "april_risk_rate_unique_seniors": senior_rate,
            "april_risk_rate_flags": flag_rate,
        }
    )
    summary_rows.append(
        {
            "Project": "APRIL",
            "KPI": f"Risk validation rate ({risk_denominator_mode})",
            "Actual": risk_rate,
            "Target": OFFICIAL_TARGETS["APRIL"]["risk_validation_rate"],
            "Unit": "Percentage",
            "Status": sheet_status("APRIL_Risk_Flags", risk_den),
        }
    )
    for centre in ALL_CENTRES:
        c = reviewed.loc[reviewed["Centre_Canonical"].eq(centre)].copy() if not reviewed.empty else reviewed
        if use_seniors:
            den = int(c["Senior_ID"].nunique()) if not c.empty else 0
            num = int(c.loc[c["Validation_Clean"].eq("VALIDATED"), "Senior_ID"].nunique()) if not c.empty else 0
        else:
            den = int(len(c)) if not c.empty else 0
            num = int(c["Validation_Clean"].eq("VALIDATED").sum()) if not c.empty else 0
        centre_rows.append(
            {
                "Project": "APRIL",
                "Centre": centre,
                "KPI": f"Risk validation rate ({risk_denominator_mode})",
                "Actual": num / den if den else np.nan,
                "Target": OFFICIAL_TARGETS["APRIL"]["risk_validation_rate"],
                "Numerator": num,
                "Denominator": den,
            }
        )

    # Assessment completion for both projects. The CST target is annual, so
    # every calendar year in the selected reporting period is shown separately.
    assessments = frames["Assessments"]
    reporting_years = list(range(pd.Timestamp(reporting_start).year, pd.Timestamp(reporting_end).year + 1))
    for project in ["APRIL", "L'Harmoni"]:
        completion = _assessment_completion_table(
            assessments, project, reporting_start, reporting_end
        )
        complete = completion.loc[completion["Complete_Set"].eq(True)].copy()
        annual_counts = complete.groupby("Year")["Senior_ID"].nunique() if not complete.empty else pd.Series(dtype=int)
        annual_count_map = {year: int(annual_counts.get(year, 0)) for year in reporting_years}
        three_year_unique = int(complete["Senior_ID"].nunique()) if not complete.empty else 0
        calc[f"{project}_annual_complete_assessment_sets"] = annual_count_map
        calc[f"{project}_three_year_unique_tracked"] = three_year_unique

        for year in reporting_years:
            summary_rows.append(
                {
                    "Project": project,
                    "KPI": f"Complete MMSE/GDS/SPPB sets in {year}",
                    "Actual": annual_count_map[year],
                    "Target": OFFICIAL_TARGETS[project]["annual_complete_assessment_sets"],
                    "Unit": "Unique seniors",
                    "Status": sheet_status("Assessments"),
                }
            )

        summary_rows.append(
            {
                "Project": project,
                "KPI": "Unique seniors with complete assessment set in reporting period",
                "Actual": three_year_unique,
                "Target": OFFICIAL_TARGETS[project]["three_year_unique_tracked_seniors"],
                "Unit": "Unique seniors",
                "Status": sheet_status("Assessments"),
            }
        )

        applicable_centres = ALL_CENTRES if project == "APRIL" else sorted(PROJECT_CENTRES[project])
        for centre in applicable_centres:
            c = complete.loc[complete["Centre"].eq(centre)] if not complete.empty else complete
            for year in reporting_years:
                centre_rows.append(
                    {
                        "Project": project,
                        "Centre": centre,
                        "KPI": f"Complete MMSE/GDS/SPPB sets in {year}",
                        "Actual": int(c.loc[c["Year"].eq(year), "Senior_ID"].nunique()) if not c.empty else 0,
                        "Target": pd.NA,
                    }
                )
        if not completion.empty:
            for _, row in completion.iterrows():
                detail_rows.append(
                    {
                        "Project": project,
                        "KPI": "Assessment set completion",
                        "Record ID": row["Senior_ID"],
                        "Centre": row["Centre"],
                        "Year": int(row["Year"]),
                        "Result": "Complete" if row["Complete_Set"] else "Incomplete",
                        "Calculation Detail": ", ".join(row["Assessment_Types"]),
                    }
                )

    # APRIL beneficiary-table counts are annual and remain separate from onboarding.
    beneficiaries = frames["APRIL_Beneficiaries"].copy()
    if not beneficiaries.empty:
        valid_b = beneficiaries.loc[
            _valid_centre_mask(beneficiaries, "APRIL")
            & _within_reporting_period(beneficiaries["Engagement_Date"], reporting_start, reporting_end)
            & beneficiaries["Beneficiary_ID"].apply(_clean_text).ne("")
            & beneficiaries["Beneficiary_Type_Clean"].isin({"AAC CLIENT", "VOLUNTEER", "CAREGIVER"})
        ].copy()
        valid_b["Year"] = valid_b["Engagement_Date"].dt.year
    else:
        valid_b = beneficiaries
    beneficiary_map = {
        "AAC CLIENT": ("AAC clients reached", "annual_aac_clients"),
        "VOLUNTEER": ("Volunteers reached", "annual_volunteers"),
        "CAREGIVER": ("Caregivers reached", "annual_caregivers"),
    }
    beneficiary_counts: dict[str, dict[int, int]] = {}
    for b_type, (label, target_key) in beneficiary_map.items():
        beneficiary_counts[b_type] = {}
        for year in reporting_years:
            if valid_b.empty:
                actual = 0
            else:
                actual = int(
                    valid_b.loc[
                        valid_b["Beneficiary_Type_Clean"].eq(b_type) & valid_b["Year"].eq(year),
                        "Beneficiary_ID",
                    ].nunique()
                )
            beneficiary_counts[b_type][year] = actual
            summary_rows.append(
                {
                    "Project": "APRIL",
                    "KPI": f"{label} in {year}",
                    "Actual": actual,
                    "Target": OFFICIAL_TARGETS["APRIL"][target_key],
                    "Unit": "Unique beneficiaries",
                    "Status": sheet_status("APRIL_Beneficiaries"),
                }
            )
    calc["april_annual_beneficiary_counts"] = beneficiary_counts

    # L'Harmoni enrolment: unique participants, with fixed operational centre mapping.
    enrolment = frames["LHarmoni_Enrolment"].copy()
    if not enrolment.empty:
        valid_e = enrolment.loc[
            _valid_centre_mask(enrolment, "L'Harmoni")
            & _within_reporting_period(enrolment["Enrolment_Date"], reporting_start, reporting_end)
            & enrolment["Senior_ID"].apply(_clean_text).ne("")
        ].copy()
    else:
        valid_e = enrolment
    total_participants = int(valid_e["Senior_ID"].nunique()) if not valid_e.empty else 0
    calc["lharmoni_unique_participants"] = total_participants
    summary_rows.append(
        {
            "Project": "L'Harmoni",
            "KPI": "Unique participating seniors",
            "Actual": total_participants,
            "Target": OFFICIAL_TARGETS["L'Harmoni"]["total_unique_participants"],
            "Unit": "Unique seniors",
            "Status": sheet_status("LHarmoni_Enrolment"),
        }
    )
    for centre, target in OFFICIAL_TARGETS["L'Harmoni"]["centre_targets"].items():
        actual = int(valid_e.loc[valid_e["Centre_Canonical"].eq(centre), "Senior_ID"].nunique()) if not valid_e.empty else 0
        centre_rows.append(
            {
                "Project": "L'Harmoni",
                "Centre": centre,
                "KPI": "Unique participating seniors",
                "Actual": actual,
                "Target": target,
            }
        )

    # L'Harmoni official outcome rate. Classifications are supplied and approved;
    # this code does not interpret raw clinical scores.
    outcomes = frames["LHarmoni_Outcomes"].copy()
    if not outcomes.empty:
        measurable_outcomes = {"IMPROVED", "MAINTAINED", "DECLINED", "NO CHANGE", "MIXED"}
        has_measurable_domain = (
            outcomes["Physical_Outcome_Clean"].isin(measurable_outcomes)
            | outcomes["Cognitive_Outcome_Clean"].isin(measurable_outcomes)
        )
        eligible = outcomes.loc[
            _valid_centre_mask(outcomes, "L'Harmoni")
            & outcomes["Outcome_Approved_Bool"].eq(True)
            & outcomes["Senior_ID"].apply(_clean_text).ne("")
            & _within_reporting_period(outcomes["Followup_Date"], reporting_start, reporting_end)
            & outcomes["Followup_Days"].between(followup_min_days, followup_max_days, inclusive="both")
            & outcomes["Physical_Outcome_Clean"].isin(VALID_OUTCOMES)
            & outcomes["Cognitive_Outcome_Clean"].isin(VALID_OUTCOMES)
            & has_measurable_domain
        ].copy()
    else:
        eligible = outcomes
    if not eligible.empty:
        eligible["Qualifies"] = (
            eligible["Physical_Outcome_Clean"].isin({"IMPROVED", "MAINTAINED"})
            | eligible["Cognitive_Outcome_Clean"].isin({"IMPROVED", "MAINTAINED"})
        )
        # One official outcome per senior. Duplicate Senior_IDs remain a critical
        # data-quality issue; this grouping prevents double-counting while still
        # leaving duplicates visible in the exception log.
        senior_outcome = (
            eligible.groupby(["Senior_ID", "Centre_Canonical"], as_index=False)
            .agg(Qualifies=("Qualifies", "max"), Followup_Days=("Followup_Days", "max"))
        )
    else:
        senior_outcome = pd.DataFrame(columns=["Senior_ID", "Centre_Canonical", "Qualifies", "Followup_Days"])
    outcome_den = int(senior_outcome["Senior_ID"].nunique()) if not senior_outcome.empty else 0
    outcome_num = int(senior_outcome.loc[senior_outcome["Qualifies"].eq(True), "Senior_ID"].nunique()) if not senior_outcome.empty else 0
    outcome_rate = outcome_num / outcome_den if outcome_den else np.nan
    calc.update(
        {
            "lharmoni_outcome_numerator": outcome_num,
            "lharmoni_outcome_denominator": outcome_den,
            "lharmoni_outcome_rate": outcome_rate,
            "lharmoni_followup_min_days": int(followup_min_days),
            "lharmoni_followup_max_days": int(followup_max_days),
        }
    )
    summary_rows.append(
        {
            "Project": "L'Harmoni",
            "KPI": "Improved or maintained physical and/or cognitive wellbeing",
            "Actual": outcome_rate,
            "Target": OFFICIAL_TARGETS["L'Harmoni"]["improved_or_maintained_rate"],
            "Unit": "Percentage",
            "Status": sheet_status("LHarmoni_Outcomes", outcome_den),
            "Numerator": outcome_num,
            "Denominator": outcome_den,
        }
    )
    for centre in sorted(PROJECT_CENTRES["L'Harmoni"]):
        c = senior_outcome.loc[senior_outcome["Centre_Canonical"].eq(centre)] if not senior_outcome.empty else senior_outcome
        den = int(c["Senior_ID"].nunique()) if not c.empty else 0
        num = int(c.loc[c["Qualifies"].eq(True), "Senior_ID"].nunique()) if not c.empty else 0
        centre_rows.append(
            {
                "Project": "L'Harmoni",
                "Centre": centre,
                "KPI": "Improved or maintained physical and/or cognitive wellbeing",
                "Actual": num / den if den else np.nan,
                "Target": OFFICIAL_TARGETS["L'Harmoni"]["improved_or_maintained_rate"],
                "Numerator": num,
                "Denominator": den,
            }
        )
    if not senior_outcome.empty:
        for _, row in senior_outcome.iterrows():
            detail_rows.append(
                {
                    "Project": "L'Harmoni",
                    "KPI": "One-year outcome",
                    "Record ID": row["Senior_ID"],
                    "Centre": row["Centre_Canonical"],
                    "Year": pd.NA,
                    "Result": "Qualifies" if row["Qualifies"] else "Does not qualify",
                    "Calculation Detail": f"Follow-up {int(row['Followup_Days'])} days after enrolment",
                }
            )

    summary = pd.DataFrame(summary_rows)
    centre_breakdown = pd.DataFrame(centre_rows)
    detail = pd.DataFrame(detail_rows)
    return KpiBundle(summary=summary, centre_breakdown=centre_breakdown, detail=detail, calculations=calc)


def official_export_blockers(
    validation: ValidationBundle,
    kpis: KpiBundle | None,
    mapping_approved: bool,
    mapping_approver: str,
    mapping_reference: str,
    risk_definition_approved: bool,
    followup_rule_approved: bool,
    followup_rule_version: str,
    reporting_start: date | datetime | pd.Timestamp,
    reporting_end: date | datetime | pd.Timestamp,
) -> list[str]:
    blockers: list[str] = []
    if validation.critical_count:
        blockers.append(f"{validation.critical_count} critical data-quality issue(s) remain unresolved.")
    if kpis is not None and not kpis.summary.empty:
        unavailable = kpis.summary[kpis.summary["Status"].eq("Data unavailable")]
        if not unavailable.empty:
            missing_labels = ", ".join(
                unavailable.apply(lambda r: f"{r['Project']}: {r['KPI']}", axis=1).tolist()
            )
            blockers.append(f"Required KPI source data is unavailable for: {missing_labels}.")
    if not mapping_approved:
        blockers.append("Operational centre mapping has not been formally approved.")
    if mapping_approved and not _clean_text(mapping_approver):
        blockers.append("Centre-mapping approver name is missing.")
    if mapping_approved and not _clean_text(mapping_reference):
        blockers.append("Centre-mapping approval reference is missing.")
    if not risk_definition_approved:
        blockers.append("APRIL risk-validation denominator definition has not been approved.")
    if not followup_rule_approved:
        blockers.append("L'Harmoni follow-up window and outcome rule have not been approved.")
    if followup_rule_approved and not _clean_text(followup_rule_version):
        blockers.append("L'Harmoni approved outcome rule version is missing.")
    if pd.Timestamp(reporting_start) > pd.Timestamp(reporting_end):
        blockers.append("Reporting-period start date is after end date.")
    return blockers


def build_export_workbook(
    validation: ValidationBundle,
    kpis: KpiBundle,
    reporting_start: date | datetime | pd.Timestamp,
    reporting_end: date | datetime | pd.Timestamp,
    prepared_by: str,
    reviewed_by: str,
    mapping_approver: str,
    mapping_reference: str,
    risk_denominator_mode: str,
    followup_min_days: int,
    followup_max_days: int,
    followup_rule_version: str,
    official_status: str,
) -> bytes:
    """Create a traceable multi-sheet Excel export in memory."""
    metadata = pd.DataFrame(
        [
            ["Official reporting status", official_status],
            ["Reporting period start", pd.Timestamp(reporting_start).date().isoformat()],
            ["Reporting period end", pd.Timestamp(reporting_end).date().isoformat()],
            ["Prepared by", _clean_text(prepared_by)],
            ["Reviewed by", _clean_text(reviewed_by)],
            ["Centre mapping approved by", _clean_text(mapping_approver)],
            ["Centre mapping approval reference", _clean_text(mapping_reference)],
            ["APRIL risk denominator", risk_denominator_mode],
            ["L'Harmoni follow-up minimum days", int(followup_min_days)],
            ["L'Harmoni follow-up maximum days", int(followup_max_days)],
            ["L'Harmoni outcome rule version", _clean_text(followup_rule_version)],
            ["Generated at", pd.Timestamp.now().isoformat()],
            ["APRIL source note", SOURCE_NOTES["APRIL"]],
            ["L'Harmoni source note", SOURCE_NOTES["L'Harmoni"]],
            ["Centre-mapping note", SOURCE_NOTES["CENTRE_MAPPING"]],
        ],
        columns=["Field", "Value"],
    )

    definitions = pd.DataFrame(
        [
            ["APRIL", "Unique seniors onboarded", "Distinct Senior_ID with Onboarded=Yes, valid date and approved APRIL centre.", 1000],
            ["APRIL", "Risk validation rate", f"Approved calculation mode: {risk_denominator_mode}.", "80%"],
            ["APRIL", "Annual complete assessment sets", "Distinct seniors with MMSE, GDS and SPPB, reported separately for every calendar year in the selected period.", 100],
            ["APRIL", "Three-year unique tracked seniors", "Distinct seniors with at least one complete MMSE/GDS/SPPB set in the selected project reporting period.", 300],
            ["APRIL", "Annual AAC clients", "Separate beneficiary-table measure; distinct AAC Client Beneficiary_ID reported for every calendar year and not combined with onboarding.", 1000],
            ["APRIL", "Annual volunteers", "Distinct Volunteer Beneficiary_ID, reported separately for every calendar year in the selected period.", 100],
            ["APRIL", "Annual caregivers", "Distinct Caregiver Beneficiary_ID, reported separately for every calendar year in the selected period.", 200],
            ["L'Harmoni", "Unique participating seniors", "Distinct Senior_ID recorded as participating/enrolled at the two approved GLOW centres within the selected period.", 1000],
            ["L'Harmoni", "Centre participation", "Distinct Senior_ID by approved GLOW centre.", "500 each"],
            ["L'Harmoni", "Improved/maintained rate", "Approved physical or cognitive classification is Improved or Maintained, among eligible approved one-year outcomes.", "60%"],
            ["L'Harmoni", "Annual complete assessment sets", "Distinct seniors with MMSE, GDS and SPPB, reported separately for every calendar year in the selected period.", 100],
            ["L'Harmoni", "Three-year unique tracked seniors", "Distinct seniors with at least one complete MMSE/GDS/SPPB set in the selected project reporting period.", 300],
        ],
        columns=["Project", "KPI", "Definition", "Target"],
    )

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="Submission_Metadata", index=False)
        kpis.summary.to_excel(writer, sheet_name="AIC_KPI_Summary", index=False)
        kpis.centre_breakdown.to_excel(writer, sheet_name="Centre_Breakdown", index=False)
        kpis.detail.to_excel(writer, sheet_name="Calculation_Detail", index=False)
        validation.issues.to_excel(writer, sheet_name="Exceptions", index=False)
        validation.source_register.to_excel(writer, sheet_name="Source_Register", index=False)
        definitions.to_excel(writer, sheet_name="KPI_Definitions", index=False)

        # Basic readable formatting without altering values or formulas.
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True, color="FFFFFF")
                cell.fill = cell.fill.copy(fill_type="solid", fgColor="0D2B45")
            for col_cells in ws.columns:
                values = [str(c.value) if c.value is not None else "" for c in col_cells[:100]]
                width = min(max(max((len(v) for v in values), default=0) + 2, 12), 48)
                ws.column_dimensions[col_cells[0].column_letter].width = width
                for cell in col_cells:
                    cell.alignment = cell.alignment.copy(wrap_text=True, vertical="top")

    return output.getvalue()


def format_metric(value: Any, unit: str) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    if unit == "Percentage":
        return f"{float(value):.1%}"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):,.1f}"
    return str(value)


def progress_ratio(actual: Any, target: Any) -> float | None:
    try:
        if pd.isna(actual) or pd.isna(target) or float(target) == 0:
            return None
        return max(0.0, float(actual) / float(target))
    except Exception:
        return None
