# SYNTHETIC DATA · for training only · no OSFI data
"""
build_notebooks.py - writes the three Fabric notebooks (nbformat 4, Fabric PySpark kernel):

  nb_fda_00_generate_data.ipynb      tables + Excel reference file (embeds the generator)
  nb_fda_01_analyst_explore.ipynb    LIVE D4: SQL, pandas, Data Wrangler, Semantic Link
  nb_fda_02_land_late_filings.ipynb  LIVE D2: append / remove the 10 late filers' 2026 Q3 rows

The generator cell is a verbatim copy of data_gen/gen_supervisory_data.py (minus its
__main__ block), so local tests and Fabric produce identical numbers.
tests/test_generator.py fails if the copy drifts. Run:  python notebooks/build_notebooks.py
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
BANNER = "SYNTHETIC DATA · for training only · no OSFI data"
GEN_PATH = os.path.join(KIT, "data_gen", "gen_supervisory_data.py")
EMBED_BEGIN = "# ===== BEGIN embedded copy of data_gen/gen_supervisory_data.py (do not edit here; run notebooks/build_notebooks.py) ====="
EMBED_END = "# ===== END embedded copy ====="

METADATA = {
    "kernel_info": {"name": "synapse_pyspark"},
    "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark", "language": "Python"},
    "language_info": {"name": "python"},
    "microsoft": {"language": "python", "language_group": "synapse_pyspark"},
    "dependencies": {},
}


def generator_source() -> str:
    with open(GEN_PATH, encoding="utf-8") as f:
        src = f.read()
    return src.split('\nif __name__ == "__main__":')[0].rstrip() + "\n"


def embedded_generator_cell_source() -> str:
    return f"{EMBED_BEGIN}\n{generator_source()}{EMBED_END}\n"


def _lines(text: str) -> list:
    text = text.strip("\n")
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + [parts[-1]]


class NB:
    def __init__(self):
        self.cells = []

    def md(self, text):
        self.cells.append({"cell_type": "markdown", "metadata": {}, "source": _lines(text), "id": f"c{len(self.cells):02d}"})

    def code(self, text, parameters=False):
        meta = {"tags": ["parameters"]} if parameters else {}
        self.cells.append({"cell_type": "code", "execution_count": None, "metadata": meta, "outputs": [],
                           "source": _lines(text), "id": f"c{len(self.cells):02d}"})

    def write(self, name):
        nb = {"cells": self.cells, "metadata": METADATA, "nbformat": 4, "nbformat_minor": 5}
        path = os.path.join(HERE, f"{name}.ipynb")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(nb, f, indent=1, ensure_ascii=False)
            f.write("\n")
        return path


# --------------------------------------------------------------------------- shared Spark helpers
HELPERS = f'''
# {BANNER}
# Spark helpers: absolute OneLake paths when ids are given, else the notebook's default lakehouse.
import os
import notebookutils
from pyspark.sql import types as T

ONELAKE = "onelake.dfs.fabric.microsoft.com"
SPARK_TYPES = {{"int": T.IntegerType(), "long": T.LongType(), "double": T.DoubleType(),
               "string": T.StringType(), "boolean": T.BooleanType(), "date": T.DateType()}}
spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")


def _context(key):
    try:
        return notebookutils.runtime.context.get(key)   # VERIFY: context key names can vary by runtime
    except Exception:
        return None


def resolve_root(ws_id, lh_id):
    """abfss root of lh_supervisory, or None = use the default lakehouse.
    Ids that belong to ANOTHER workspace are ignored (e.g. a copy deployed by dp_fda_analyst),
    so this notebook can never write into Dev from Test."""
    if ws_id and lh_id:
        here = _context("currentWorkspaceId")
        if here and here.lower() != ws_id.lower():
            print(f"[warn] workspace_id parameter {{ws_id}} is not this workspace ({{here}}): using the default lakehouse.")
            return None
        return f"abfss://{{ws_id}}@{{ONELAKE}}/{{lh_id}}"
    return None


ROOT = resolve_root(workspace_id, lakehouse_id)
if ROOT is None and not _context("defaultLakehouseId"):
    print("[warn] No ids and no default lakehouse detected. Attach lh_supervisory (Explorer > Add lakehouse) if the next cells fail.")
print("target:", ROOT or "default lakehouse (attach lh_supervisory)")


def table_path(table):
    return f"{{ROOT}}/Tables/{{table}}" if ROOT else None


def files_path(rel):
    return f"{{ROOT}}/Files/{{rel}}" if ROOT else f"Files/{{rel}}"


def spark_schema(table):
    return T.StructType([T.StructField(c, SPARK_TYPES[t], True) for c, t in TABLE_SCHEMAS[table]])


def write_table(pdf, table, mode="overwrite"):
    sdf = spark.createDataFrame(pdf, schema=spark_schema(table))
    w = sdf.write.format("delta").mode(mode)
    if mode == "overwrite":
        w = w.option("overwriteSchema", "true")
    if ROOT:
        w.save(table_path(table))
    else:
        w.saveAsTable(table)


def read_table(table):
    return spark.read.format("delta").load(table_path(table)) if ROOT else spark.read.table(table)


def sql_ref(table):
    return f"delta.`{{table_path(table)}}`" if ROOT else table
'''

# --------------------------------------------------------------------------- nb_fda_00
def build_nb00():
    nb = NB()
    nb.md(f"""
# nb_fda_00_generate_data
**{BANNER}**

Builds every table of `lh_supervisory` (dbo, Delta) from a deterministic generator (seed 20261105) and drops the
reference Excel file `Files/reference/supervisory_watch_thresholds.xlsx` that the Dataflow Gen2 `df_fda_watch_thresholds` reads.

* Run by `scripts/01-Deploy-FdaEnvironment.ps1` (Dev: scale_factor 1.0, Test: 0.25). You don't run it live.
* Initial state: 2026 Q3 is **missing for the 10 late filers** (30 of 40 institutions reporting). `nb_fda_02_land_late_filings` lands them in D2.
* `only_reset_thresholds=True` only rewrites `supervisory_watch_thresholds` with the v1 values and re-copies the v1 Excel file (used by `02-Reset-FdaDemo.ps1`).
* Watch thresholds are *internal watch thresholds (illustrative)*, not OSFI regulatory minimums. All institutions are fictitious.
""")
    nb.code(f"""
# {BANNER}
# Parameters (filled by 01-Deploy-FdaEnvironment.ps1; empty ids = use the default lakehouse)
workspace_id = ""
lakehouse_id = ""
scale_factor = 1.0
only_reset_thresholds = False
""", parameters=True)
    nb.md("## Generator\nVerbatim copy of `data_gen/gen_supervisory_data.py`. Pure Python (numpy + pandas): the same code computes the expected values in `docs/expected-values.md`.")
    nb.code(embedded_generator_cell_source())
    nb.code(HELPERS)
    nb.code(f"""
# {BANNER}
# Write the v1 Excel reference file to lh_supervisory/Files/reference (source of df_fda_watch_thresholds).
def write_reference_xlsx():
    local_dir = os.path.abspath("fda_work")            # driver-local scratch folder
    os.makedirs(local_dir, exist_ok=True)
    local = build_thresholds_workbook("v1", os.path.join(local_dir, THRESHOLD_FILES["v1"]))
    notebookutils.fs.mkdirs(files_path("reference"))
    for version in ("v1", "v2"):                       # v2 may be left over from a rehearsal (D5)
        try:
            notebookutils.fs.rm(files_path("reference/" + THRESHOLD_FILES[version]))
        except Exception:
            pass
    notebookutils.fs.cp("file:" + local, files_path("reference/" + THRESHOLD_FILES["v1"]))
    print("reference file:", files_path("reference/" + THRESHOLD_FILES["v1"]))
""")
    nb.code(f"""
# {BANNER}
import time

reset_only = str(only_reset_thresholds).strip().lower() in ("true", "1", "yes")
t0 = time.time()
if reset_only:
    write_table(build_watch_thresholds("v1"), "supervisory_watch_thresholds")
    print("supervisory_watch_thresholds reset to v1")
else:
    data = generate_all(scale_factor=float(scale_factor))
    for name, pdf in data.items():
        write_table(pdf, name)
        print(f"{{name:32s}} {{len(pdf):>10,d}} rows written")
write_reference_xlsx()
print(f"done in {{time.time() - t0:.0f}} s")
""")
    nb.code(f"""
# {BANNER}
# Row counts as stored, and 2026 Q3 filings (expected: 30 reporting before nb_fda_02 runs)
for name in TABLE_ORDER:
    print(f"{{name:32s}} {{read_table(name).count():>10,d}}")
q3_dt = read_table("fact_capital").where(f"quarter_key = {{CURRENT_QUARTER_KEY}}").select("institution_id").distinct().count()
q3_in = read_table("fact_insurance_capital").where(f"quarter_key = {{CURRENT_QUARTER_KEY}}").select("institution_id").distinct().count()
print(f"2026 Q3 institutions reporting: {{q3_dt + q3_in}} (deposit-taking {{q3_dt}}, insurers {{q3_in}})")
""")
    nb.md("""
**Expected (Dev, scale_factor 1.0):** dim_institution 40 · dim_quarter 31 · dim_province 13 · fact_capital 677 · fact_liquidity 677 ·
fact_insurance_capital 553 · fact_mortgage_exposure 1,211,265 · supervisory_watch_thresholds 14 · 2026 Q3 reporting 30 (17 + 13).
**Test (0.25):** the same except fact_mortgage_exposure 302,936.

Next: refresh the SQL analytics endpoint metadata (the deploy script does it) so the tables appear for T-SQL and the semantic models.
""")
    return nb.write("nb_fda_00_generate_data")


# --------------------------------------------------------------------------- nb_fda_02
def build_nb02():
    nb = NB()
    nb.md(f"""
# nb_fda_02_land_late_filings
**{BANNER}**

**LIVE in D2 (Direct Lake vs Import).** The 10 late filers' 2026 Q3 returns "arrive": this notebook appends their rows to
fact_capital, fact_liquidity, fact_insurance_capital and fact_mortgage_exposure in `lh_supervisory`.

* `mode = "land"` (default): delete any existing late-filer 2026 Q3 rows, then append them. Idempotent: run it twice, same result.
* `mode = "reset"`: delete them only (back to 30 of 40 reporting). Used by `02-Reset-FdaDemo.ps1`.
* Rows come from the same generator as nb_fda_00, so values are identical to a full load.

*Expected:* Institutions Reporting 2026 Q3 goes from **30 to 40** in `sm_fda_supervisory` (Direct Lake) within seconds; `sm_fda_supervisory_import` stays at 30 until refreshed.
""")
    nb.code(f"""
# {BANNER}
# Parameters
mode = "land"          # "land" or "reset"
workspace_id = ""
lakehouse_id = ""
scale_factor = 1.0     # must match the scale nb_fda_00 used in this workspace (Dev 1.0)
""", parameters=True)
    nb.md("## Generator\nVerbatim copy of `data_gen/gen_supervisory_data.py`.")
    nb.code(embedded_generator_cell_source())
    nb.code(HELPERS)
    nb.code(f"""
# {BANNER}
import pandas as pd

mode = str(mode).strip().lower()
assert mode in ("land", "reset"), "mode must be 'land' or 'reset'"
LATE_IDS = late_filer_ids()


def q3_status():
    rows = []
    for t in FACT_TABLES:
        df = read_table(t).where(f"quarter_key = {{CURRENT_QUARTER_KEY}}")
        rows.append({{"table": t, "rows_2026q3": df.count(),
                     "institutions_2026q3": df.select("institution_id").distinct().count()}})
    return pd.DataFrame(rows).set_index("table")


before = q3_status()
before
""")
    nb.code(f"""
# {BANNER}
import time

t0 = time.time()
ids = ", ".join(str(i) for i in LATE_IDS)
for t in FACT_TABLES:                         # delete first = idempotent
    spark.sql(f"DELETE FROM {{sql_ref(t)}} WHERE quarter_key = {{CURRENT_QUARTER_KEY}} AND institution_id IN ({{ids}})")
if mode == "land":
    for t, pdf in generate_late_filings(scale_factor=float(scale_factor)).items():
        write_table(pdf, t, mode="append")
        print(f"{{t:26s}} +{{len(pdf):,d}} rows appended")
print(f"mode={{mode}} done in {{time.time() - t0:.0f}} s")
""")
    nb.code(f"""
# {BANNER}
after = q3_status()
summary = before.join(after, lsuffix="_before", rsuffix="_after")
reporting = {{"before": int(before.loc["fact_capital", "institutions_2026q3"] + before.loc["fact_insurance_capital", "institutions_2026q3"]),
             "after": int(after.loc["fact_capital", "institutions_2026q3"] + after.loc["fact_insurance_capital", "institutions_2026q3"])}}
print(f"2026 Q3 institutions reporting: {{reporting['before']}} -> {{reporting['after']}}")
summary
""")
    nb.md("""
**Expected after `land` (Dev):** fact_capital 17 → 22 institutions, fact_insurance_capital 13 → 18, fact_mortgage_exposure 2026 Q3 rows 32,175 → 39,303.
2026 Q3 institutions reporting **30 → 40**. After `reset`: back to 30.

Now switch to the DAX query view of `sm_fda_supervisory` and run the query again (D2 step 4).
""")
    return nb.write("nb_fda_02_land_late_filings")


# --------------------------------------------------------------------------- nb_fda_01
def build_nb01():
    nb = NB()
    nb.md(f"""
# nb_fda_01_analyst_explore
**{BANNER}**

**LIVE in D4: notebooks for analysts.** Default lakehouse: `lh_supervisory`. Each cell is short; together they run in under 2 minutes on F2 once the Spark session is up.

1. SQL in a notebook (`%%sql`)
2. pandas + Data Wrangler
3. Quarter-over-quarter change and a chart
4. Semantic Link: the model's measures from Python ("one definition, every tool")
5. Save the outliers as a table the team can query
""")
    nb.md("## 1. SQL in a notebook\nCET1 ratio by institution type for **2026 Q2**: SUM of capital / SUM of RWA (store components, not ratios).")
    nb.code(f"""
%%sql
-- {BANNER}
SELECT i.institution_type,
       COUNT(DISTINCT c.institution_id)        AS institutions,
       ROUND(SUM(c.cet1_capital) / SUM(c.rwa), 4) AS cet1_ratio
FROM fact_capital AS c
JOIN dim_institution AS i ON i.institution_id = c.institution_id
WHERE c.quarter_key = 20262
GROUP BY i.institution_type
ORDER BY cet1_ratio
""")
    nb.md("*Expected:* D-SIB 0.1328 (6) · Other bank 0.1413 (10) · Trust and loan 0.1504 (6).")
    nb.md("## 2. pandas + Data Wrangler")
    nb.code(f"""
# {BANNER}
cap = spark.read.table("fact_capital")
inst = spark.read.table("dim_institution")
qtr = spark.read.table("dim_quarter")

pdf = (cap.join(inst, "institution_id").join(qtr, "quarter_key")
          .selectExpr("institution_code", "institution_name", "institution_type", "peer_group",
                      "quarter_key", "quarter_label", "quarter_index", "cet1_capital", "rwa",
                      "cet1_capital / rwa AS cet1_ratio",
                      "tier1_capital / leverage_exposure AS leverage_ratio")
          .toPandas())
pdf.describe()
""")
    nb.md("""
**Open it in Data Wrangler:** notebook ribbon **Data** (or the toolbar above the output) > **Launch Data Wrangler** > choose `pdf`.
1. Filter: `quarter_key` equals `20263`.
2. Group by and aggregate: `institution_type`, `cet1_ratio` > Mean.
3. Sort by the mean ascending.
4. **Add code to notebook**: Data Wrangler writes the pandas code for you (review it; no magic).

*Say:* the summary statistics and every step become plain, reviewable pandas code.
""")
    nb.md("## 3. Quarter-over-quarter change and a chart")
    nb.code(f"""
# {BANNER}
import matplotlib.pyplot as plt

pdf = pdf.sort_values(["institution_code", "quarter_index"])
pdf["prev_quarter_index"] = pdf.groupby("institution_code")["quarter_index"].shift(1)
pdf["cet1_qoq_pp"] = (pdf["cet1_ratio"] - pdf.groupby("institution_code")["cet1_ratio"].shift(1)) * 100
pdf.loc[pdf["prev_quarter_index"] != pdf["quarter_index"] - 1, "cet1_qoq_pp"] = None   # gap = no comparison

current = int(qtr.where("is_current").first()["quarter_key"])
latest = pdf[pdf["quarter_key"] == current].sort_values("cet1_qoq_pp")
display(latest[["institution_name", "institution_type", "cet1_ratio", "cet1_qoq_pp"]].head(5))

by_type = (pdf[pdf["quarter_index"] > 31 - 12]
           .groupby(["quarter_label", "institution_type"])[["cet1_capital", "rwa"]].sum())
trend = (by_type["cet1_capital"] / by_type["rwa"]).unstack("institution_type") * 100
ax = trend.plot(figsize=(9, 4), marker="o", title="CET1 ratio by institution type, last 12 quarters (SYNTHETIC)")
ax.set_ylabel("CET1 ratio (%)"); ax.set_xlabel(""); ax.grid(alpha=0.3)
plt.xticks(rotation=45); plt.tight_layout(); plt.show()
""")
    nb.md("*Expected (after D2 landing):* largest 2026 Q3 drops: Driftwood Bank −1.41 pp, Stonebridge Bank −0.64 pp, Riverbend Trust and Loan −0.58 pp.")
    nb.md("""
## 4. Semantic Link: one definition, every tool
The same measures the report, Excel and Copilot use, called from Python. No re-implementation of the CET1 formula.
""")
    nb.code(f"""
# {BANNER}
import sempy.fabric as fabric

measures = fabric.list_measures("sm_fda_supervisory")
display(measures.head(20))
""")
    nb.code(f"""
# {BANNER}
result = fabric.evaluate_measure(
    "sm_fda_supervisory",
    measure=["CET1 Ratio", "Institutions Reporting"],
    groupby_columns=["dim_quarter[quarter_label]", "dim_institution[institution_type]"],
    filters={{"dim_quarter[quarter_label]": ["2026 Q2", "2026 Q3"]}},
)
display(result)
""")
    nb.md("*Expected:* 2026 Q2 CET1 Ratio = the `%%sql` numbers above (D-SIB 13.28%, Other bank 14.13%, Trust and loan 15.04%). Same definition, every tool.")
    nb.md("## 5. Save the outliers\nInstitutions whose CET1 ratio fell more than **0.5 pp** quarter over quarter in the current quarter, saved as the lakehouse table `analyst_outliers`.")
    nb.code(f"""
# {BANNER}
outliers = latest[latest["cet1_qoq_pp"] < -0.5][["institution_code", "institution_name", "institution_type",
                                                  "quarter_key", "cet1_ratio", "cet1_qoq_pp"]]
spark.createDataFrame(outliers).write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("analyst_outliers")
print(f"analyst_outliers: {{len(outliers)}} rows")
display(outliers)
""")
    nb.md("""
*Expected:* **3 rows** after D2 (Driftwood Bank, Stonebridge Bank, Riverbend Trust and Loan); 2 if the late filings are not landed.

## Summary
* `%%sql`, pandas and Data Wrangler for exploration, in one place, on the same Delta tables as the SQL analytics endpoint.
* Semantic Link reads the **governed measures** from `sm_fda_supervisory`, so Python agrees with the report.
* The result is a table (`analyst_outliers`) others can query from SQL, Power BI or Excel.
""")
    return nb.write("nb_fda_01_analyst_explore")


if __name__ == "__main__":
    for p in (build_nb00(), build_nb01(), build_nb02()):
        print("wrote", p)
