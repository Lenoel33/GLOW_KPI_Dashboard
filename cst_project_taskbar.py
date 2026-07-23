"""Top taskbar and embedded CST project KPI views for the GLOW dashboard.

This module is intentionally conservative for AIC-facing reporting:
- targets are fixed to the submitted CST application;
- unknown or unsupported data is shown as unavailable, not inferred;
- L'Harmoni is restricted to the two operationally confirmed GLOW centres;
- clinical outcome classifications must be supplied and approved in the source workbook.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from cst_kpi_core import (
    ALL_CENTRES,
    OFFICIAL_TARGETS,
    PROJECT_CENTRES,
    SOURCE_NOTES,
    calculate_kpis,
    format_metric,
    progress_ratio,
    read_project_workbook,
    validate_workbook,
)

APP_DIR = Path(__file__).resolve().parent
TEMPLATE_CANDIDATES = [
    APP_DIR / "CST_KPI_Data_Template.xlsx",
    APP_DIR / "templates" / "CST_KPI_Data_Template.xlsx",
]

NAV_OPTIONS = ["Centre Dashboard", "Project APRIL", "Project L'Harmoni"]


def render_project_taskbar() -> str:
    """Render a horizontal taskbar above the existing dashboard."""
    st.markdown(
        """
        <style>
        .cst-taskbar-title {
            color: #0D2B45;
            font-weight: 800;
            font-size: 0.92rem;
            margin: 0 0 0.35rem 0;
            letter-spacing: 0.02em;
        }
        div[data-testid="stRadio"] > div {
            flex-direction: row;
            gap: 0.55rem;
            background: #FFFFFF;
            border: 1px solid #E9D6B3;
            border-radius: 16px;
            padding: 0.45rem 0.55rem;
            box-shadow: 0 5px 16px rgba(13, 43, 69, 0.08);
        }
        div[data-testid="stRadio"] label {
            background: #F7F1E7;
            border: 1px solid #E9D6B3;
            border-radius: 12px;
            padding: 0.45rem 0.8rem;
            margin: 0;
            min-height: 42px;
            align-items: center;
        }
        div[data-testid="stRadio"] label:has(input:checked) {
            background: #0D2B45;
            color: #FFFFFF;
            border-color: #0D2B45;
        }
        div[data-testid="stRadio"] label:has(input:checked) p {
            color: #FFFFFF !important;
            font-weight: 800;
        }
        </style>
        <div class="cst-taskbar-title">DASHBOARD PAGES</div>
        """,
        unsafe_allow_html=True,
    )
    return st.radio(
        "Dashboard page",
        NAV_OPTIONS,
        horizontal=True,
        label_visibility="collapsed",
        key="glow_top_dashboard_page",
    )


def _target_reference(project: str) -> pd.DataFrame:
    if project == "APRIL":
        return pd.DataFrame(
            [
                {
                    "KPI": "Unique seniors onboarded onto APRIL tools",
                    "Target": "1,000 seniors",
                    "Applicable centres": "All four centres",
                    "Evidence required": "Senior ID, approved centre, onboarding date and onboarding status",
                },
                {
                    "KPI": "At-risk seniors validated through staff assessment",
                    "Target": "80%",
                    "Applicable centres": "All four centres",
                    "Evidence required": "Risk flag, staff review, validation outcome and reviewer",
                },
                {
                    "KPI": "Complete annual MMSE, GDS and SPPB assessment sets",
                    "Target": "100 seniors per year",
                    "Applicable centres": "All four centres",
                    "Evidence required": "All three assessment types for the same senior and year",
                },
                {
                    "KPI": "Unique seniors tracked across three years",
                    "Target": "300 unique seniors",
                    "Applicable centres": "All four centres",
                    "Evidence required": "De-duplicated senior IDs with complete assessment sets",
                },
                {
                    "KPI": "AAC clients reached",
                    "Target": "1,000 annually",
                    "Applicable centres": "All four centres",
                    "Evidence required": "Unique beneficiary ID and engagement date",
                },
                {
                    "KPI": "Volunteers reached",
                    "Target": "100 annually",
                    "Applicable centres": "All four centres",
                    "Evidence required": "Unique beneficiary ID and engagement date",
                },
                {
                    "KPI": "Caregivers reached",
                    "Target": "200 annually",
                    "Applicable centres": "All four centres",
                    "Evidence required": "Unique beneficiary ID and engagement date",
                },
            ]
        )

    return pd.DataFrame(
        [
            {
                "KPI": "Unique participating seniors",
                "Target": "1,000 seniors",
                "Applicable centres": "GLOW Bukit Batok and GLOW Nanyang",
                "Evidence required": "Senior ID, approved GLOW centre and enrolment date",
            },
            {
                "KPI": "GLOW Bukit Batok participation",
                "Target": "500 seniors",
                "Applicable centres": "GLOW Bukit Batok",
                "Evidence required": "Unique enrolled senior IDs",
            },
            {
                "KPI": "GLOW Nanyang participation",
                "Target": "500 seniors",
                "Applicable centres": "GLOW Nanyang",
                "Evidence required": "Unique enrolled senior IDs",
            },
            {
                "KPI": "Improved or maintained physical and/or cognitive wellbeing",
                "Target": "60% at approved one-year follow-up",
                "Applicable centres": "Both GLOW centres",
                "Evidence required": "Approved outcome, rule version, reviewer and valid follow-up date",
            },
            {
                "KPI": "Complete annual MMSE, GDS and SPPB assessment sets",
                "Target": "100 seniors per year",
                "Applicable centres": "Both GLOW centres",
                "Evidence required": "All three assessment types for the same senior and year",
            },
            {
                "KPI": "Unique seniors tracked across three years",
                "Target": "300 unique seniors",
                "Applicable centres": "Both GLOW centres",
                "Evidence required": "De-duplicated senior IDs with complete assessment sets",
            },
        ]
    )


def _template_path() -> Path | None:
    for candidate in TEMPLATE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _project_header(project: str, subtitle: str) -> None:
    accent = "#C45D2D" if project == "APRIL" else "#6F9CA3"
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0D2B45 0%,{accent} 100%);color:white;
                    padding:24px 28px;border-radius:22px;margin:12px 0 18px 0;
                    box-shadow:0 10px 28px rgba(13,43,69,.18);">
            <div style="font-size:2rem;font-weight:850;line-height:1.15;">{project}</div>
            <div style="margin-top:8px;color:#F3E8D2;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _metric_card(label: str, value: str, target: str, status: str = "") -> None:
    st.markdown(
        f"""
        <div style="background:#FFFFFF;border:1px solid #E9D6B3;border-radius:18px;
                    padding:18px 20px;min-height:145px;box-shadow:0 5px 16px rgba(13,43,69,.07);">
            <div style="font-size:.92rem;color:#55623B;font-weight:750;">{label}</div>
            <div style="font-size:2rem;color:#0D2B45;font-weight:850;margin-top:10px;">{value}</div>
            <div style="font-size:.86rem;color:#6B7280;margin-top:8px;">Target: {target}</div>
            <div style="font-size:.82rem;color:#C45D2D;margin-top:4px;">{status}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _load_controlled_workbook(project_key: str) -> bytes | None:
    template_path = _template_path()
    left, right = st.columns([1, 1])
    with left:
        if template_path is not None:
            st.download_button(
                "Download controlled CST KPI template",
                data=template_path.read_bytes(),
                file_name="CST_KPI_Data_Template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"download_cst_template_{project_key}",
            )
        else:
            st.error("CST_KPI_Data_Template.xlsx is missing from the repository root.")
    with right:
        if st.button(
            "Clear project workbook",
            use_container_width=True,
            key=f"clear_cst_workbook_{project_key}",
        ):
            st.session_state.pop("cst_project_workbook_bytes", None)
            st.session_state.pop("cst_project_workbook_name", None)
            st.rerun()

    uploaded = st.file_uploader(
        "Upload the completed controlled CST KPI workbook",
        type=["xlsx"],
        accept_multiple_files=False,
        key=f"cst_project_uploader_{project_key}",
        help=(
            "Only source-backed project records should be entered. The dashboard does not infer APRIL onboarding, "
            "risk validation or L'Harmoni outcomes from ordinary attendance workbooks."
        ),
    )
    if uploaded is not None:
        st.session_state["cst_project_workbook_bytes"] = uploaded.getvalue()
        st.session_state["cst_project_workbook_name"] = uploaded.name

    stored = st.session_state.get("cst_project_workbook_bytes")
    if stored:
        st.caption(
            f"Loaded controlled workbook: {st.session_state.get('cst_project_workbook_name', 'uploaded workbook')}"
        )
    return stored


def _reporting_controls(project_key: str) -> dict[str, Any]:
    st.markdown("### Reporting controls")
    c1, c2 = st.columns(2)
    with c1:
        reporting_start = st.date_input(
            "Reporting period start",
            value=pd.Timestamp("2025-01-01").date(),
            key=f"reporting_start_{project_key}",
        )
        reporting_end = st.date_input(
            "Reporting period end",
            value=pd.Timestamp.today().date(),
            key=f"reporting_end_{project_key}",
        )
    with c2:
        risk_mode = st.selectbox(
            "APRIL risk-validation denominator",
            ["Unique seniors", "Risk flags"],
            index=0,
            key=f"risk_mode_{project_key}",
            disabled=project_key != "april",
            help="Use the written, approved definition for formal reporting.",
        )
        followup_days = st.number_input(
            "Approved L'Harmoni follow-up day",
            min_value=1,
            max_value=730,
            value=365,
            step=1,
            key=f"followup_days_{project_key}",
            disabled=project_key != "lharmoni",
        )
    return {
        "reporting_start": reporting_start,
        "reporting_end": reporting_end,
        "risk_mode": risk_mode,
        "followup_days": int(followup_days),
    }


def _calculate_from_bytes(data: bytes, controls: dict[str, Any]):
    if controls["reporting_start"] > controls["reporting_end"]:
        st.error("Reporting period start cannot be after the reporting period end.")
        return None, None
    try:
        raw_sheets, source_register = read_project_workbook(BytesIO(data))
        validation = validate_workbook(raw_sheets, source_register)
        kpis = calculate_kpis(
            validation,
            reporting_start=controls["reporting_start"],
            reporting_end=controls["reporting_end"],
            risk_denominator_mode=controls["risk_mode"],
            followup_min_days=controls["followup_days"],
            followup_max_days=controls["followup_days"],
        )
        return validation, kpis
    except Exception as exc:  # defensive: workbook errors must be visible, not hidden
        st.error(f"The controlled workbook could not be read safely: {exc}")
        return None, None


def _format_actual(row: pd.Series) -> str:
    if str(row.get("Status", "")) != "Available":
        return str(row.get("Status", "Data unavailable"))
    return format_metric(row.get("Actual"), str(row.get("Unit", "")))


def _show_data_quality(validation, project: str) -> None:
    st.markdown("### AIC data-quality status")
    c1, c2, c3 = st.columns(3)
    c1.metric("Critical issues", int(validation.critical_count))
    c2.metric("Warnings", int(validation.warning_count))
    c3.metric("Recognised source sheets", len(validation.present_sheets))

    issues = validation.issues.copy()
    if not issues.empty and "Project" in issues.columns:
        project_names = {project.upper(), "L'HARMONI" if project == "L'Harmoni" else project.upper()}
        project_issues = issues[
            issues["Project"].astype(str).str.upper().isin(project_names)
            | issues["Project"].astype(str).str.strip().eq("")
            | issues["Project"].isna()
        ].copy()
    else:
        project_issues = issues

    if project_issues.empty:
        st.success("No project-specific validation issues were detected in the uploaded workbook.")
    else:
        st.dataframe(project_issues, use_container_width=True, hide_index=True)

    if validation.critical_count:
        st.error(
            "Critical validation issues remain. Do not use the displayed figures for an AIC submission until every critical issue is resolved and the source totals are reconciled."
        )
    else:
        st.warning(
            "Passing automated validation does not replace human reconciliation and approval before submission to AIC."
        )


def _show_project_results(project: str, validation, kpis) -> None:
    summary = kpis.summary[kpis.summary["Project"].eq(project)].copy()
    summary["Actual result"] = summary.apply(_format_actual, axis=1)
    summary["Progress"] = summary.apply(
        lambda row: progress_ratio(row.get("Actual"), row.get("Target"))
        if str(row.get("Status", "")) == "Available"
        else np.nan,
        axis=1,
    )
    summary["Progress to target"] = summary["Progress"].apply(
        lambda value: "Not available" if pd.isna(value) else f"{value:.1%}"
    )

    st.markdown("### Verified actual-versus-target results")
    st.dataframe(
        summary[["KPI", "Actual result", "Target", "Unit", "Progress to target", "Status"]],
        use_container_width=True,
        hide_index=True,
    )

    chart_data = summary.loc[summary["Progress"].notna(), ["KPI", "Progress"]].copy()
    if not chart_data.empty:
        chart_data["Progress percent"] = (chart_data["Progress"] * 100).clip(lower=0)
        fig = px.bar(
            chart_data,
            x="Progress percent",
            y="KPI",
            orientation="h",
            text="Progress percent",
            title=f"{project} progress against assigned targets",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
        fig.update_layout(
            xaxis_title="Progress to target (%)",
            yaxis_title=None,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=80, t=60, b=30),
        )
        st.plotly_chart(fig, use_container_width=True, key=f"{project}_progress_chart")

    centre = kpis.centre_breakdown[kpis.centre_breakdown["Project"].eq(project)].copy()
    if not centre.empty:
        centre["Actual display"] = centre.apply(
            lambda row: format_metric(
                row.get("Actual"),
                "Percentage" if "rate" in str(row.get("KPI", "")).lower() or "wellbeing" in str(row.get("KPI", "")).lower() else "Unique seniors",
            ),
            axis=1,
        )
        st.markdown("### Centre comparison")
        display_cols = [
            col
            for col in ["Centre", "KPI", "Actual display", "Target", "Numerator", "Denominator"]
            if col in centre.columns
        ]
        st.dataframe(centre[display_cols], use_container_width=True, hide_index=True)

    _show_data_quality(validation, project)


def render_april_dashboard() -> None:
    _project_header(
        "Project APRIL",
        "All four centres · onboarding, validated risk flags, annual assessments and beneficiary reach",
    )

    cards = st.columns(4)
    with cards[0]:
        _metric_card("Seniors onboarded", "Data not uploaded", "1,000")
    with cards[1]:
        _metric_card("Risk validation", "Data not uploaded", "80%")
    with cards[2]:
        _metric_card("Annual assessment cohort", "Data not uploaded", "100 seniors")
    with cards[3]:
        _metric_card("Three-year tracked cohort", "Data not uploaded", "300 seniors")

    with st.expander("Assigned APRIL KPI definitions", expanded=True):
        st.dataframe(_target_reference("APRIL"), use_container_width=True, hide_index=True)
        st.caption(SOURCE_NOTES["APRIL"])

    st.markdown("### Controlled project data")
    data = _load_controlled_workbook("april")
    controls = _reporting_controls("april")
    if not data:
        st.info("Upload the controlled workbook to replace 'Data not uploaded' with source-backed actual results.")
        return

    validation, kpis = _calculate_from_bytes(data, controls)
    if validation is None or kpis is None:
        return
    _show_project_results("APRIL", validation, kpis)


def render_lharmoni_dashboard() -> None:
    _project_header(
        "Project L'Harmoni",
        "GLOW Bukit Batok and GLOW Nanyang only · participation and approved one-year outcomes",
    )

    cards = st.columns(4)
    with cards[0]:
        _metric_card("Total participants", "Data not uploaded", "1,000")
    with cards[1]:
        _metric_card("GLOW Bukit Batok", "Data not uploaded", "500")
    with cards[2]:
        _metric_card("GLOW Nanyang", "Data not uploaded", "500")
    with cards[3]:
        _metric_card("Improved / maintained", "Data not uploaded", "60%")

    with st.expander("Assigned L'Harmoni KPI definitions", expanded=True):
        st.dataframe(_target_reference("L'Harmoni"), use_container_width=True, hide_index=True)
        st.caption(SOURCE_NOTES["L'Harmoni"])
        mapping = pd.DataFrame(
            [
                {
                    "Centre": centre,
                    "L'Harmoni applicability": "Applicable"
                    if centre in PROJECT_CENTRES["L'Harmoni"]
                    else "Not applicable",
                }
                for centre in ALL_CENTRES
            ]
        )
        st.dataframe(mapping, use_container_width=True, hide_index=True)

    st.markdown("### Controlled project data")
    data = _load_controlled_workbook("lharmoni")
    controls = _reporting_controls("lharmoni")
    if not data:
        st.info("Upload the controlled workbook to replace 'Data not uploaded' with source-backed actual results.")
        return

    validation, kpis = _calculate_from_bytes(data, controls)
    if validation is None or kpis is None:
        return
    _show_project_results("L'Harmoni", validation, kpis)
