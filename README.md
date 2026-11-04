# Microsoft Fabric for Data Analysts: OSFI demo kit

> **SYNTHETIC DATA · for training only · no OSFI data.**
> All 40 institutions and every supervisory lead are fictitious. Watch thresholds are **internal watch thresholds (illustrative)**, not OSFI regulatory minimums, targets or guidance.

| | |
|---|---|
| Session | "Microsoft Fabric for Data Analysts" for OSFI (Teams), session 5 of 6 of the *OSFI Fabric Knowledge Transfer* series. Thu Nov 5 2026, 9:30–11:30 a.m. ET: 90 min content, then 30 min Q&A |
| Presenter | Nicolas Soukoff, Microsoft Solution Engineer – Data Platform |
| Audience | OSFI data analysts and supervision analysts (Excel, Power BI, SQL, some SAS) |
| Format | Presenter-run live demos. The audience doesn't need Fabric access. 9 demos of 4–6 min each, all on one data path |
| Self-contained | Builds everything from scratch in **any** tenant. No dependency on earlier sessions, workspaces, lakehouses, repos or users |
| Numbers | Every number in this runbook comes from `docs/expected-values.md` (generated, seed 20261105). The deck quotes the same file |

---

## 1. What the kit shows: one data path, every analyst tool

```
 supervisory_watch_thresholds.xlsx (v1, then v2 in D5)          nb_fda_00_generate_data   (setup: all tables, 2026 Q3 missing for 10 late filers)
   lh_supervisory/Files/reference                               nb_fda_02_land_late_filings (D2: the late filings arrive)
        │ df_fda_watch_thresholds (Dataflow Gen2) [D5]                  │
        ▼                                                               ▼
 lh_supervisory (lakehouse, dbo Delta tables) ◄─────────────────────────┘
   dim_institution · dim_quarter · dim_province · fact_capital · fact_liquidity · fact_insurance_capital
   fact_mortgage_exposure (1.2 M rows) · supervisory_watch_thresholds        ◄── nb_fda_01_analyst_explore [D4]
        │
        ├── SQL analytics endpoint (read-only T-SQL, views vw_capital_ratios_quarterly, vw_mortgage_by_province) [D3]
        │        └── 3-part names ──► wh_analyst_sandbox (warehouse, writable: CTAS watchlist_2026q3, analyst_notes) [D3]
        │
        ├── sm_fda_supervisory        (Direct Lake, on the SQL analytics endpoint) [D1, D2]
        └── sm_fda_supervisory_import (Import, same tables and measures)        [D2]
                 │ (sm_fda_supervisory)
                 ├──► rpt_fda_supervisory_overview (Power BI report)          [D6]
                 ├──► rpt_fda_institution_return   (paginated report, .rdl)   [D6]
                 ├──► Copilot in Power BI (Prep data for AI)                   [D7]
                 └──► Excel (Analyze in Excel, Get Data, Export)              [D8]

 FDA-Analyst-Dev ── Git (GitHub <you>/fabric-analyst-workshop, /analyst-dev, main) [D9]
        └── dp_fda_analyst: Development ──► Test (FDA-Analyst-Test, lh_supervisory at scale 0.25) [D9]
```

### Demo map

| # | Demo (time) | Item(s) | The point |
|---|---|---|---|
| D1 | Semantic models (5 min) | sm_fda_supervisory | One governed model: relationships, measures with descriptions, DAX query view. Store components, not ratios. One model, many reports. Build permission |
| D2 | Direct Lake vs Import (6 min) | sm_fda_supervisory, sm_fda_supervisory_import, nb_fda_02_land_late_filings | Late filings land: Direct Lake shows **30 → 40** in seconds, Import stays at 30 until refresh |
| D3 | SQL analytics endpoint (6 min) | lh_supervisory SQL analytics endpoint, wh_analyst_sandbox | T-SQL on the lake, visual query, read-only vs writable, cross-database CTAS, connection string |
| D4 | Notebooks for analysts (5 min) | nb_fda_01_analyst_explore | `%%sql`, pandas, Data Wrangler, Semantic Link: same numbers as the model |
| D5 | Dataflows Gen2 (6 min) | df_fda_watch_thresholds | Excel → long table; v2 file changes **Institutions Below CET1 Watch 2 → 4** |
| D6 | Power BI and paginated (6 min) | rpt_fda_supervisory_overview, rpt_fda_institution_return | Interactive report vs pixel-perfect return, export to PDF/Excel |
| D7 | Copilot in Power BI (6 min) | report, DAX query view, standalone Copilot | Prompts, Prep data for AI, verified answer, caveats |
| D8 | Excel still works (4 min) | Analyze in Excel, Get Data | Same numbers in a PivotTable |
| D9 | Git and deployment (6 min) | Git, dp_fda_analyst | One change → one TMDL diff → deploy to Test with smaller Test data |

---

## 2. Prerequisites

| Need | Detail |
|---|---|
| Capacity | Fabric **F64 recommended** (works on **F2+**), region **Canada Central** (data-residency talking point), not paused. Note the capacity id (Admin portal > Capacity settings > Fabric capacity). **Copilot needs a paid F SKU (F2 or larger); it doesn't run on a Fabric trial capacity** |
| Fabric rights | Fabric administrator (tenant settings) and capacity admin or contributor (to assign workspaces). The presenter is Fabric admin in his own demo tenant |
| PowerShell 7 | `pwsh` 7.2+ |
| Modules | `Install-Module Az.Accounts -Scope CurrentUser` · `Install-Module SqlServer -MinimumVersion 22.0.0 -Scope CurrentUser` |
| Power BI Report Builder | Latest version, for D6 (Windows) |
| Excel | Microsoft 365 Apps desktop (Excel for Windows), signed in with the presenter account, for D8 |
| Git | A GitHub account with an empty repo `<you>/fabric-analyst-workshop` and a fine-grained personal access token (contents read/write on that repo). Azure DevOps works too |
| Power BI Desktop | Optional, for the PBIP view in D9 |
| Python 3 | Optional: `python tests/test_generator.py` rechecks the kit and the expected values locally |

### Licensing (read this)
- On capacities **smaller than F64**, anyone who **views** Power BI content needs **Power BI Pro or PPU**. The session is presenter-run, so **only the presenter needs Pro or PPU** (on F64+ viewers with a free licence can view).
- Lakehouse, warehouse, SQL analytics endpoint, notebook and dataflow experiences run on the capacity.
- **Copilot** needs a paid F SKU (F2+) or P SKU, the tenant settings in section 3, and is not available on trial capacities.

---

## 3. Tenant settings (Admin portal > Tenant settings)

Search for the keywords; names change between releases. Allow up to **15 minutes** for changes to apply.

| Setting (search keyword) | Value for the demo | Why |
|---|---|---|
| Users can create Fabric items | Enabled (presenter or org) | All items |
| **Users can use Copilot and other features powered by Azure OpenAI** | Enabled (presenter, or a security group) | D5 Copilot in Dataflow, D7 |
| **Data sent to Azure OpenAI can be processed outside your capacity's geographic region...** | **Decide deliberately.** Leave it off if Copilot is available in your capacity region; turn it on only if it isn't | OSFI data-residency question: know the state and explain it |
| Data sent to Azure OpenAI can be stored outside your capacity's geographic region (if shown) | Same decision | Copilot history/storage residency |
| **Users can synchronize workspace items with their Git repositories** | Enabled | D9 |
| **Users can sync workspace items with GitHub repositories** | Enabled (needed for GitHub; not for Azure DevOps) | D9 |
| Create and use Dataflow Gen2 with CI/CD, Git and deployment pipelines (only if your tenant still shows a switch) | Enabled | df_fda_watch_thresholds is a CI/CD dataflow |
| XMLA endpoint (capacity setting: Read Write) | Only if you use external tools (Tabular Editor, SSMS on the model). Not needed by the scripts | Optional |
| **Users can work with semantic models in Excel using a live connection** | Enabled | D8 Analyze in Excel |
| **Allow Live Connections** / Allow XMLA endpoints and Analyze in Excel with on-premises semantic models | Enabled | D8 |
| **Export to Excel** (and Export to .csv) | Enabled (default) | D6, D8 |
| Users can view Power BI items saved in OneDrive and SharePoint / OneLake catalog in Excel (if shown) | Enabled | D8 Get Data |
| Q&A (semantic model setting, not tenant) | **On** for sm_fda_supervisory (S10) | **Prep data for AI requires Q&A to be enabled on the semantic model** |
| Standalone Copilot / Copilot search (preview) (if shown) | Enabled | D7 optional |

---

## 4. Setup (do it the day before; about 1.5 h the first time)

```powershell
cd osfi-fabric-analyst-demo/scripts
Copy-Item config.sample.json config.json     # fill in tenantId, capacityId, presenterUpn (no secrets)
./01-Deploy-FdaEnvironment.ps1               # ~25-35 min, mostly Spark and model refreshes
```
Outputs go to `scripts/out/` (`fda-environment.json` with all ids, and the RDL with your tenant/model ids filled in).

**01 switches:** `-SkipTest`, `-SkipImportModel`, `-SkipPaginated`, `-SkipDataflow`, `-SkipPipeline`, `-ScaleFactor <n>` (Dev mortgage volume, default 1.0), `-RegenerateData` (rebuild all tables; undoes D2/D5), `-UseDeviceAuthentication`. It's idempotent: rerun it after fixing a failed step. Each failure prints the matching click fallback below.

| # | Step | Automated / Click | Time | How / fallback |
|---|---|---|---|---|
| S1 | Capacity running, region Canada Central, note the capacity id | Click | 5 min | Azure portal / Admin portal |
| S2 | Tenant settings (section 3) | Click | 10 min (+15 min to apply) | Admin portal |
| S3 | Local tools: PowerShell modules, Report Builder, Excel, GitHub repo `fabric-analyst-workshop` (empty, branch `main`) + token | Click | 10 min | section 2 |
| S4 | Workspace `FDA-Analyst-Dev` on the capacity | **Automated**: 01 | 1 min | Fallback: Workspaces > New workspace > `FDA-Analyst-Dev` > Advanced > License mode: Fabric capacity > your capacity |
| S5 | `lh_supervisory` (leave **Lakehouse schemas unticked**), `wh_analyst_sandbox` | **Automated**: 01 | 1 min | Fallback: New item > Lakehouse / Warehouse, exact names |
| S6 | Import `nb_fda_00_generate_data`, `nb_fda_01_analyst_explore`, `nb_fda_02_land_late_filings` (default lakehouse lh_supervisory, ids in the parameters cell) | **Automated**: 01 | 1 min | Fallback: workspace > Import > Notebook > From this computer > `notebooks/*.ipynb`; in each: Explorer > **Add lakehouse** > lh_supervisory. Leave `workspace_id`/`lakehouse_id` empty (the notebooks then use the default lakehouse) |
| S7 | Generate data: run nb_fda_00 | **Automated**: 01 | 5–10 min | Fallback: open nb_fda_00_generate_data > **Run all**. *Expected* last cell: fact_mortgage_exposure 1,211,265 rows; "2026 Q3 institutions reporting: 30 (deposit-taking 17, insurers 13)" |
| S8 | SQL analytics endpoint refresh; views (`sql/20_lh_views.sql`); warehouse table (`sql/30_wh_sandbox_setup.sql`) | **Automated**: 01 | 2 min | Fallback: lh_supervisory > SQL analytics endpoint > **Refresh**; New SQL query > paste sql/20 > Run. wh_analyst_sandbox > New SQL query > paste sql/30 > Run. *Expected:* 677 capital rows, 17 in 2026 Q3; 5 analyst_notes |
| S9 | Semantic models `sm_fda_supervisory` (Direct Lake) and `sm_fda_supervisory_import` (Import) from TMDL | **Automated**: 01 | 3 min | See S9 below |
| S10 | Model settings: credentials, refresh, **Q&A on**, permissions | Click | 5 min | See S10 below |
| S11 | Dataflow `df_fda_watch_thresholds`: sign in to the connection, check the preview | Automated upload + Click | 5 min | See S11 below and `dataflow/click-build.md` |
| S12 | Paginated report `rpt_fda_institution_return` | **Automated**: 01 | 1 min | Fallback: `paginated/README-paginated.md` (Report Builder > Publish) |
| S13 | `FDA-Analyst-Test` (lh_supervisory at scale 0.25, late filers missing) and deployment pipeline `dp_fda_analyst` (Development → Test) | **Automated**: 01 | 6–10 min | *Expected* in Test: fact_mortgage_exposure **302,936** rows, other tables as Dev initial. Fallback: create the workspace, lakehouse, import nb_fda_00, set `scale_factor = 0.25`, Run all. Workspaces > **Deployment pipelines** > Create pipeline `dp_fda_analyst` > stages *Development*, *Test* > assign the two workspaces |
| S14 | Report `rpt_fda_supervisory_overview` (spec below), then **Prep data for AI**, **Approved for Copilot**, verified answer | Click | 20 min | See S14 below |
| S15 | Git: connect FDA-Analyst-Dev, initial commit. Full rehearsal, fallback screenshots (section 6), then **Reset** (section 7) | Click | 30–60 min | See S15 below |

**S9 · semantic models.** 01 uploads `model/sm_fda_supervisory` with the SQL analytics endpoint server and endpoint id filled in (Direct Lake on the SQL analytics endpoint, same pattern as the previous kit), and `model/sm_fda_supervisory_import` with the server in the `SqlEndpoint` parameter (M: `Sql.Database(SqlEndpoint, "lh_supervisory")`, navigating `dbo.<table>`). Both are generated by `model/build_models.py` from one definition.
*Click fallback:* lh_supervisory > **New semantic model** > `sm_fda_supervisory` > tick the 8 tables > Confirm. Then open the data model and recreate relationships and measures from `model/sm_fda_supervisory/definition/` (relationships.tmdl, tables/*.tmdl). For the Import copy: Power BI Desktop > Get data > SQL Server > server = SQL analytics endpoint, database `lh_supervisory`, **Import** > 8 tables > TMDL view: paste the measures > Publish to FDA-Analyst-Dev as `sm_fda_supervisory_import`.

**S10 · model settings** (workspace > model > ... > **Settings**):
1. `sm_fda_supervisory_import` > **Data source credentials** > Edit credentials > **OAuth2**, privacy level *Organizational* > Sign in. Then **Refresh now**. *Expected:* refresh succeeds in about 1 min.
2. `sm_fda_supervisory` > Data source credentials / Gateway and cloud connections: signed in with OAuth2 (Direct Lake connection). **Refresh** once (framing).
3. `sm_fda_supervisory` > **Q&A** > *Turn on Q&A* = On. **Prep data for AI requires Q&A to be enabled on the semantic model.**
4. Check that "Keep your Direct Lake data up to date" is **On** for sm_fda_supervisory (default). D2 relies on it.
5. DAX query view on both models (open the model > **Write DAX queries**): run the D2 query; *Expected:* **30** on both.

**S11 · dataflow.** 01 uploads the query (`dataflow/df_fda_watch_thresholds/mashup.pq`) with your workspace and lakehouse ids. Open **df_fda_watch_thresholds**: if prompted, **Configure connection** > Lakehouse > OAuth2 > Sign in. *Expected* preview: **14 rows**, columns institution_type, metric, watch_threshold, effective_from_quarter, source_file; source_file = supervisory_watch_thresholds.xlsx. **Save** (don't add a destination yet: you set it live in D5). Pre-warm: open it once more an hour before the session. If the upload failed or the Source steps error, rebuild with `dataflow/click-build.md` (8 min).

**S14 · report rpt_fda_supervisory_overview** (presenter, about 12 min): sm_fda_supervisory > **Create report** > *Create a blank report*. View > Themes > **Browse for themes** > `theme/osfi-dark-theme.json`.

*Page "Capital and liquidity"*
- Slicers: `dim_quarter[quarter_label]` (dropdown, **single select**, set to **2026 Q3**), `dim_institution[institution_type]`, `dim_institution[sector]`.
- Cards (new card visual, 4 callouts): **Institutions Reporting**, **Filing Completeness %**, **Institutions Below CET1 Watch**, **Insurers Below Capital Watch**.
- Clustered column: X `institution_type`, Y **CET1 Ratio**, visual filter sector = Deposit-taking.
- Line chart *CET1 ratio trend*: X `quarter_label`, Y **CET1 Ratio**, legend `institution_type`, visual filter sector = Deposit-taking; Format > Edit interactions: the quarter slicer does **not** filter this visual.
- Table *Institutions*: `institution_name`, `institution_type`, **CET1 Ratio**, **CET1 Watch Threshold**, **CET1 Ratio QoQ Change (pp)**, **LCR**, **NSFR**, **Institutions Below CET1 Watch** (rename it "Below watch"). Conditional formatting: *Below watch* > Icons > rules: = 1 → red circle; *CET1 Ratio QoQ Change (pp)* > Font color > rules: < -0.5 → red (#FF6B6B). Sort by CET1 Ratio ascending.
- *Expected (initial, 2026 Q3):* Reporting **30**, Completeness **75.00%**, Below CET1 watch **1** (Cedarline Bank, 11.38% vs 11.5%), Insurers below **2**.

*Page "Mortgage exposure"*
- Slicer `quarter_label` (single select 2026 Q3, synced with page 1: View > Sync slicers).
- Cards: **Mortgage Balance** (CAD millions), **Arrears 90d Rate**, **Uninsured High-LTV Share**.
- Clustered bar: `dim_province[province_name]` × **Arrears 90d Rate**, sorted descending.
- Line chart: X `quarter_label` (not filtered by the slicer), Y **Arrears 90d Rate**, legend `dim_province[province_code]`, filter province_code in ON, BC, QC, AB.
- Stacked column: X `ltv_band`, Y **Mortgage Balance**, legend `insured_flag`.
- Matrix: rows `channel`, values **Uninsured High-LTV Share**, **Mortgage Balance**.
- *Expected (initial, 2026 Q3):* Mortgage Balance **839,202**, Arrears 90d Rate **0.37%**, Uninsured High-LTV Share **27.73%** (Broker 34.70% vs Branch 23.65%); ON 0.47% and BC 0.44% top the province bar.

*Page "Filing status"*
- Slicer `quarter_label` (2026 Q3). Cards **Institutions Reporting**, **Institutions Expected**, **Filing Completeness %**.
- Table: `institution_code`, `institution_name`, `institution_type`, `supervisory_lead`, `is_late_filer_2026q3`, **Institutions Reporting** (rename "Filed"). On `institution_name`: **Show items with no data**. Conditional formatting on *Filed*: Background color > rules: *is blank* → dark red (#7F1D1D).
- Clustered column: X `quarter_label` (last 8 quarters, filter quarter_index > 23), Y **Filing Completeness %**.
- Link to the paginated report, either:
  - Insert > **Paginated report** visual > Connect to report > `rpt_fda_institution_return` > Set parameters: *Institution* = `dim_institution[institution_code]` > See report. Selecting a row in the table drives it. **Or**
  - a **Button** > Action type *Web URL* > `https://app.powerbi.com/groups/<devWorkspaceId>/rdlreports/<reportId>?rp:Institution=FI007` (ids in `scripts/out/fda-environment.json`; append `&rp:Institution=FI011` for a second institution).
- *Expected (initial):* 30 / 40 / **75.00%**; 10 rows with a red *Filed* cell (the late filers).

Save as **rpt_fda_supervisory_overview** in FDA-Analyst-Dev.

*Copilot preparation (service, on sm_fda_supervisory):*
1. Model **Settings > Q&A** is on (S10).
2. Open sm_fda_supervisory > ribbon **Prep data for AI** (preview). For this **Direct Lake** model author it **in the Power BI service**: in Power BI Desktop, Prep data for AI authoring supports only Import, DirectQuery and composite models.
   - **AI data schema**: keep all 8 tables; untick hidden keys and the *Components* folders of the fact tables; keep every measure.
   - **AI instructions**: paste the text from `docs/copilot-prompts.md` (section "AI instructions").
   - **Apply**.
3. **Verified answer**: open rpt_fda_supervisory_overview > **Edit** > the *Below CET1 watch* card > **... > Set up a verified answer** > trigger phrases from `docs/copilot-prompts.md` > Apply. Save.
4. Model **Settings > Approved for Copilot** > tick > **Apply**. Changes can take a few minutes to apply.
5. Ask one rehearsal question (D7) to warm Copilot up.

**S15 · Git and rehearsal.**
1. FDA-Analyst-Dev > Workspace settings > **Git integration** > GitHub > add account (name, token, repo URL `https://github.com/<you>/fabric-analyst-workshop`) > branch **main**, folder **analyst-dev** > Connect and sync. *Expected:* all supported items committed; Source control shows **0 changes**. (Items or types that Git doesn't support yet are listed as unsupported: that's fine.)
2. Full rehearsal D1–D9; capture the screenshots in section 6.
3. Run **Reset** (section 7). Revert the D9 description change in the repo (commit "Reset demo") so Source control shows 0 changes.
4. Start a Spark session check: open nb_fda_02 and nb_fda_01 once on the morning of the session.

---

## 5. The 9 live demos (click-by-click)

Run order D1 → D9; the expected values assume this order. Ten minutes before D1: open nb_fda_01 and nb_fda_02 in two tabs and **start their Spark sessions** (run the first cell); open both models' DAX query view; open Report Builder with `scripts/out/rpt_fda_institution_return.rdl`; open Excel. Browser zoom 125% for Teams.

### D1 · Semantic models (5 min)
1. FDA-Analyst-Dev > **sm_fda_supervisory** > **Open data model** (web modeling) > Model view.
   *Expected:* 4 fact tables (fact_capital, fact_liquidity, fact_insurance_capital, fact_mortgage_exposure) → dim_institution and dim_quarter, fact_mortgage_exposure → dim_province; **supervisory_watch_thresholds** stands alone (looked up by institution_type). Keys hidden.
2. Select measure **CET1 Ratio** > Properties: description, format 0.00%, display folder *Capital*. Show `DIVIDE(SUM(fact_capital[cet1_capital]), SUM(fact_capital[rwa]))`.
3. **DAX query view** > new query:
   ```dax
   EVALUATE
   SUMMARIZECOLUMNS(
       dim_institution[institution_type],
       TREATAS({"2026 Q2"}, dim_quarter[quarter_label]),
       "CET1 Ratio", [CET1 Ratio],
       "Average of institution ratios (wrong)", AVERAGEX(VALUES(dim_institution[institution_id]), [CET1 Ratio])
   )
   ```
   *Expected:* D-SIB **13.28%** vs 13.35% · Other bank **14.13%** vs 13.95% · Trust and loan **15.04%** vs 15.02%.
4. Workspace > **Lineage view**: sm_fda_supervisory feeds rpt_fda_supervisory_overview and rpt_fda_institution_return. Model > ... > **Manage permissions**: *Build*.
- *Say:* **store components, not ratios**: the model divides sums, so any slice (type, peer group, province) is right. Every table and measure has a description, written for people and for Copilot. **One model, many reports**: Build permission lets an analyst create reports, Analyze in Excel and Copilot answers on the governed model without copying data.

### D2 · Direct Lake vs Import (6 min)
1. **sm_fda_supervisory** > DAX query view (tab 1) and **sm_fda_supervisory_import** > DAX query view (tab 2). Run in both:
   ```dax
   EVALUATE
   SUMMARIZECOLUMNS(
       dim_quarter[quarter_label],
       TREATAS({"2026 Q3"}, dim_quarter[quarter_label]),
       "Reporting", [Institutions Reporting]
   )
   ```
   *Expected:* **30** on both (Filing Completeness % 75.00%).
2. **nb_fda_02_land_late_filings** (session already started) > **Run all** (`mode = "land"`).
   *Expected:* "2026 Q3 institutions reporting: 30 -> 40"; fact_mortgage_exposure +7,128 rows (now 1,218,393).
3. Tab 1 (Direct Lake): run again. *Expected:* **40** within seconds (auto-update reframes the model; if it still shows 30 after ~30 s, model > **Refresh**: a reframe takes seconds).
4. Tab 2 (Import): run again. *Expected:* still **30**. Optional: model > **Refresh now** (~1 min) → 40.
5. Optional extra query on tab 1: add `"Below CET1 watch", [Institutions Below CET1 Watch]` → 2026 Q3: **1 → 2** (Driftwood Bank landed at 11.21%).
- *Say:* **Direct Lake** reads the Delta files in OneLake directly; a "refresh" is a metadata reframe, not a copy. **Import** copies data into the model: fastest queries, but data is only as fresh as the last refresh. **DirectQuery** sends every query to the source. Direct Lake on the SQL analytics endpoint (this model) **falls back to DirectQuery** for SQL views, SQL-endpoint security, or when a table exceeds the **SKU guardrails** (rows per table, model memory: smaller SKUs have lower limits). **Direct Lake on OneLake** (newer) reads OneLake without the SQL endpoint, has no DirectQuery fallback and can combine tables from several Fabric items.
- *Fallback:* screenshots D2-1..3. If nb_fda_02 is slow to start, say what it does and show the screenshot of the "30 -> 40" output.

### D3 · SQL analytics endpoint (6 min)
1. lh_supervisory > switch to **SQL analytics endpoint** > New SQL query > paste `sql/21_analyst_queries.sql`.
2. Run **BLOCK A**. *Expected:* dim_institution 40, fact_capital **682**, fact_mortgage_exposure **1,218,393** (after D2).
3. Run **BLOCK B**. *Expected (2026 Q3):* D-SIB **0.1309**, Other bank **0.1398**, Trust and loan **0.1496** (vs naive average 0.1318 / 0.1382 / 0.1487).
4. Run **BLOCK C** (LAG + RANK in peer group). *Expected* rank 1: Stonebridge Bank −0.64 (D-SIB), **Driftwood Bank −1.41** (Mid-size bank), Ashgrove Bank −0.17 (Small bank), Riverbend Trust and Loan −0.58.
5. Run **BLOCK D**. *Expected:* 10 late filers, all *Filed* (after D2).
6. **New visual query** > drag fact_capital and dim_institution > Merge on institution_id > Group by institution_type, Sum cet1_capital and rwa > **View SQL**. *Say:* no-code for some, SQL for others: same engine.
7. Run **BLOCK F1** (INSERT). *Expected:* **error**: the SQL analytics endpoint is read-only.
8. **wh_analyst_sandbox** > New SQL query > run **BLOCK E** (cross-database with 3-part names + CTAS). *Expected:* `dbo.watchlist_2026q3` = **2 rows**: Driftwood Bank 0.1121, Cedarline Bank 0.1138 (v1 threshold 0.115). Then **BLOCK F2**: insert works, 6 notes.
9. lh_supervisory SQL analytics endpoint > Settings > copy the **SQL connection string**. *Say:* SSMS, Azure Data Studio, Excel and Power BI Desktop connect with Entra ID; same permissions.
- *Say:* the lakehouse gets a **read-only T-SQL endpoint** automatically: views, security, cross-database joins. When analysts need to **write** (sandbox tables, notes, CTAS), use a **warehouse**. No copies between them: 3-part names.

### D4 · Notebooks for analysts (5 min)
1. **nb_fda_01_analyst_explore** (session started) > run cells one by one.
2. `%%sql` cell. *Expected (2026 Q2):* D-SIB 0.1328 · Other bank 0.1413 · Trust and loan 0.1504.
3. pandas cell > `describe()`. Then **Data** > **Launch Data Wrangler** > `pdf` > Filter quarter_key = 20263 > Group by institution_type, mean cet1_ratio > **Add code to notebook**.
4. QoQ cell. *Expected* top 3 drops in 2026 Q3: **Driftwood Bank −1.41**, Stonebridge Bank −0.64, Riverbend Trust and Loan −0.58; line chart by type.
5. **Semantic Link** cells: `list_measures("sm_fda_supervisory")`, then `evaluate_measure(... measure=["CET1 Ratio","Institutions Reporting"], groupby_columns=["dim_quarter[quarter_label]","dim_institution[institution_type]"])`. *Expected:* 2026 Q2 CET1 Ratio = the `%%sql` numbers (13.28%, 14.13%, 15.04%); 2026 Q3 Institutions Reporting 6 / 10 / 6 / 9 / 9.
6. Last cell writes **analyst_outliers**. *Expected:* **3 rows**.
- *Say:* **one definition, every tool**: Python reads the governed measures instead of re-coding CET1. Data Wrangler writes reviewable pandas code. Results become tables others can query.

### D5 · Dataflows Gen2 (6 min)
1. **df_fda_watch_thresholds** > walk the **Applied steps**: Source (lh_supervisory > Files/reference) → pick the latest `supervisory_watch_thresholds*.xlsx` → sheet *Watch thresholds* → **Skip 3 rows** → **Promote headers** → **Unpivot** metric columns → **Remove nulls** → **Types** → **Add source_file**. *Expected:* 14 rows.
2. **Add data destination** (bottom right of the query, or Home > Add data destination) > **Lakehouse** > FDA-Analyst-Dev > lh_supervisory > **Existing table** `supervisory_watch_thresholds` > Next > update method **Replace** > check column mapping (5 columns, same types) > Save settings. **Save** (publish).
3. **Refresh now** (~1–3 min). Talk through Copilot in Dataflow while it runs: Copilot pane > *"Add a column that flags thresholds above 100%"* > show the generated step > **Undo** (don't save it).
4. lh_supervisory > Files > **reference** > ... > **Upload** > Upload files > `excel/supervisory_watch_thresholds_v2.xlsx` (Overwrite if asked).
5. Dataflow > **Refresh now** again. *Expected:* source_file = supervisory_watch_thresholds_v2.xlsx; Other bank CET1 ratio **0.12**, Life insurer LICAT total **1.25**.
6. sm_fda_supervisory DAX query view (or the report): **Institutions Below CET1 Watch** 2026 Q3 **2 → 4** (+ Ashgrove Bank 11.78%, Larchmont Bank 11.91%); **Insurers Below Capital Watch 2 → 4** (+ Evergreen Mutual Life 122.2%, Summit Peak Life 123.6%).
- *Say:* the Excel file stays the business-owned input; the dataflow makes it a governed table, with every step visible. Settings worth knowing: **staging** (off for small loads), **fast copy** (large file/table loads), **refresh schedule**, refresh history, Dataflow Gen2 in **Git** and deployment pipelines.
- *Fallback:* if the destination can't be set live, configure it in rehearsal and only show it. If the refresh fails, run `02-Reset` later and show screenshot D5.

### D6 · Power BI and paginated reports (6 min)
1. **rpt_fda_supervisory_overview**: tour the 3 pages. *Expected (after D2 and D5, 2026 Q3):* Reporting **40**, Completeness **100.00%**, Below CET1 watch **4**, Insurers below **4**; Mortgage Balance **1,014,896**, Arrears 90d Rate 0.37%, ON **0.47%**, BC **0.44%**.
2. Build one visual live (Edit): on *Mortgage exposure* add a line chart X `quarter_label`, Y **Arrears 90d Rate**, legend `province_code` filtered ON, BC. *Expected:* ON 0.16% (2024 Q3) → 0.47% (2026 Q3), BC 0.17% → 0.44%. Don't save (or Undo).
3. **Power BI Report Builder** > `rpt_fda_institution_return.rdl` (from `scripts/out/`): show the data source (sm_fda_supervisory), the DAX dataset, the Institution parameter, the red-text expression, page break per institution. **Run**.
4. **File > Publish** > FDA-Analyst-Dev (overwrite). In the service open **rpt_fda_institution_return** > Institution = Cedarline Bank (FI007, default) > View report.
   *Expected:* "Quarterly supervisory return — Cedarline Bank (FI007)", 8 quarters 2024 Q4–2026 Q3, CET1 12.43% → **11.38%**. Watch threshold **12.0%** after D5 (v2): **5 red** CET1 cells (2025 Q3–2026 Q3). With v1 thresholds (after Reset): 11.5%, 2 red (2026 Q2 11.46%, 2026 Q3 11.38%).
5. Add **Driftwood Bank** to the parameter > View report: page 2, 2026 Q3 **11.21%** red. **Export** > PDF, then Excel.
- *Say:* **Power BI report** = interactive exploration on screen. **Paginated report** = fixed-layout, printable, multi-page return per institution, parameter-driven, exports cleanly to PDF/Excel/Word: the "supervisory return" pack. Same model, same numbers.

### D7 · Copilot in Power BI (6 min)
Prompts and the AI instructions text are in `docs/copilot-prompts.md`.
1. rpt_fda_supervisory_overview > **Copilot** pane > *"Summarize this page for a supervisor"* (page *Capital and liquidity*, 2026 Q3).
   *Expected:* mentions 40 institutions reporting (100%), 4 below CET1 watch (Driftwood Bank, Cedarline Bank, Ashgrove Bank, Larchmont Bank) and 4 insurers below capital watch. Wording varies.
2. **Edit** > Copilot > *"Create a page showing arrears 90d rate by province and quarter"*. *Expected:* new page; ON and BC highest in 2026 Q3 (0.47%, 0.44%). Keep it or delete it (reset checklist).
3. sm_fda_supervisory > **DAX query view** > **Copilot** (inline) > *"Show the five institutions with the largest CET1 ratio drop from 2026 Q2 to 2026 Q3"* > Run. *Expected:* Driftwood Bank −1.41 pp, Stonebridge Bank −0.64, Riverbend Trust and Loan −0.58, Northgate Trust −0.26, Silverpine Bank −0.24. Show the DAX it wrote (uses **CET1 Ratio**).
4. **Standalone Copilot** (Power BI home > Copilot; preview) > *"Which D-SIB had the biggest LCR drop in 2026 Q3 and by how much?"* *Expected:* **Stonebridge Bank, 148.2% → 118.7%** (about −29.5 pp, still above the 110% internal watch).
5. Show the preparation: model > **Prep data for AI**: AI data schema, **AI instructions**, verified answer (from S14); model Settings > **Approved for Copilot**.
- *Say / caveats:* Copilot uses the model's names, descriptions and the AI instructions, so **model hygiene is Copilot readiness**. **Prep data for AI requires Q&A on**; for a **Direct Lake** model author it in the service (Desktop authoring supports Import/DirectQuery/composite only). After Git/deployment edits to AI instructions, a Direct Lake model must be **refreshed in the service** to sync. Copilot output is a draft: verify numbers, check the DAX. Needs a paid F SKU; know the cross-geo processing setting (section 3). Respects the user's permissions and RLS.

### D8 · Excel still works (4 min)
1. sm_fda_supervisory > ... > **Analyze in Excel** (or Export > Analyze in Excel) > open in **Excel desktop** > Enable editing/content.
2. PivotTable: Rows `institution_type`, Columns `quarter_label` (filter 2026 Q2, 2026 Q3), Values **CET1 Ratio**, **Institutions Reporting**. *Expected:* 2026 Q3 D-SIB **13.09%**, Other bank **13.98%**, Trust and loan **14.96%**; 2026 Q2 13.28% / 14.13% / 15.04%. Same numbers as D1, D3, D4.
3. Excel > Data > **Get Data** > From Power Platform > **From Power BI** (OneLake catalog) > sm_fda_supervisory; or **From Database > From SQL Server Database** > server = SQL analytics endpoint, database lh_supervisory > `vw_capital_ratios_quarterly`.
4. rpt_fda_supervisory_overview > table visual > ... > **Export data** > Summarized data > .xlsx.
- *Say:* Excel is a first-class client of the governed model: live connection, no extract. Requires **Build** permission on the model and the Excel tenant settings.

### D9 · Git and deployment (6 min)
1. FDA-Analyst-Dev > **Source control**. *Expected:* 0 changes; repo `<you>/fabric-analyst-workshop`, branch main, folder analyst-dev.
2. sm_fda_supervisory > Open data model > measure **CET1 Ratio** > Description: append *" Reviewed for the 2026 Q3 cycle."* > it saves automatically.
3. **Source control** > *Changes*: **1** item (sm_fda_supervisory) > commit message *"CET1 Ratio: description reviewed"* > **Commit**.
4. GitHub > the commit > `analyst-dev/sm_fda_supervisory.SemanticModel/definition/tables/fact_capital.tmdl`: **one line changed** (the `///` description). *Say:* models are code: diffs, reviews, pull requests, history.
5. **Deployment pipelines** > **dp_fda_analyst** > Development vs Test > **Compare**: sm_fda_supervisory and rpt_fda_supervisory_overview *New* (or *Different*) > select both > **Deploy** > note *"Deploy reviewed model"* > Deploy.
6. FDA-Analyst-Test > rpt_fda_supervisory_overview. *Expected:* Institutions Reporting 2026 Q3 = **30** (late filers never landed in Test), Mortgage Balance 2026 Q2 **251,381** vs **994,808** in Dev: the deployed model **auto-binds** to Test's own lh_supervisory (VERIFY).
7. Show **Deployment rules** (stage Test > item sm_fda_supervisory_import > Parameter rule on `SqlEndpoint`): the way to repoint Import models per stage. Optional: Power BI Desktop > open the cloned repo's `.pbip`/model folder (PBIP + TMDL view).
- *Say:* Git for history and review; deployment pipelines to promote the **same** definitions from Dev to Test (to Prod) while each stage keeps its own data.
- *Fallback:* if the Test report shows Dev numbers, auto-binding didn't happen: set a **data source rule** on sm_fda_supervisory in the Test stage (Test SQL endpoint server and id from `scripts/out/fda-environment.json`) and deploy again; or show screenshot D9-4.

---

## 6. Fallback screenshots (capture during rehearsal)

Save in `shots/`. If a live step fails, say "here's what this looks like" and move on.

| Demo | Screenshots |
|---|---|
| D1 | Model view (star + disconnected thresholds) · CET1 Ratio properties with description · DAX query result (SUM/SUM vs average) · Lineage view |
| D2 | Both DAX query views at **30** · nb_fda_02 output "30 -> 40" · Direct Lake at **40** while Import at **30** |
| D3 | Blocks A–D results · visual query + View SQL · F1 error · E watchlist (2 rows) · connection string dialog |
| D4 | `%%sql` result · Data Wrangler with steps · QoQ chart · Semantic Link `evaluate_measure` output · analyst_outliers (3 rows) |
| D5 | Applied steps · destination settings (Replace) · source_file = v2 · Below CET1 Watch **4** / Insurers **4** |
| D6 | Each report page · Report Builder design · Cedarline Bank return (red cells) · page 2 Driftwood Bank · exported PDF |
| D7 | Copilot summary · Copilot-created page · DAX query view Copilot result (top 5) · standalone answer · Prep data for AI dialog · Approved for Copilot |
| D8 | PivotTable with CET1 Ratio by type · Get Data from Power BI · exported xlsx |
| D9 | Source control 1 change · GitHub diff (fact_capital.tmdl) · pipeline Compare · Test report (30, 251,381) · deployment rules |

---

## 7. Reset (between rehearsal and live) and teardown

**Reset for a clean live run**
```powershell
./02-Reset-FdaDemo.ps1      # ~10 min: late filings removed, thresholds v1, v1 Excel only, sandbox reset, models refreshed
```
*Expected afterwards:* Institutions Reporting 2026 Q3 = **30** on both models; Institutions Below CET1 Watch = **1**; Insurers Below Capital Watch = **2**; watchlist_2026q3 gone; 5 analyst_notes. Then work through the checklist the script prints:
- Git: Source control shows 0 changes; revert the D9 description change (commit) if needed.
- Copilot: delete Copilot-created report pages; new Copilot chat.
- Dataflow: keep or remove the destination you set in D5 (keep it if you want the fallback).
- Test stage: leave as is, or delete sm_fda_supervisory and rpt_fda_supervisory_overview from FDA-Analyst-Test so Compare shows *New* items.
- Spark: stop sessions in the Monitor hub.

**Teardown after the session**
```powershell
./99-Remove-FdaEnvironment.ps1      # deletes dp_fda_analyst, FDA-Analyst-Test, FDA-Analyst-Dev (type the names to confirm)
Remove-Item ./out -Recurse          # local ids and the filled RDL
```
Then delete or archive the GitHub repo, revert tenant settings you changed, and **pause the capacity** in the Azure portal.

---

## 8. Verify on the day (preview and fast-moving items)
- [ ] Capacity **not paused**; Spark sessions start (nb_fda_01, nb_fda_02) and finish within a minute or two.
- [ ] **Direct Lake auto-update** ("Keep your Direct Lake data up to date") is on and reframes within seconds (D2).
- [ ] sm_fda_supervisory_import credentials still valid (OAuth2 tokens expire: re-sign in if the refresh fails).
- [ ] **Dataflow Gen2** connection signed in; destination dialog labels; Copilot in Dataflow available (preview in some regions).
- [ ] **Prep data for AI (preview)**, **verified answers (preview)**, **Approved for Copilot**, **standalone Copilot (preview)**: labels and availability; Q&A on.
- [ ] **Copilot cross-geo** setting state (OSFI residency question).
- [ ] **Paginated report visual** in Power BI reports and the `rp:` URL parameter.
- [ ] **Git**: GitHub token valid; item types supported (paginated reports, Dataflow Gen2 CI/CD; preview status varies).
- [ ] **Deployment pipeline auto-binding** of the Direct Lake model to Test's lh_supervisory (D9 step 6).
- [ ] Analyze in Excel opens (Excel signed in with the presenter account).
- [ ] Items marked `VERIFY` in the scripts and definitions: lakehouse schema default, `refreshMetadata` endpoint, `RunNotebook` executionData body, `definition.pbism` version 4.0 and Direct Lake `Sql.Database(server, endpointId)` expression, Dataflow definition parts (`queryMetadata.json`, `mashup.pq`) and `Lakehouse.Contents` navigation keys, PBIDATASET connect string and the Imports API for .rdl, deployment pipeline create/assign/unassign APIs, notebook `runtime.context` keys. Each has a click fallback in section 4.

---

## 9. Files

```
osfi-fabric-analyst-demo/
├── README.md                              this runbook
├── docs/
│   ├── expected-values.md / .json         numbers quoted by the runbook and the deck (generated)
│   ├── demo-script-cheatsheet.md          one-page demo card
│   └── copilot-prompts.md                 D7 prompts, AI instructions, verified answer
├── data_gen/
│   ├── gen_supervisory_data.py            deterministic generator (seed 20261105), pure Python
│   └── expected_values.py                 computes docs/expected-values.*
├── excel/
│   ├── supervisory_watch_thresholds.xlsx      v1 (also dropped into lh_supervisory/Files/reference by nb_fda_00)
│   ├── supervisory_watch_thresholds_v2.xlsx   v2 for D5
│   └── build_excel.py
├── scripts/
│   ├── config.sample.json                 copy to config.json (no secrets)
│   ├── FdaCommon.ps1                      shared REST/auth/LRO/SQL helpers
│   ├── 01-Deploy-FdaEnvironment.ps1       everything in section 4 marked Automated
│   ├── 02-Reset-FdaDemo.ps1               back to the pre-session state
│   └── 99-Remove-FdaEnvironment.ps1       delete pipeline and both workspaces
├── notebooks/
│   ├── nb_fda_00_generate_data.ipynb      tables + reference Excel (embeds the generator)
│   ├── nb_fda_01_analyst_explore.ipynb    LIVE D4
│   ├── nb_fda_02_land_late_filings.ipynb  LIVE D2 (mode land / reset)
│   └── build_notebooks.py
├── sql/
│   ├── 20_lh_views.sql                    views on the SQL analytics endpoint
│   ├── 21_analyst_queries.sql             LIVE D3 blocks A-F with expected results
│   └── 30_wh_sandbox_setup.sql            wh_analyst_sandbox.dbo.analyst_notes (5 rows)
├── model/
│   ├── build_models.py                    one builder, two models
│   ├── sm_fda_supervisory/                Direct Lake TMDL (definition.pbism + definition/...)
│   └── sm_fda_supervisory_import/         Import TMDL
├── dataflow/
│   ├── df_fda_watch_thresholds/           mashup.pq + queryMetadata.json
│   └── click-build.md                     full UI fallback
├── paginated/
│   ├── rpt_fda_institution_return.rdl     RDL 2016, PBIDATASET on sm_fda_supervisory
│   ├── build_rdl.py
│   └── README-paginated.md
├── theme/osfi-dark-theme.json             Power BI theme (black, teal #1FB58F / #2DD4A7)
└── tests/test_generator.py                python tests/test_generator.py (pytest optional)
```

To change the data: edit `data_gen/gen_supervisory_data.py`, then run `python notebooks/build_notebooks.py`, `python data_gen/expected_values.py`, `python excel/build_excel.py`, `python model/build_models.py`, `python paginated/build_rdl.py` and `python tests/test_generator.py`. **The generator is frozen for the Nov 5 2026 session**: the deck quotes these values.
