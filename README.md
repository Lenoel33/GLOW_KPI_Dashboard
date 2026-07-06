# GLOW KPI Dashboard

Upload any attendance Excel file and view centre KPIs, activity trends, male participation, returning members, and inactive seniors.

## Important inactive rule
Inactive seniors are calculated from attendance records:

- 0, 1, or 2 attended records = inactive
- 3 or more attended records = active

This does **not** rely on the imported AAP field.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Upload to GitHub / Streamlit Cloud

Upload these files to your repository:

- app.py
- utils.py
- requirements.txt
- README.md

Then deploy from Streamlit Community Cloud.
