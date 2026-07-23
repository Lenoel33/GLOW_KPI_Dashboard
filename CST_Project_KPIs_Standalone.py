"""Streamlit page for Project APRIL and L'Harmoni CST/AIC KPI monitoring."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

PAGE_DIR = Path(__file__).resolve().parent
APP_DIR = PAGE_DIR.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from cst_kpi_core import (  # noqa: E402
    ALL_CENTRES,
    OFFICIAL_TARGETS,
    PROJECT_CENTRES,
    SOURCE_NOTES,
    build_export_workbook,
    calculate_kpis,
    format_metric,
    official_export_blockers,
    progress_ratio,
    read_project_workbook,
    validate_workbook,
)

st.set_page_config(page_title="CST Project KPI Progress", page_icon="✅", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(180deg, #F7F1E7 0%, #FFFDF8 52%, #F7F1E7 100%); }
    .main .block-container { padding-top: 1.25rem; padding-bottom: 3rem; }
    .cst-hero {
        background: linear-gradient(135deg, #0D2B45 0%, #164766 62%, #6F9CA3 100%);
        color: white; padding: 26px 30px; border-radius: 22px; margin-bottom: 16px;
        box-shadow: 0 10px 28px rgba(13, 43, 69, 0.20);
    }
    .cst-hero h1 { margin: 0; font-size: 2rem; }
    .cst-hero p { color: #F3E8D2; margin: 8px 0 0 0; }
    .audit-box {
        border: 1px solid #E9D6B3; border-radius: 16px; padding: 16px 18px;
        background: #FFFFFF; box-shadow: 0 4px 14px rgba(13,43,69,0.06);
    }
    .status-pass { border-left: 7px solid #2E7D32; }
    .status-block { border-left: 7px solid #C62828; }
    .source-note { color: #55623B; font-size: .91rem; line-height: 1.45; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="cst-hero">
      <h1>✅ CST Project KPI Progress</h1>
      <p>Auditable tracking for Project APRIL across four centres and L'Harmoni across the two GLOW centres.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.warning(
    "Official AIC export is blocked until critical data issues are resolved and the centre mapping, "
    "APRIL risk-validation definition, and L'Harmoni outcome rule are formally approved."
)

TEMPLATE_PATH = APP_DIR / "templates" / "CST_KPI_Data_Template.xlsx"
if TEMPLATE_PATH.exists():
    st.download_button(
        "Download controlled KPI data template",
        data=TEMPLATE_PATH.read_bytes(),
        file_name="CST_KPI_Data_Template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
else:
    st.error("Template file is missing from templates/CST_KPI_Data_Template.xlsx.")

def assigned_target_reference() -> pd.DataFrame:
    """Return the submitted project indicators even before actual data is uploaded."""
    rows = [
        {
            "Project": "APRIL",
            "KPI": "Unique seniors onboarded onto APRIL tools",
            "Target": 1000,
            "Target display": "1,000 seniors",
            "Applicable centres": "All 4 centres",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "APRIL",
            "KPI": "At-risk seniors validated by staff assessment",
            "Target": 0.80,
            "Target display": "80%",
            "Applicable centres": "All 4 centres",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "APRIL",
            "KPI": "Complete annual MMSE, GDS and SPPB assessment sets",
            "Target": 100,
            "Target display": "100 seniors per year",
            "Applicable centres": "All 4 centres",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "APRIL",
            "KPI": "Unique seniors tracked across three years",
            "Target": 300,
            "Target display": "300 unique seniors",
            "Applicable centres": "All 4 centres",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "APRIL",
            "KPI": "AAC clients reached",
            "Target": 1000,
            "Target display": "1,000 annually",
            "Applicable centres": "All 4 centres",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "APRIL",
            "KPI": "Volunteers reached",
            "Target": 100,
            "Target display": "100 annually",
            "Applicable centres": "All 4 centres",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "APRIL",
            "KPI": "Caregivers reached",
            "Target": 200,
            "Target display": "200 annually",
            "Applicable centres": "All 4 centres",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "L'Harmoni",
            "KPI": "Unique participating seniors",
            "Target": 1000,
            "Target display": "1,000 seniors",
            "Applicable centres": "GLOW Bukit Batok and GLOW Nanyang",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "L'Harmoni",
            "KPI": "GLOW Bukit Batok participation",
            "Target": 500,
            "Target display": "500 seniors",
            "Applicable centres": "GLOW Bukit Batok",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "L'Harmoni",
            "KPI": "GLOW Nanyang participation",
            "Target": 500,
            "Target display": "500 seniors",
            "Applicable centres": "GLOW Nanyang",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "L'Harmoni",
            "KPI": "Improved or maintained physical and/or cognitive wellbeing",
            "Target": 0.60,
            "Target display": "60% at approved one-year follow-up",
            "Applicable centres": "GLOW Bukit Batok and GLOW Nanyang",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "L'Harmoni",
            "KPI": "Complete annual MMSE, GDS and SPPB assessment sets",
            "Target": 100,
            "Target display": "100 seniors per year",
            "Applicable centres": "GLOW Bukit Batok and GLOW Nanyang",
            "Current result": "Data not uploaded",
        },
        {
            "Project": "L'Harmoni",
            "KPI": "Unique seniors tracked across three years",
            "Target": 300,
            "Target display": "300 unique seniors",
            "Applicable centres": "GLOW Bukit Batok and GLOW Nanyang",
            "Current result": "Data not uploaded",
        },
    ]
    return pd.DataFrame(rows)


st.markdown("## Assigned CST/AIC KPI targets")
st.caption(
    "These assigned KPI names and targets are always shown. Actual results remain marked as data not uploaded until a valid controlled workbook is provided."
)
_target_reference = assigned_target_reference()

_target_cards = [
    ("APRIL onboarded", "1,000"),
    ("APRIL risk validation", "80%"),
    ("L'Harmoni participants", "1,000"),
    ("L'Harmoni outcome", "60%"),
]
_cols = st.columns(4)
for _col, (_label, _value) in zip(_cols, _target_cards):
    with _col:
        st.metric(_label, _value, delta="Assigned target")

st.dataframe(
    _target_reference[["Project", "KPI", "Target display", "Applicable centres", "Current result"]],
    use_container_width=True,
    hide_index=True,
)

st.info(
    "The normal attendance workbooks cannot by themselves prove APRIL onboarding, APRIL risk validation, "
    "L'Harmoni enrolment or one-year outcomes. Use the controlled template so unsupported values are not inferred."
)

with st.expander("KPI source and centre applicability", expanded=False):
    mapping = pd.DataFrame(
        [
            {
                "Centre": centre,
                "APRIL": "Applicable" if centre in PROJECT_CENTRES["APRIL"] else "Not applicable",
                "L'Harmoni": "Applicable" if centre in PROJECT_CENTRES["L'Harmoni"] else "Not applicable",
            }
            for centre in ALL_CENTRES
        ]
    )
    st.dataframe(mapping, use_container_width=True, hide_index=True)
    st.markdown(f"<div class='source-note'><b>APRIL:</b> {SOURCE_NOTES['APRIL']}</div>", unsafe_allow_html=True)
    lharmoni_source_note = SOURCE_NOTES["L'Harmoni"]
    st.markdown(f"<div class='source-note'><b>L'Harmoni:</b> {lharmoni_source_note}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='source-note'><b>Mapping control:</b> {SOURCE_NOTES['CENTRE_MAPPING']}</div>", unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Upload the controlled CST KPI workbook",
    type=["xlsx"],
    accept_multiple_files=False,
    help="Use the downloadable template. The page does not save names, IDs or uploaded files after the Streamlit session ends.",
)

st.markdown("## Reporting configuration")
config_left, config_right = st.columns(2)
with config_left:
    reporting_start = st.date_input("Reporting period start", value=pd.Timestamp("2025-01-01").date())
    reporting_end = st.date_input("Reporting period end", value=pd.Timestamp.today().date())
    risk_denominator_mode = st.selectbox(
        "APRIL risk-validation denominator",
        ["Unique seniors", "Risk flags"],
        help=(
            "The application wording refers to at-risk seniors, so Unique seniors is the conservative default. "
            "Use Risk flags only if formally approved."
        ),
    )
    risk_definition_approved = st.checkbox(
        "APRIL risk-validation definition has written approval",
        value=False,
    )
with config_right:
    followup_min_days = st.number_input(
        "L'Harmoni minimum follow-up days",
        min_value=1,
        max_value=730,
        value=365,
        step=1,
    )
    followup_max_days = st.number_input(
        "L'Harmoni maximum follow-up days",
        min_value=1,
        max_value=730,
        value=365,
        step=1,
    )
    followup_rule_version = st.text_input(
        "Approved L'Harmoni outcome-rule version",
        placeholder="Example: LH-OUTCOME-v1.0",
    )
    followup_rule_approved = st.checkbox(
        "Follow-up window and outcome-classification rule have written approval",
        value=False,
    )

st.markdown("### Centre-mapping approval")
map1, map2, map3 = st.columns(3)
with map1:
    mapping_approved = st.checkbox(
        "APRIL four-centre and L'Harmoni two-GLOW-centre mapping approved",
        value=False,
    )
with map2:
    mapping_approver = st.text_input("Mapping approved by", placeholder="Name and designation")
with map3:
    mapping_reference = st.text_input("Approval reference", placeholder="Email date, memo or approval ID")

st.markdown("### Submission ownership")
own1, own2 = st.columns(2)
with own1:
    prepared_by = st.text_input("Prepared by")
with own2:
    reviewed_by = st.text_input("Reviewed by")

if not uploaded:
    st.info("The assigned KPIs are shown above. Upload the controlled template to add verified actual results and run the AIC submission checks.")
    st.stop()

try:
    raw_sheets, source_register = read_project_workbook(uploaded)
    validation = validate_workbook(raw_sheets, source_register)
except Exception as exc:
    st.error(f"The workbook could not be read safely: {exc}")
    st.stop()

if followup_min_days > followup_max_days:
    st.error("L'Harmoni minimum follow-up days cannot exceed maximum follow-up days.")
    st.stop()

kpis = calculate_kpis(
    validation,
    reporting_start=reporting_start,
    reporting_end=reporting_end,
    risk_denominator_mode=risk_denominator_mode,
    followup_min_days=int(followup_min_days),
    followup_max_days=int(followup_max_days),
)

blockers = official_export_blockers(
    validation=validation,
    kpis=kpis,
    mapping_approved=mapping_approved,
    mapping_approver=mapping_approver,
    mapping_reference=mapping_reference,
    risk_definition_approved=risk_definition_approved,
    followup_rule_approved=followup_rule_approved,
    followup_rule_version=followup_rule_version,
    reporting_start=reporting_start,
    reporting_end=reporting_end,
)

if blockers:
    st.markdown(
        f"""
        <div class="audit-box status-block">
          <h3 style="margin-top:0; color:#8E1B1B;">Official reporting status: BLOCKED</h3>
          <p>{len(blockers)} blocker(s) must be resolved before an AIC-labelled export can be produced.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for blocker in blockers:
        st.error(blocker)
else:
    st.markdown(
        """
        <div class="audit-box status-pass">
          <h3 style="margin-top:0; color:#1B5E20;">Official reporting status: PASSED</h3>
          <p>No critical validation or approval blocker is currently detected. A human reviewer must still compare the export with the source records before submission.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

summary_tab, april_tab, lharmoni_tab, quality_tab = st.tabs(
    ["Combined Overview", "Project APRIL", "Project L'Harmoni", "Data Quality & Export"]
)


def render_target_cards(project: str) -> None:
    project_rows = kpis.summary[kpis.summary["Project"].eq(project)].copy()
    if project_rows.empty:
        st.info("No KPI rows are available.")
        return
    cols = st.columns(3)
    for i, (_, row) in enumerate(project_rows.iterrows()):
        with cols[i % 3]:
            actual = format_metric(row.get("Actual"), row.get("Unit", ""))
            target = format_metric(row.get("Target"), row.get("Unit", ""))
            st.metric(row["KPI"], actual, delta=f"Target: {target}")
            ratio = progress_ratio(row.get("Actual"), row.get("Target"))
            if ratio is not None:
                st.progress(min(ratio, 1.0), text=f"{ratio:.1%} of target")
            if row.get("Status") == "Data unavailable":
                st.caption("Data unavailable in the uploaded workbook.")


with summary_tab:
    st.markdown("## Actual performance against assigned targets")
    display_summary = kpis.summary.copy()
    display_summary["Actual Display"] = display_summary.apply(
        lambda row: format_metric(row["Actual"], row["Unit"]), axis=1
    )
    display_summary["Target Display"] = display_summary.apply(
        lambda row: format_metric(row["Target"], row["Unit"]), axis=1
    )
    display_summary["Progress"] = display_summary.apply(
        lambda row: progress_ratio(row["Actual"], row["Target"]), axis=1
    )
    shown = display_summary[
        ["Project", "KPI", "Actual Display", "Target Display", "Progress", "Status"]
    ].copy()
    st.dataframe(
        shown,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Progress": st.column_config.ProgressColumn(
                "Progress", min_value=0, max_value=1, format="percent"
            )
        },
    )

    chart_df = display_summary[
        display_summary["Unit"].ne("Percentage")
        & display_summary["Actual"].apply(lambda x: pd.notna(x))
        & display_summary["Target"].apply(lambda x: pd.notna(x))
    ].copy()
    if not chart_df.empty:
        chart_df["KPI Label"] = chart_df["Project"] + " — " + chart_df["KPI"]
        long = chart_df.melt(
            id_vars=["KPI Label"],
            value_vars=["Actual", "Target"],
            var_name="Measure",
            value_name="Value",
        )
        fig = px.bar(long, x="KPI Label", y="Value", color="Measure", barmode="group", text_auto=True)
        fig.update_layout(xaxis_title=None, yaxis_title=None, xaxis_tickangle=-30, margin=dict(b=150))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Centre comparison")
    centre_display = kpis.centre_breakdown.copy()
    if not centre_display.empty:
        centre_display["Actual Display"] = centre_display.apply(
            lambda row: (
                f"{float(row['Actual']):.1%}"
                if pd.notna(row.get("Actual")) and isinstance(row.get("Actual"), (float, np.floating)) and 0 <= float(row.get("Actual")) <= 1
                else (f"{int(row['Actual']):,}" if pd.notna(row.get("Actual")) else "N/A")
            ),
            axis=1,
        )
        st.dataframe(centre_display, use_container_width=True, hide_index=True)

with april_tab:
    st.markdown("## Project APRIL — all four centres")
    st.caption(
        "The dashboard keeps the 1,000-senior onboarding indicator separate from the annual beneficiary-table counts."
    )
    render_target_cards("APRIL")

    st.markdown("### Risk-validation calculation audit")
    risk_audit = pd.DataFrame(
        [
            {
                "Calculation": "Unique seniors",
                "Validated": kpis.calculations.get("april_risk_unique_senior_numerator"),
                "Reviewed": kpis.calculations.get("april_risk_unique_senior_denominator"),
                "Rate": kpis.calculations.get("april_risk_rate_unique_seniors"),
                "Selected for official reporting": risk_denominator_mode == "Unique seniors",
            },
            {
                "Calculation": "Risk flags",
                "Validated": kpis.calculations.get("april_risk_flag_numerator"),
                "Reviewed": kpis.calculations.get("april_risk_flag_denominator"),
                "Rate": kpis.calculations.get("april_risk_rate_flags"),
                "Selected for official reporting": risk_denominator_mode == "Risk flags",
            },
        ]
    )
    st.dataframe(
        risk_audit,
        use_container_width=True,
        hide_index=True,
        column_config={"Rate": st.column_config.NumberColumn(format="percent")},
    )

    april_centre = kpis.centre_breakdown[kpis.centre_breakdown["Project"].eq("APRIL")]
    if not april_centre.empty:
        st.markdown("### APRIL centre breakdown")
        st.dataframe(april_centre, use_container_width=True, hide_index=True)

with lharmoni_tab:
    st.markdown("## Project L'Harmoni — GLOW Bukit Batok and GLOW Nanyang only")
    st.caption(
        "SEEN records are not counted. Any L'Harmoni record assigned to a SEEN centre is a critical exception."
    )
    render_target_cards("L'Harmoni")

    st.markdown("### Outcome denominator and assessment coverage")
    out1, out2, out3 = st.columns(3)
    with out1:
        st.metric(
            "Qualifying seniors",
            f"{int(kpis.calculations.get('lharmoni_outcome_numerator', 0)):,}",
        )
    with out2:
        st.metric(
            "Eligible approved outcomes",
            f"{int(kpis.calculations.get('lharmoni_outcome_denominator', 0)):,}",
        )
    with out3:
        rate = kpis.calculations.get("lharmoni_outcome_rate")
        st.metric("Outcome rate", "N/A" if rate is None or pd.isna(rate) else f"{float(rate):.1%}")

    st.info(
        "The system does not derive Improved or Maintained from raw MMSE, GDS or SPPB scores. "
        "Only outcome classifications approved under the stated rule version can enter the official rate."
    )
    lharmoni_centre = kpis.centre_breakdown[kpis.centre_breakdown["Project"].eq("L'Harmoni")]
    if not lharmoni_centre.empty:
        st.markdown("### L'Harmoni centre breakdown")
        st.dataframe(lharmoni_centre, use_container_width=True, hide_index=True)

with quality_tab:
    st.markdown("## AIC submission checks")
    q1, q2, q3 = st.columns(3)
    q1.metric("Critical issues", f"{validation.critical_count:,}")
    q2.metric("Warnings", f"{validation.warning_count:,}")
    q3.metric("Source sheets read", f"{len(validation.source_register):,}")

    st.markdown("### Exception register")
    if validation.issues.empty:
        st.success("No validation issue was detected.")
    else:
        severity_filter = st.multiselect(
            "Severity",
            ["Critical", "Warning", "Info"],
            default=["Critical", "Warning", "Info"],
        )
        issue_view = validation.issues[validation.issues["Severity"].isin(severity_filter)]
        st.dataframe(issue_view, use_container_width=True, hide_index=True)
        st.download_button(
            "Download exception register CSV",
            validation.issues.to_csv(index=False).encode("utf-8-sig"),
            file_name="CST_KPI_Exception_Register.csv",
            mime="text/csv",
        )

    st.markdown("### Source register")
    st.dataframe(validation.source_register, use_container_width=True, hide_index=True)

    st.markdown("### Calculation detail")
    if kpis.detail.empty:
        st.info("No record-level calculation detail is available from the current upload.")
    else:
        st.dataframe(kpis.detail, use_container_width=True, hide_index=True)

    st.markdown("### Controlled export")
    if not prepared_by.strip() or not reviewed_by.strip():
        st.warning("Enter both Prepared by and Reviewed by before exporting.")
    export_ready = not blockers and bool(prepared_by.strip()) and bool(reviewed_by.strip())
    if export_ready:
        export_bytes = build_export_workbook(
            validation=validation,
            kpis=kpis,
            reporting_start=reporting_start,
            reporting_end=reporting_end,
            prepared_by=prepared_by,
            reviewed_by=reviewed_by,
            mapping_approver=mapping_approver,
            mapping_reference=mapping_reference,
            risk_denominator_mode=risk_denominator_mode,
            followup_min_days=int(followup_min_days),
            followup_max_days=int(followup_max_days),
            followup_rule_version=followup_rule_version,
            official_status="PASSED — pending final human sign-off",
        )
        st.download_button(
            "Download AIC controlled KPI export",
            data=export_bytes,
            file_name=f"AIC_CST_KPI_Export_{reporting_end.isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
        st.caption(
            "The export remains pending final human sign-off. Compare the summary, exceptions, calculation detail and source register before sending."
        )
    else:
        st.button(
            "Download AIC controlled KPI export",
            disabled=True,
            use_container_width=True,
            help="Resolve all blockers and complete submission ownership fields first.",
        )
