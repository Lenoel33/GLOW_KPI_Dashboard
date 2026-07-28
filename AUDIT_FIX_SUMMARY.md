# Audit fix summary

Use `app.py` as the only Streamlit entry point.

## Fixed
- Unicode participant names are preserved during name matching, including Chinese names.
- L'Harmoni centre assignment uses only the row-level `Centres` field.
- Values containing `Bukit Batok` map to `GLOW Bukit Batok`.
- Values containing `Nanyang` map to `GLOW Nanyang`.
- Filenames are not used to infer L'Harmoni centres.
- Obsolete duplicate dashboard architecture was removed.
- Streamlit configuration was moved to `.streamlit/config.toml`.

## Streamlit deployment
- Repository: `Lenoel33/GLOW_KPI_Dashboard`
- Branch: `main`
- Main file path: `app.py`
