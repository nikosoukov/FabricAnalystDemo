# Copilot prompts, AI instructions and verified answer (D7)
**SYNTHETIC DATA · for training only · no OSFI data.** Expected answers assume D2 (late filings landed) and D5 (v2 thresholds) ran before D7. Copilot wording varies; check the numbers.

## Preparation (S14, once)
1. sm_fda_supervisory > Settings > **Q&A** on. *Prep data for AI requires Q&A to be enabled on the semantic model.*
2. sm_fda_supervisory is **Direct Lake**: author Prep data for AI **in the Power BI service** (Semantic model > **Prep data for AI** ribbon button > Apply). Power BI Desktop authoring supports only Import, DirectQuery and composite models.
3. **AI data schema**: all 8 tables; untick hidden keys and the fact tables' *Components* folders; keep all measures.
4. **AI instructions**: paste the block below > **Apply**.
5. **Verified answer**: rpt_fda_supervisory_overview > **Edit** > card *Institutions Below CET1 Watch* > **... > Set up a verified answer** > add the trigger phrases below > Apply > Save the report.
6. Settings > **Approved for Copilot** > tick > **Apply**. Changes can take a few minutes to apply.
7. After any Git or deployment-pipeline change to the AI instructions, **refresh the Direct Lake model in the service** so they sync (at most once a day is enough).

## AI instructions (paste as is)
```
This model holds SYNTHETIC supervisory data for training. All institutions are fictitious; never present results as real OSFI data.
Users are prudential supervision analysts. Answer concisely, give the quarter you used, and show ratios as percentages with two decimals.
Quarters: use dim_quarter[quarter_label] (for example "2026 Q3"). The current quarter is 2026 Q3 (dim_quarter[is_current] = TRUE). When no quarter is given, use 2026 Q3 and say so.
Ratios: always use the measures (CET1 Ratio, Tier 1 Ratio, Total Capital Ratio, Leverage Ratio, LCR, NSFR, Insurance Capital Ratio). They divide sums of components; never average institution ratios.
CET1, leverage, LCR and NSFR apply to deposit-taking institutions (D-SIB, Other bank, Trust and loan). Insurance Capital Ratio applies to insurers: LICAT total for life insurers, MCT for P&C insurers; don't mix the two in one number.
"Watch", "watch list" or "below threshold" means the internal watch thresholds in supervisory_watch_thresholds (Institutions Below CET1 Watch, Insurers Below Capital Watch). They are internal and illustrative, NOT OSFI regulatory minimums; say so when you use them.
"Late filers" or "missing returns" means dim_institution[is_late_filer_2026q3] or Filing Completeness % below 100%.
Quarter-over-quarter change in CET1 is CET1 Ratio QoQ Change (pp), in percentage points.
Mortgage balances are a stock in CAD millions: always filter to one quarter. Arrears 90d Rate and Uninsured High-LTV Share are shares of balance.
```

## Prompts and expected answers
| Where | Prompt | Expected |
|---|---|---|
| Report Copilot pane, page *Capital and liquidity* (2026 Q3) | **Summarize this page for a supervisor** | 40 institutions reporting (100.00%); 4 below the internal CET1 watch: Driftwood Bank 11.21%, Cedarline Bank 11.38%, Ashgrove Bank 11.78%, Larchmont Bank 11.91% (Other bank watch 12.0%); 4 insurers below capital watch |
| Report, Edit mode, Copilot | **Create a page showing arrears 90d rate by province and quarter** | New page; Ontario 0.47% and British Columbia 0.44% highest in 2026 Q3, up from 0.16% / 0.17% in 2024 Q3 |
| sm_fda_supervisory > DAX query view > Copilot | **Show the five institutions with the largest CET1 ratio drop from 2026 Q2 to 2026 Q3** | Driftwood Bank −1.41 pp (12.62% → 11.21%), Stonebridge Bank −0.64, Riverbend Trust and Loan −0.58, Northgate Trust −0.26, Silverpine Bank −0.24 |
| Standalone Copilot (preview) | **Which D-SIB had the biggest LCR drop in 2026 Q3 and by how much?** | Stonebridge Bank: 148.2% → 118.7% (−29.5 pp), still above the 110% internal watch |
| Standalone Copilot / report pane | **Which institutions have not filed for 2026 Q3?** | Before D2: 10 (Borealis Bank Group, Driftwood Bank, Pembrook Bank, Old Mill Trust, Sandstone Mortgage and Loan, Northwind Life, Tamarack Life, Stormguard Insurance, Snowfield Insurance, Timberline Mutual). After D2: none |
| Report pane | **Which insurers are below their capital watch threshold?** | Prairie Crown Life (LICAT 117.1%), Evergreen Mutual Life (122.2%), Summit Peak Life (123.6%), Kettle Lake General (MCT 176.1%) with v2 |
| Report pane (verified answer) | **How many institutions are on the CET1 watch list?** | Returns the verified card *Institutions Below CET1 Watch* (4 after D5) |

## Verified answer: trigger phrases
- How many institutions are on the CET1 watch list?
- Institutions below CET1 watch
- CET1 watch list count
- Which banks are below the CET1 watch threshold?

## Caveats to say out loud
- Copilot is only as good as the model: names, descriptions, AI instructions. Model hygiene = Copilot readiness.
- Output is a draft: verify numbers and the generated DAX before you share.
- Copilot runs on a paid F SKU (F2+), not a trial. Know the tenant setting on cross-geo processing (Canada Central).
- Copilot uses the signed-in user's permissions (RLS, Build).
