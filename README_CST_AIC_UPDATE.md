# GLOW KPI Dashboard — CST/AIC Project KPI Update

This is a drop-in update for the existing Streamlit repository.

## What this adds

- A new Streamlit page: **CST Project KPIs**.
- Project APRIL tracking across all four centres.
- Project L'Harmoni tracking only for GLOW Bukit Batok and GLOW Nanyang.
- Actual-versus-target reporting for the CST application indicators.
- Strict data validation, exception logs and traceable calculation details.
- A controlled Excel input template.
- An AIC export lock that prevents official export when critical errors, missing KPI sources or required approvals remain.
- Separate calculations for APRIL onboarding and APRIL beneficiary-table counts, with annual targets shown year by year rather than combined across years.
- Both unique-senior and risk-flag APRIL validation calculations, with the selected official denominator recorded.
- L'Harmoni outcomes based only on approved classifications within the approved follow-up window. The code does not interpret clinical scores.

## Files to add to the repository

Copy these paths into the root of `GLOW_KPI_Dashboard`:

```text
cst_kpi_core.py
pages/2_CST_Project_KPIs.py
templates/CST_KPI_Data_Template.xlsx
tests/test_cst_kpi_core.py
```

Do not place the page beside `app.py`. It must remain inside the `pages` folder so Streamlit registers it as a second page automatically.

## Installation using GitHub web interface

1. Open the repository.
2. Select **Add file → Upload files**.
3. Upload `cst_kpi_core.py`.
4. Create/upload the `pages` and `templates` folders with the files above.
5. Commit the changes.
6. Streamlit Community Cloud will redeploy from the repository.

The existing `app.py` and `utils.py` do not need to be replaced. This keeps the operational dashboard stable while adding the grant-reporting page separately.

## Controlled workbook workflow

1. Open the new **CST Project KPIs** page.
2. Download the controlled input template from the page.
3. Populate the six recognised data sheets. Do not alter their sheet names or required column names.
4. Upload the completed template.
5. Resolve every critical validation issue.
6. Enter the approved reporting period, APRIL denominator definition, L'Harmoni follow-up rule, centre-mapping approval and reviewer details.
7. Reconcile the displayed totals against source records.
8. Export the AIC workbook only after the page shows **PASSED**.

## Important governance point

The CST application beneficiary tables name SEEN locations, while the confirmed operational mapping supplied for this dashboard assigns L'Harmoni to the two GLOW centres. The page therefore requires a named approver and approval reference before an AIC-labelled export is enabled.

## Tests

Run from the repository root:

```bash
python -m pytest -q
```

The included tests cover clean KPI calculation, rejection of SEEN L'Harmoni records, official-export approval controls, annual target separation, outcome denominator rules, and controlled-template parsing.

## Accuracy safeguards

- Unknown centre values are not guessed.
- Missing identifiers and invalid dates are critical errors.
- Duplicate source record IDs are critical errors.
- L'Harmoni records from SEEN centres are blocked.
- Missing KPI source sheets block official export.
- Zero eligible denominators are displayed as not calculable, not as 0%.
- Outcome classifications require approval, a reviewer and a rule version.
- Every exported number includes supporting calculation detail and an exception/source register.
