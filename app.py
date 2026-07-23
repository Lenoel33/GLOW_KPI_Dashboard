"""GLOW KPI Dashboard entrypoint with APRIL and L'Harmoni taskbar.

Before using this file, rename the repository's existing ``app.py`` to
``centre_dashboard.py``. This entrypoint keeps that dashboard unchanged and
runs it beneath the new horizontal taskbar.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
CENTRE_DASHBOARD = APP_DIR / "centre_dashboard.py"

# Must be the first Streamlit command in the entrypoint.
st.set_page_config(
    page_title="GLOW KPI Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from cst_project_taskbar import (  # noqa: E402
    render_april_dashboard,
    render_lharmoni_dashboard,
    render_project_taskbar,
)

selected_page = render_project_taskbar()

if selected_page == "Project APRIL":
    render_april_dashboard()
elif selected_page == "Project L'Harmoni":
    render_lharmoni_dashboard()
else:
    if not CENTRE_DASHBOARD.exists():
        st.error(
            "centre_dashboard.py is missing. Rename the previous app.py to "
            "centre_dashboard.py before uploading this new app.py."
        )
        st.stop()

    # centre_dashboard.py already calls st.set_page_config(). Streamlit only
    # permits that call once, so suppress the duplicate while executing the
    # unchanged dashboard below the taskbar.
    original_set_page_config = st.set_page_config
    st.set_page_config = lambda *args, **kwargs: None
    try:
        runpy.run_path(
            str(CENTRE_DASHBOARD),
            run_name="__glow_centre_dashboard__",
        )
    finally:
        st.set_page_config = original_set_page_config
