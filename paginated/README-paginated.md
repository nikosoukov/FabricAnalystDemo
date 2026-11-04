# rpt_fda_institution_return: paginated report
**SYNTHETIC DATA · for training only · no OSFI data.**

Quarterly supervisory return per institution: last 8 quarters of CET1, Tier 1, total capital, leverage, LCR, NSFR and the insurer capital ratio (LICAT total / MCT), with the internal watch threshold. Letter portrait, one page per institution, red text when a ratio is below its internal watch threshold (illustrative, not an OSFI regulatory minimum). Footer: *SYNTHETIC DATA · for training only · no OSFI data · Page x of y*.

| Element | Value |
|---|---|
| Data source | `sm_fda_supervisory` (Power BI semantic model, DataProvider `PBIDATASET`) |
| Datasets | `dsInstitutions` (parameter list) · `dsReturn` (DAX, `@InstitutionList` = `Join(Parameters!Institution.Value, "|")`, `PATHCONTAINS`) |
| Parameter | `Institution` (multi-value, default **FI007 = Cedarline Bank**) |
| Source of truth | `paginated/build_rdl.py` (regenerates the .rdl) |

## Automated (01-Deploy-FdaEnvironment.ps1, S12)
The script replaces `__TENANT_ID__` and `__DATASET_ID__` in the connect string, saves `scripts/out/rpt_fda_institution_return.rdl` and uploads it with the Power BI **Imports API** (`datasetDisplayName=rpt_fda_institution_return.rdl`). VERIFY: connect string format; if the report errors on the data source, use the Report Builder path.

## Report Builder (D6 and fallback)
1. Open **Power BI Report Builder** > File > Open > `scripts/out/rpt_fda_institution_return.rdl` (ids filled) or `paginated/rpt_fda_institution_return.rdl`.
2. If asked, sign in. **Data Sources** > `sm_fda_supervisory` > Properties > **Build** / Browse > Power BI semantic models > FDA-Analyst-Dev > **sm_fda_supervisory** > OK. (This rewrites the connect string for your tenant.)
3. **Run**. *Expected (Cedarline Bank, v1 thresholds):* 2024 Q4 12.43% … 2026 Q1 11.62%, **2026 Q2 11.46%** and **2026 Q3 11.38%** in red, watch threshold 11.5%. *After D5 (v2):* threshold 12.0%, 5 red quarters (2025 Q3 11.89% to 2026 Q3).
4. File > **Publish** > Power BI service > FDA-Analyst-Dev > name `rpt_fda_institution_return` > Overwrite.
5. In the service: open the report > Institution = Cedarline Bank, Driftwood Bank > **View report** > page 2: Driftwood Bank 2026 Q3 **11.21%** red (after D2; before D2 the row reads "2026 Q3 (not filed)"). **Export** > PDF / Excel.

## Fallback in the service (no Report Builder)
sm_fda_supervisory > ... > **Create paginated report** (or in a Power BI report: a table visual > ... > *Export to paginated report*): pick `dim_institution[institution_name]`, `dim_quarter[quarter_label]`, **CET1 Ratio**, **Tier 1 Ratio**, **LCR**, **NSFR**, **Insurance Capital Ratio**, **CET1 Watch Threshold** > filter quarter_label to the last 8 quarters > **Save** as `rpt_fda_institution_return`. Less formatting, same numbers; then export to PDF.
