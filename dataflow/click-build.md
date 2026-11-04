# df_fda_watch_thresholds: click-build fallback (about 8 min)
**SYNTHETIC DATA · for training only · no OSFI data.** Use this if `01-Deploy-FdaEnvironment.ps1` couldn't upload the dataflow definition, or if the Source steps error in your tenant (`Lakehouse.Contents` navigation keys are marked VERIFY in `mashup.pq`).

1. FDA-Analyst-Dev > **New item** > **Dataflow Gen2** > name `df_fda_watch_thresholds` (keep *Git integration, deployment pipelines and Public API scenarios* ticked if offered) > Create.
2. **Get data** > **Lakehouse** (or OneLake catalog) > sign in (OAuth2) > FDA-Analyst-Dev > **lh_supervisory** > **Files** > **reference** > `supervisory_watch_thresholds.xlsx` > sheet **Watch thresholds** > Create.
3. Rename the query `supervisory_watch_thresholds`.
4. If the navigator already promoted headers or typed columns, delete those auto steps (Applied steps > x) so you start from the raw sheet (Column1 … Column8).
5. Home > **Remove rows** > **Remove top rows** > 3. (Rows 1–3 = title, "Last reviewed", blank.)
6. Home > **Use first row as headers**.
7. Select `institution_type` and `effective_from_quarter` > Transform > **Unpivot columns** > **Unpivot other columns**. Rename *Attribute* → `metric`, *Value* → `watch_threshold`.
8. Filter `watch_threshold`: untick (null) and empty (**remove nulls**).
9. Types: `institution_type` Text, `metric` Text, `watch_threshold` **Decimal number**, `effective_from_quarter` **Whole number** (Int64).
10. Add column > **Custom column** `source_file` = `"supervisory_watch_thresholds.xlsx"` (type Text). In the scripted version the name comes from the file itself, which is why the v2 file shows `supervisory_watch_thresholds_v2.xlsx`; in this click version, either change the Source step to the v2 file in D5, or edit this constant.
11. Choose columns in this order: institution_type, metric, watch_threshold, effective_from_quarter, source_file. *Expected:* **14 rows**.
12. **Save** (publish). The destination is set live in D5: **Add data destination** > Lakehouse > lh_supervisory > **Existing table** `supervisory_watch_thresholds` > update method **Replace** > column mapping (5 columns) > Save settings > Save.

**D5 with the click version:** upload `supervisory_watch_thresholds_v2.xlsx` to Files/reference, then in the dataflow change the file selected in the navigation step to the v2 file (and `source_file` text), Save, Refresh. *Expected:* Institutions Below CET1 Watch 2026 Q3 **2 → 4**, Insurers Below Capital Watch **2 → 4**.

**Output schema must match** `lh_supervisory.dbo.supervisory_watch_thresholds` written by nb_fda_00: `institution_type` string, `metric` string, `watch_threshold` double, `effective_from_quarter` bigint (Int64), `source_file` string. Thresholds are internal watch thresholds (illustrative), not OSFI regulatory minimums.
