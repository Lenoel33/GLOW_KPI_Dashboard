# GLOW KPI Dashboard — Sidebar Project Navigation

This build preserves the original centre KPI dashboard and adds two project views inside the existing Streamlit sidebar:

- Centre Dashboard
- Project APRIL — all four centres
- Project L’Harmoni — GLOW Bukit Batok and GLOW Nanyang only

## GitHub upload

Upload the extracted files to the repository root and replace the existing `app.py`, `utils.py`, `.streamlit/config.toml`, and related files.

The Streamlit entrypoint remains:

```
app.py
```

The package intentionally contains no `pages` folder. If an old `pages` folder remains in GitHub, delete it to avoid keeping obsolete routes. The included Streamlit configuration also hides automatic multipage navigation so only the custom sidebar navigation is shown.

## Accuracy

The APRIL and L’Harmoni pages require the controlled Excel input template. Missing project data is not estimated from the operational attendance workbook.
