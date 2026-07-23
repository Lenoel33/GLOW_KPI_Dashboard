# Final GitHub Upload — GLOW KPI Dashboard

This version adds a horizontal taskbar inside the same Streamlit app:

```text
Centre Dashboard | Project APRIL | Project L'Harmoni
```

It does not use a `pages` folder.

## Important: preserve the existing dashboard first

Before uploading the files in this package, rename the current repository file:

```text
app.py  →  centre_dashboard.py
```

### Rename it directly in GitHub

1. Open the existing `app.py` in the repository.
2. Select the pencil/edit button.
3. Change the filename at the top to `centre_dashboard.py`.
4. Commit the change to `main`.

Do not change the code inside that file.

## Upload this package

GitHub does not extract ZIP files automatically. Extract the ZIP on your
computer, then upload these files to the repository root:

```text
app.py
cst_project_taskbar.py
cst_kpi_core.py
CST_KPI_Data_Template.xlsx
requirements.txt
```

After uploading, the repository must contain:

```text
GLOW_KPI_Dashboard/
├── app.py                    # new taskbar entrypoint
├── centre_dashboard.py       # previous app.py, unchanged
├── utils.py                  # existing processing code
├── cst_project_taskbar.py
├── cst_kpi_core.py
├── CST_KPI_Data_Template.xlsx
└── requirements.txt
```

Because the deployed entrypoint remains `app.py`, you do not need a `pages`
folder or a different Streamlit file path. Streamlit Community Cloud should
pick up the committed Python changes automatically. Reboot the app from
**Manage app** if the old version remains cached.

## Project rules in this version

### APRIL

- Applies to all four centres.
- Target: 1,000 unique seniors onboarded.
- Target: 80% risk validation.
- Target: 100 complete MMSE/GDS/SPPB sets annually.
- Target: 300 unique seniors tracked over three years.
- Annual beneficiary counts are shown separately from onboarding.

### L'Harmoni

- Applies only to GLOW Bukit Batok and GLOW Nanyang.
- Target: 500 unique participants per GLOW centre.
- Combined target: 1,000 participants.
- Target: 60% improving or maintaining physical and/or cognitive wellbeing.

## Accuracy safeguards

- Missing data is shown as unavailable, not zero.
- Unknown centres are not guessed.
- SEEN records are rejected from L'Harmoni reporting.
- Clinical outcomes are not inferred from raw scores.
- Invalid and duplicate records are placed in an exception register.
- AIC-facing totals still require source reconciliation and authorised review.
