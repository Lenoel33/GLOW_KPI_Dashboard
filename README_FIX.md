# CST KPI Visibility Fix

## Why the new KPIs did not appear

The deployed GitHub repository must contain the actual files and folders below. Uploading the ZIP file itself does not install or extract them.

```text
cst_kpi_core.py
pages/2_CST_Project_KPIs.py
templates/CST_KPI_Data_Template.xlsx
```

This revision also changes the CST page so the assigned APRIL and L'Harmoni KPI names and targets appear immediately, before any data workbook is uploaded.

## Correct GitHub structure

```text
GLOW_KPI_Dashboard/
├── app.py
├── utils.py
├── cst_kpi_core.py
├── pages/
│   └── 2_CST_Project_KPIs.py
└── templates/
    └── CST_KPI_Data_Template.xlsx
```

## Installation

1. Extract this ZIP on your computer.
2. Open the GitHub repository.
3. Upload `cst_kpi_core.py` into the repository root.
4. Upload the `pages` folder and its Python file.
5. Upload the `templates` folder and its Excel file.
6. Commit directly to the branch used by Streamlit Community Cloud.
7. Reboot the Streamlit app from **Manage app** if it does not redeploy automatically.
8. Open the sidebar page named **CST Project KPIs**.

Do not upload only `GLOW_KPI_Dashboard_CST_AIC_Update_v2.zip` to GitHub. GitHub stores a ZIP as a file and does not extract it into the app.

## Expected result

Before data upload, the page displays:

- APRIL: 1,000 seniors onboarded
- APRIL: 80% risk validation
- APRIL: 100 complete annual MMSE/GDS/SPPB sets
- APRIL: 300 unique seniors tracked over three years
- APRIL beneficiary targets for AAC clients, volunteers and caregivers
- L'Harmoni: 1,000 participating seniors
- L'Harmoni: 500 seniors per GLOW centre
- L'Harmoni: 60% improved or maintained outcome target
- L'Harmoni annual and three-year assessment targets

Actual results continue to display as unavailable until valid source data is uploaded.
