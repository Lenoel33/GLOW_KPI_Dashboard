# GLOW KPI Dashboard — AIC/CST Complete Project KPI Update

This package preserves the existing Centre Dashboard and adds two project pages in the existing left sidebar:

- Centre Dashboard
- Project APRIL
- Project L’Harmoni

The Streamlit main file remains `app.py`. There is no `pages` folder and no `centre_dashboard.py` requirement.

## Upload to GitHub

1. Extract the ZIP on your computer.
2. Upload all extracted files and folders directly to the root of `Lenoel33/GLOW_KPI_Dashboard`.
3. Replace the existing `app.py`, `utils.py`, `requirements.txt`, and `.streamlit/config.toml` when prompted.
4. Delete any old `pages` folder and obsolete project-dashboard Python files from earlier versions.
5. Keep the Streamlit main file path as `app.py`.
6. Reboot the Streamlit Community Cloud app.

## APRIL scope and indicators

APRIL includes all four centres:

- GLOW Bukit Batok
- Tzu Chi SEEN @ Bukit Batok
- GLOW Nanyang
- Tzu Chi SEEN @ Nanyang

The dashboard reflects:

- 1,000 seniors onboarded onto APRIL tools.
- 80% of all APRIL-flagged seniors validated with staff-assessment evidence.
- 1,000 AAC clients annually; 3,000 beneficiary instances over three years.
- 100 volunteers annually; 300 beneficiary instances over three years.
- 200 caregivers annually; 600 beneficiary instances over three years.
- Total three-year beneficiary commitment of 3,900.
- 100 complete MMSE/GDS/SPPB assessment sets annually.
- 300 unique seniors tracked across the full three-year study period.
- APRIL usage, productivity savings, user satisfaction, risk-review coverage, and implementation milestones.

The official APRIL validation formula is:

`flagged seniors validated with MMSE/GDS/SPPB evidence ÷ all APRIL-flagged seniors`

Pending reviews remain in the denominator and are shown separately.

## L’Harmoni scope and indicators

L’Harmoni includes only:

- GLOW Bukit Batok
- GLOW Nanyang

The dashboard reflects:

- 1,000 total participating seniors.
- 500 participants per GLOW centre.
- 60% improving or maintaining physical and/or cognitive scores one year after joining.
- 100 complete MMSE/GDS/SPPB assessment sets annually.
- 300 unique seniors tracked across the full three-year study period.
- One-year assessment coverage, approved physical/cognitive outcome breakdown, tracks, sessions, group-size compliance, transitions, ICCP escalation, and implementation milestones.

The official 60% result is withheld until the user approves the one-year follow-up window in the dashboard controls. Generic overall/emotional outcomes do not enter the official physical/cognitive numerator.

## Supported source formats

The project pages scan every structured table in:

- XLSX, XLS, XLSM
- CSV, TSV, TXT
- JSON
- ZIP containing the supported formats

Unrelated attendance is not converted into project participation. Missing evidence is shown as `Data unavailable`, not zero.

## Included workbooks

- `AIC_Project_KPI_Input_Template.xlsx`: controlled data-entry template covering every project indicator and monitoring field.
- `AIC_Project_KPI_Mock_Verification.xlsx`: fictional verification data with expected results.

For the mock workbook use:

- Reporting year: 2026
- Three-year study start: 2025
- L’Harmoni follow-up window: 335–395 days
- L’Harmoni data cut-off: 2026-07-23
- Approve the timing window checkbox

## Accuracy safeguards

- Exact project and centre scope.
- Stable ID de-duplication; name fallback is warned.
- Annual and three-year calculations are separate.
- MMSE/GDS/SPPB must belong to one dated episode.
- APRIL pending reviews are not hidden.
- APRIL validation requires assessment evidence.
- L’Harmoni one-year timing is verified.
- L’Harmoni formal outcomes are limited to physical and/or cognitive domains.
- `No Change` is not automatically treated as `Maintained`.
- Source and field registers show how every source was interpreted.
- AIC submission-readiness table identifies missing evidence.

A final human reconciliation against the source system remains mandatory before any submission to AIC.
