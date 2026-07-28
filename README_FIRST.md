# GLOW KPI Dashboard — keep the original centre dashboard

This fix does **not** replace or rename your current `app.py`.

Your existing `app.py` remains the full Centre Dashboard. The new `main.py`
adds a taskbar above it and loads the APRIL and L'Harmoni dashboards when those
buttons are selected.

## Upload these four files to the repository root

- `main.py`
- `cst_project_taskbar.py`
- `cst_kpi_core.py`
- `CST_KPI_Data_Template.xlsx`

Do not delete, rename, or overwrite your existing:

- `app.py`
- `utils.py`
- `requirements.txt`

The repository should look like this:

```text
GLOW_KPI_Dashboard/
├── main.py                    NEW — unified entry point
├── app.py                     KEEP — original centre KPI dashboard
├── utils.py                   KEEP
├── requirements.txt           KEEP
├── cst_project_taskbar.py     NEW
├── cst_kpi_core.py            NEW
└── CST_KPI_Data_Template.xlsx NEW
```

## Deploy the unified dashboard

Create or redeploy a Streamlit Community Cloud app using:

- Repository: `Lenoel33/GLOW_KPI_Dashboard`
- Branch: `main`
- Main file path: `main.py`

The original `app.py` remains in the same repository and is executed by
`main.py` whenever **Centre Dashboard** is selected.

For a safe first test, deploy `main.py` as a second Streamlit app. After it is
working, you may keep the new URL or replace the old deployment. Streamlit
treats the entrypoint path as part of the app's GitHub coordinates, so changing
an existing deployment from `app.py` to `main.py` may require deleting and
redeploying it.

## Expected result

The top taskbar will show:

```text
Centre Dashboard | Project APRIL | Project L'Harmoni
```

- **Centre Dashboard** executes the original `app.py` unchanged.
- **Project APRIL** shows all APRIL targets and controlled actual results.
- **Project L'Harmoni** shows the two GLOW-centre targets and controlled outcomes.

## Important

Do not rename the original `app.py` to `centre_dashboard.py`. This package is
specifically designed to keep it in place and remove the missing-file error.
