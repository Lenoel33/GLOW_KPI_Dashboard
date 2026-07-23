# GLOW KPI Dashboard — APRIL and L’Harmoni Taskbar Update

This package keeps the original centre KPI dashboard in `app.py` and adds a horizontal taskbar at the top:

- Centre Dashboard
- Project APRIL
- Project L’Harmoni

No `centre_dashboard.py`, `main.py`, or `pages/` folder is required.

## What changed

Only `app.py` was extended with the taskbar and the two project KPI views. The original centre dashboard code continues to run when **Centre Dashboard** is selected.

### Project APRIL

Applies to all four centres:

- GLOW Bukit Batok
- Tzu Chi SEEN @ Bukit Batok
- GLOW Nanyang
- Tzu Chi SEEN @ Nanyang

The page compares current uploaded values against the project-wide APRIL targets. It does not invent individual centre targets where the CST application does not specify them.

### Project L’Harmoni

Applies only to:

- GLOW Bukit Batok
- GLOW Nanyang

SEEN centre rows are rejected from this page.

## GitHub upload

Extract the ZIP and upload all extracted files to the root of the GitHub repository. Replace the existing files when GitHub asks.

The repository should contain:

```text
app.py
utils.py
requirements.txt
CST_Project_KPI_Input_Template.xlsx
.streamlit/config.toml
tests/test_utils.py
```

Keep the Streamlit deployment entry point as:

```text
app.py
```

## Using the project KPI pages

1. Open Project APRIL or Project L’Harmoni from the taskbar.
2. Download the controlled input template from the page.
3. Complete the relevant sheet without renaming it.
4. Upload the completed workbook to the matching project page.
5. Resolve all validation errors and reconcile totals before AIC reporting.

The dashboard does not estimate missing official project fields from attendance data. Missing values remain unavailable until source-backed data is entered.
