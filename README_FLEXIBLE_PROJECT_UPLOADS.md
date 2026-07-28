# Flexible APRIL and L'Harmoni source uploads

The original Centre Dashboard UI and calculations remain unchanged.

The APRIL and L'Harmoni sidebar pages now accept one or more differently structured, **structured data files**:

- Excel: `.xlsx`, `.xls`, `.xlsm` — every sheet is scanned
- Delimited files: `.csv`, `.tsv`, `.txt`
- JSON: `.json`
- ZIP: `.zip` containing any of the formats above

The controlled Excel template remains available but is optional.

## Accuracy controls

- The extractor matches recognised source columns to a controlled field dictionary and displays the mapping in an audit expander.
- Missing or ambiguous KPIs display **Data unavailable**, never an assumed zero.
- Ordinary attendance is not automatically treated as APRIL or L'Harmoni participation. The project must be explicitly identified by the file, sheet, project/activity field, or project-specific source columns.
- APRIL includes all four centres. A generic Bukit Batok/Nanyang APRIL record may contribute to the project total but remains labelled as service unspecified.
- L'Harmoni includes only records explicitly identified as GLOW Bukit Batok or GLOW Nanyang. SEEN and generic location-only rows are excluded.
- L'Harmoni outcomes require an explicit classification, follow-up date, approval indicator and rule version.
- PDF/image files are intentionally unsupported because automatic extraction is not sufficiently reliable for official AIC KPI calculations.

## GitHub upload

Upload all extracted files to the repository root. Keep Streamlit's main file path as `app.py`. Do not create a `pages` folder.
