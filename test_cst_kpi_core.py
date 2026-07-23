from datetime import date
from pathlib import Path

import pandas as pd

from cst_kpi_core import calculate_kpis, official_export_blockers, read_project_workbook, validate_workbook


def _base_frames():
    return {
        "APRIL_Onboarding": pd.DataFrame(
            [
                {"Senior_ID": "S1", "Centre": "GLOW Bukit Batok", "Onboarding_Date": "2026-01-10", "Onboarded": "Yes", "Source_Record_ID": "A1", "__Source_Row": 2},
                {"Senior_ID": "S2", "Centre": "SEEN Nanyang", "Onboarding_Date": "2026-02-10", "Onboarded": "Yes", "Source_Record_ID": "A2", "__Source_Row": 3},
            ]
        ),
        "APRIL_Risk_Flags": pd.DataFrame(
            [
                {"Risk_Flag_ID": "R1", "Senior_ID": "S1", "Centre": "GLOW Bukit Batok", "Flag_Date": "2026-03-01", "Reviewed_By_Staff": "Yes", "Validation_Outcome": "Validated", "Reviewer": "Reviewer A", "__Source_Row": 2},
                {"Risk_Flag_ID": "R2", "Senior_ID": "S2", "Centre": "SEEN Nanyang", "Flag_Date": "2026-03-02", "Reviewed_By_Staff": "Yes", "Validation_Outcome": "Not Validated", "Reviewer": "Reviewer A", "__Source_Row": 3},
            ]
        ),
        "Assessments": pd.DataFrame(
            [
                {"Assessment_Record_ID": f"AS{i}", "Senior_ID": "S1", "Centre": "GLOW Bukit Batok", "Project": "APRIL", "Assessment_Type": kind, "Assessment_Date": "2026-04-01", "Assessment_Point": "Annual", "__Source_Row": i + 2}
                for i, kind in enumerate(["MMSE", "GDS", "SPPB"])
            ]
            + [
                {"Assessment_Record_ID": f"LS{i}", "Senior_ID": "L1", "Centre": "GLOW Nanyang", "Project": "L'Harmoni", "Assessment_Type": kind, "Assessment_Date": "2026-04-01", "Assessment_Point": "Annual", "__Source_Row": i + 5}
                for i, kind in enumerate(["MMSE", "GDS", "SPPB"])
            ]
        ),
        "LHarmoni_Enrolment": pd.DataFrame(
            [
                {"Senior_ID": "L1", "Centre": "GLOW Nanyang", "Enrolment_Date": "2025-01-01", "Active_Status": "Yes", "Source_Record_ID": "LHE1", "__Source_Row": 2}
            ]
        ),
        "LHarmoni_Outcomes": pd.DataFrame(
            [
                {"Outcome_Record_ID": "O1", "Senior_ID": "L1", "Centre": "GLOW Nanyang", "Enrolment_Date": "2025-01-01", "Baseline_Date": "2025-01-01", "Followup_Date": "2026-01-01", "Physical_Outcome": "Maintained", "Cognitive_Outcome": "Declined", "Outcome_Approved": "Yes", "Rule_Version": "LH-v1", "Reviewer": "Reviewer B", "__Source_Row": 2}
            ]
        ),
        "APRIL_Beneficiaries": pd.DataFrame(
            [
                {"Beneficiary_Record_ID": "B1", "Beneficiary_ID": "V1", "Beneficiary_Type": "Volunteer", "Centre": "GLOW Bukit Batok", "Engagement_Date": "2026-06-01", "__Source_Row": 2}
            ]
        ),
    }


def test_clean_workbook_and_kpis():
    raw = _base_frames()
    source_register = pd.DataFrame([{"Source File": "test.xlsx", "Original Sheet": "x", "Recognised Sheet": "x", "Rows Read": 1}])
    validation = validate_workbook(raw, source_register)
    assert validation.critical_count == 0
    result = calculate_kpis(
        validation,
        reporting_start=date(2025, 1, 1),
        reporting_end=date(2026, 12, 31),
        risk_denominator_mode="Unique seniors",
        followup_min_days=365,
        followup_max_days=365,
    )
    assert result.calculations["april_unique_onboarded"] == 2
    assert result.calculations["april_risk_rate"] == 0.5
    assert result.calculations["lharmoni_unique_participants"] == 1
    assert result.calculations["lharmoni_outcome_rate"] == 1.0


def test_seen_lharmoni_is_critical():
    raw = _base_frames()
    raw["LHarmoni_Enrolment"].loc[0, "Centre"] = "SEEN Nanyang"
    validation = validate_workbook(raw, pd.DataFrame())
    assert validation.critical_count >= 1
    assert validation.issues["Issue"].str.contains("non-GLOW", case=False).any()


def test_official_export_blockers_require_approvals():
    validation = validate_workbook(_base_frames(), pd.DataFrame())
    result = calculate_kpis(
        validation,
        reporting_start=date(2026, 1, 1),
        reporting_end=date(2026, 12, 31),
    )
    blockers = official_export_blockers(
        validation=validation,
        kpis=result,
        mapping_approved=False,
        mapping_approver="",
        mapping_reference="",
        risk_definition_approved=False,
        followup_rule_approved=False,
        followup_rule_version="",
        reporting_start=date(2026, 1, 1),
        reporting_end=date(2026, 12, 31),
    )
    assert len(blockers) >= 3


def test_missing_required_kpi_sheet_blocks_official_export():
    raw = _base_frames()
    raw.pop("APRIL_Beneficiaries")
    validation = validate_workbook(raw, pd.DataFrame())
    result = calculate_kpis(
        validation,
        reporting_start=date(2026, 1, 1),
        reporting_end=date(2026, 12, 31),
    )
    blockers = official_export_blockers(
        validation=validation,
        kpis=result,
        mapping_approved=True,
        mapping_approver="Project Owner",
        mapping_reference="Approval email 2026-07-23",
        risk_definition_approved=True,
        followup_rule_approved=True,
        followup_rule_version="LH-v1",
        reporting_start=date(2026, 1, 1),
        reporting_end=date(2026, 12, 31),
    )
    assert any("source data is unavailable" in blocker.lower() for blocker in blockers)


def test_annual_targets_are_not_combined_across_years():
    raw = _base_frames()
    raw["APRIL_Beneficiaries"] = pd.DataFrame(
        [
            {"Beneficiary_Record_ID": "B1", "Beneficiary_ID": "V1", "Beneficiary_Type": "Volunteer", "Centre": "GLOW Bukit Batok", "Engagement_Date": "2025-06-01", "__Source_Row": 2},
            {"Beneficiary_Record_ID": "B2", "Beneficiary_ID": "V1", "Beneficiary_Type": "Volunteer", "Centre": "GLOW Bukit Batok", "Engagement_Date": "2026-06-01", "__Source_Row": 3},
        ]
    )
    validation = validate_workbook(raw, pd.DataFrame())
    result = calculate_kpis(validation, date(2025, 1, 1), date(2026, 12, 31))
    volunteer_rows = result.summary[result.summary["KPI"].str.contains("Volunteers reached")].copy()
    assert volunteer_rows.set_index("KPI")["Actual"].to_dict() == {
        "Volunteers reached in 2025": 1,
        "Volunteers reached in 2026": 1,
    }
    assessment_rows = result.summary[result.summary["KPI"].str.contains("Complete MMSE/GDS/SPPB sets in")].copy()
    assert {2025, 2026}.issubset({int(label.rsplit(" ", 1)[-1]) for label in assessment_rows["KPI"]})


def test_lharmoni_outcome_uses_followup_reporting_date_and_measurable_domain():
    raw = _base_frames()
    raw["LHarmoni_Outcomes"].loc[0, "Physical_Outcome"] = "Insufficient Data"
    raw["LHarmoni_Outcomes"].loc[0, "Cognitive_Outcome"] = "Not Assessed"
    validation = validate_workbook(raw, pd.DataFrame())
    result = calculate_kpis(
        validation,
        reporting_start=date(2026, 1, 1),
        reporting_end=date(2026, 12, 31),
        followup_min_days=365,
        followup_max_days=365,
    )
    assert result.calculations["lharmoni_outcome_denominator"] == 0
    assert validation.issues["Issue"].str.contains("measurable approved outcome", case=False).any()


def test_controlled_template_headers_are_detected_below_title_rows():
    template = Path(__file__).resolve().parents[1] / "templates" / "CST_KPI_Data_Template.xlsx"
    raw, source_register = read_project_workbook(template)
    validation = validate_workbook(raw, source_register)
    assert validation.critical_count == 0
    assert validation.present_sheets == {
        "APRIL_Onboarding",
        "APRIL_Risk_Flags",
        "Assessments",
        "LHarmoni_Enrolment",
        "LHarmoni_Outcomes",
        "APRIL_Beneficiaries",
    }
