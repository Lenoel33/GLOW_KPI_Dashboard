"""Unified GLOW KPI dashboard entry point.

This file keeps the repository's existing ``app.py`` as the Centre Dashboard
and adds Project APRIL and Project L'Harmoni as two additional views.

Deploy THIS file (main.py) in Streamlit Community Cloud. Do not rename or
replace the existing app.py.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
CENTRE_DASHBOARD_PATH = APP_DIR / "app.py"

st.set_page_config(
    page_title="GLOW KPI Dashboard",
    page_icon="📊",
    layout="wide",
)


def _set_page(page_name: str) -> None:
    st.session_state["glow_dashboard_page"] = page_name
    st.rerun()


def _render_navigation() -> str:
    """Render a simple top taskbar without changing widgets in the old app."""
    pages = ["Centre Dashboard", "Project APRIL", "Project L'Harmoni"]
    current = st.session_state.get("glow_dashboard_page", pages[0])
    if current not in pages:
        current = pages[0]
        st.session_state["glow_dashboard_page"] = current

    st.markdown(
        """
        <style>
        .main .block-container { padding-top: 1.15rem; }
        .glow-nav-title {
            color: #0D2B45;
            font-size: .95rem;
            font-weight: 850;
            letter-spacing: .025em;
            margin: 0 0 .45rem 0;
        }
        div[data-testid="stHorizontalBlock"]:has(.glow-nav-anchor) {
            background: #FFFFFF;
            border: 1px solid #E9D6B3;
            border-radius: 18px;
            padding: .55rem;
            box-shadow: 0 6px 18px rgba(13,43,69,.08);
            margin-bottom: 1rem;
        }
        </style>
        <div class="glow-nav-title">DASHBOARD PAGES</div>
        """,
        unsafe_allow_html=True,
    )

    # The invisible anchor scopes the optional CSS above to this row only.
    cols = st.columns(3, gap="small")
    with cols[0]:
        st.markdown('<span class="glow-nav-anchor"></span>', unsafe_allow_html=True)
        if st.button(
            "●  Centre Dashboard",
            type="primary" if current == pages[0] else "secondary",
            use_container_width=True,
            key="nav_centre_dashboard",
        ):
            _set_page(pages[0])
    with cols[1]:
        if st.button(
            "Project APRIL",
            type="primary" if current == pages[1] else "secondary",
            use_container_width=True,
            key="nav_project_april",
        ):
            _set_page(pages[1])
    with cols[2]:
        if st.button(
            "Project L'Harmoni",
            type="primary" if current == pages[2] else "secondary",
            use_container_width=True,
            key="nav_project_lharmoni",
        ):
            _set_page(pages[2])

    return current


def _run_existing_centre_dashboard() -> None:
    """Execute the existing app.py unchanged below the top taskbar.

    The old app calls st.set_page_config itself. Because main.py has already
    configured the page before showing navigation, that one call is temporarily
    replaced with a no-op while app.py runs. All other original dashboard code,
    upload controls, calculations, charts, and session state remain unchanged.
    """
    if not CENTRE_DASHBOARD_PATH.exists():
        st.error(
            "The existing app.py is missing. Keep your original centre dashboard "
            "file named app.py in the repository root."
        )
        st.code(
            "GLOW_KPI_Dashboard/\n"
            "├── main.py                 ← deploy this file\n"
            "├── app.py                  ← keep your original centre dashboard\n"
            "├── utils.py\n"
            "├── cst_project_taskbar.py\n"
            "├── cst_kpi_core.py\n"
            "└── CST_KPI_Data_Template.xlsx"
        )
        return

    original_set_page_config = st.set_page_config
    st.set_page_config = lambda *args, **kwargs: None  # type: ignore[assignment]
    try:
        runpy.run_path(
            str(CENTRE_DASHBOARD_PATH),
            run_name="__glow_existing_centre_dashboard__",
        )
    finally:
        st.set_page_config = original_set_page_config  # type: ignore[assignment]


selected_page = _render_navigation()

if selected_page == "Centre Dashboard":
    _run_existing_centre_dashboard()
elif selected_page == "Project APRIL":
    from cst_project_taskbar import render_april_dashboard

    render_april_dashboard()
else:
    from cst_project_taskbar import render_lharmoni_dashboard

    render_lharmoni_dashboard()
