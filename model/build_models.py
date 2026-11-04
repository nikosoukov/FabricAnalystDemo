# SYNTHETIC DATA · for training only · no OSFI data
"""
build_models.py - emits the TMDL for BOTH semantic models from one definition:

  model/sm_fda_supervisory/          Direct Lake on the lh_supervisory SQL analytics endpoint
  model/sm_fda_supervisory_import/   Import mode, M = Sql.Database(<endpoint>, "lh_supervisory")

Same tables, columns, relationships, measures and descriptions in both, so D2 compares
storage modes and nothing else. Column names/types come from data_gen/gen_supervisory_data.py
(TABLE_SCHEMAS) so the model always matches the Delta tables nb_fda_00 writes.

Placeholders replaced by scripts/01-Deploy-FdaEnvironment.ps1 before upload:
  __SQL_ENDPOINT__     lh_supervisory SQL analytics endpoint server (connection string)
  __SQL_ENDPOINT_ID__  SQL analytics endpoint item id (Direct Lake only)

Run:  python model/build_models.py      (the generated output is committed)
"""
from __future__ import annotations

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "data_gen"))
import gen_supervisory_data as g  # noqa: E402

MODELS = {
    "sm_fda_supervisory": "directLake",
    "sm_fda_supervisory_import": "import",
}
TMDL_TYPES = {"int": "int64", "long": "int64", "double": "double", "string": "string", "boolean": "boolean", "date": "dateTime"}
BANNER = g.BANNER

# ----------------------------------------------------------------------------- descriptions (written for Copilot)
TABLE_DESCRIPTIONS = {
    "dim_institution": "One row per supervised federally regulated financial institution (40, all fictitious). Use institution_type, sector and peer_group to group results. is_late_filer_2026q3 flags the 10 institutions whose 2026 Q3 return arrived late.",
    "dim_quarter": "Reporting quarters from 2019 Q1 to 2026 Q3. quarter_label (for example '2026 Q3') sorts by quarter_key. is_current marks 2026 Q3, the latest quarter.",
    "dim_province": "Canadian provinces and territories (13) used for mortgage exposure, with English and French names and a region.",
    "fact_capital": "Quarterly capital return of deposit-taking institutions (D-SIB, Other bank, Trust and loan). Stores capital COMPONENTS in CAD millions, not ratios: CET1, Tier 1 and total capital, risk-weighted assets (RWA) and leverage exposure. Use the ratio measures, which divide sums.",
    "fact_liquidity": "Quarterly liquidity return of deposit-taking institutions, in CAD millions: high-quality liquid assets, 30-day net cash outflows (LCR components) and available/required stable funding (NSFR components).",
    "fact_insurance_capital": "Quarterly capital return of insurers in CAD millions. ratio_basis is 'LICAT total' for life insurers and 'MCT' for P&C insurers. Insurance Capital Ratio = capital_available / capital_required.",
    "fact_mortgage_exposure": "Residential mortgage exposure of deposit-taking institutions by quarter, province, loan-to-value band, insured flag, amortization band and channel. One row per mortgage pool (an institution can report several pools with the same attributes). Amounts in CAD millions. Balances are a stock: always filter to one quarter.",
    "supervisory_watch_thresholds": "Internal watch thresholds (illustrative) by institution_type and metric, loaded from the Excel file supervisory_watch_thresholds.xlsx by the Dataflow Gen2 df_fda_watch_thresholds. NOT OSFI regulatory minimums. Not related to other tables; the watch measures look thresholds up by institution_type. The measures apply the thresholds currently loaded to every quarter; effective_from_quarter is kept for audit.",
}
COLUMN_DESCRIPTIONS = {
    ("dim_institution", "institution_id"): "Surrogate key of the institution.",
    ("dim_institution", "institution_code"): "Institution code, FI001 to FI040.",
    ("dim_institution", "institution_name"): "Fictitious institution name, for example Cedarline Bank.",
    ("dim_institution", "institution_type"): "D-SIB, Other bank, Trust and loan, Life insurer or P&C insurer.",
    ("dim_institution", "sector"): "Deposit-taking or Insurance.",
    ("dim_institution", "peer_group"): "Peer group used for rankings, for example D-SIB, Mid-size bank, Large life.",
    ("dim_institution", "head_office_province"): "Province code of the head office.",
    ("dim_institution", "size_band"): "Large, Medium or Small.",
    ("dim_institution", "supervisory_lead"): "Name of the (fictitious) lead supervisor.",
    ("dim_institution", "intervention_stage"): "Supervisory intervention stage: 0 = normal, 1 = early warning, 2 = risk to financial viability or solvency (illustrative).",
    ("dim_institution", "is_late_filer_2026q3"): "True for the 10 institutions whose 2026 Q3 return arrived late.",
    ("dim_quarter", "quarter_key"): "Quarter as an integer YYYYQ, for example 20263.",
    ("dim_quarter", "quarter_label"): "Quarter label, for example 2026 Q3. Sorted by quarter_key.",
    ("dim_quarter", "quarter_end_date"): "Last calendar day of the quarter.",
    ("dim_quarter", "quarter_index"): "Sequential quarter number, 1 = 2019 Q1, 31 = 2026 Q3. Used for previous-quarter comparisons.",
    ("dim_quarter", "is_current"): "True for 2026 Q3, the latest reporting quarter.",
    ("dim_province", "province_code"): "Two-letter province or territory code, for example ON, BC.",
    ("fact_capital", "cet1_capital"): "Common Equity Tier 1 capital, CAD millions.",
    ("fact_capital", "tier1_capital"): "Tier 1 capital, CAD millions.",
    ("fact_capital", "total_capital"): "Total capital, CAD millions.",
    ("fact_capital", "rwa"): "Risk-weighted assets, CAD millions.",
    ("fact_capital", "leverage_exposure"): "Leverage ratio exposure measure, CAD millions.",
    ("fact_liquidity", "hqla"): "High-quality liquid assets, CAD millions (LCR numerator).",
    ("fact_liquidity", "net_cash_outflows_30d"): "Net cash outflows over 30 days, CAD millions (LCR denominator).",
    ("fact_liquidity", "available_stable_funding"): "Available stable funding, CAD millions (NSFR numerator).",
    ("fact_liquidity", "required_stable_funding"): "Required stable funding, CAD millions (NSFR denominator).",
    ("fact_insurance_capital", "ratio_basis"): "LICAT total (life insurers) or MCT (P&C insurers).",
    ("fact_insurance_capital", "capital_available"): "Capital available, CAD millions.",
    ("fact_insurance_capital", "capital_required"): "Capital required, CAD millions.",
    ("fact_mortgage_exposure", "ltv_band"): "Loan-to-value band: <=60%, 60-65%, 65-70%, 70-75%, 75-80%, >80% (insured).",
    ("fact_mortgage_exposure", "insured_flag"): "True if the mortgage is default-insured.",
    ("fact_mortgage_exposure", "amortization_band"): "Remaining amortization band: <=25y, 25-30y, >30y.",
    ("fact_mortgage_exposure", "channel"): "Origination channel: Branch, Broker or Digital.",
    ("fact_mortgage_exposure", "balance"): "Outstanding balance, CAD millions.",
    ("fact_mortgage_exposure", "loan_count"): "Number of loans in the pool.",
    ("fact_mortgage_exposure", "arrears_90d_balance"): "Balance 90 or more days in arrears, CAD millions.",
    ("supervisory_watch_thresholds", "metric"): "CET1 ratio, Leverage ratio, LCR, NSFR, LICAT total or MCT.",
    ("supervisory_watch_thresholds", "watch_threshold"): "Internal watch threshold (illustrative) as a decimal ratio, e.g. 0.115 = 11.5%.",
    ("supervisory_watch_thresholds", "effective_from_quarter"): "Quarter (YYYYQ) from which the threshold applies, for audit.",
    ("supervisory_watch_thresholds", "source_file"): "Excel file the row was loaded from.",
}
HIDDEN = {
    ("dim_institution", "institution_id"), ("dim_quarter", "quarter_key"),
    *((t, "institution_id") for t in g.FACT_TABLES), *((t, "quarter_key") for t in g.FACT_TABLES),
    ("fact_mortgage_exposure", "province_code"),
}
COLUMN_FORMATS = {"double": "#,0.0", "int": "0", "long": "0"}
PCT = "0.00%"

# (table, name, display folder, format, description, DAX)
MEASURES = [
    ("fact_capital", "CET1 Ratio", "Capital", PCT,
     "Common Equity Tier 1 ratio = sum of CET1 capital / sum of risk-weighted assets. Deposit-taking institutions only. Aggregates correctly across institutions because components are stored, not ratios.",
     "DIVIDE(SUM(fact_capital[cet1_capital]), SUM(fact_capital[rwa]))"),
    ("fact_capital", "Tier 1 Ratio", "Capital", PCT,
     "Tier 1 capital ratio = sum of Tier 1 capital / sum of risk-weighted assets. Deposit-taking institutions only.",
     "DIVIDE(SUM(fact_capital[tier1_capital]), SUM(fact_capital[rwa]))"),
    ("fact_capital", "Total Capital Ratio", "Capital", PCT,
     "Total capital ratio = sum of total capital / sum of risk-weighted assets. Deposit-taking institutions only.",
     "DIVIDE(SUM(fact_capital[total_capital]), SUM(fact_capital[rwa]))"),
    ("fact_capital", "Leverage Ratio", "Capital", PCT,
     "Leverage ratio = sum of Tier 1 capital / sum of leverage exposure. Deposit-taking institutions only.",
     "DIVIDE(SUM(fact_capital[tier1_capital]), SUM(fact_capital[leverage_exposure]))"),
    ("fact_capital", "CET1 Ratio QoQ Change (pp)", "Capital", "+0.00;-0.00;0.00",
     "Change in CET1 Ratio versus the previous quarter, in percentage points (for example -0.64 means the ratio fell by 0.64 points). Use with one quarter selected. Blank when either quarter has no filing.",
     """VAR _q = MAX(dim_quarter[quarter_index])
VAR _current = [CET1 Ratio]
VAR _previous =
    CALCULATE([CET1 Ratio], REMOVEFILTERS(dim_quarter), dim_quarter[quarter_index] = _q - 1)
RETURN
    IF(NOT ISBLANK(_current) && NOT ISBLANK(_previous), (_current - _previous) * 100)"""),
    ("fact_liquidity", "LCR", "Liquidity", PCT,
     "Liquidity Coverage Ratio = sum of high-quality liquid assets / sum of 30-day net cash outflows. Deposit-taking institutions only.",
     "DIVIDE(SUM(fact_liquidity[hqla]), SUM(fact_liquidity[net_cash_outflows_30d]))"),
    ("fact_liquidity", "NSFR", "Liquidity", PCT,
     "Net Stable Funding Ratio = sum of available stable funding / sum of required stable funding. Deposit-taking institutions only.",
     "DIVIDE(SUM(fact_liquidity[available_stable_funding]), SUM(fact_liquidity[required_stable_funding]))"),
    ("fact_insurance_capital", "Insurance Capital Ratio", "Insurance", PCT,
     "Insurer capital ratio = sum of capital available / sum of capital required. LICAT total ratio for life insurers, MCT for P&C insurers; do not mix the two bases in one number - group by institution_type or ratio_basis.",
     "DIVIDE(SUM(fact_insurance_capital[capital_available]), SUM(fact_insurance_capital[capital_required]))"),
    ("dim_institution", "Institutions Reporting", "Filing status", "#,0",
     "Number of institutions that filed a return for the quarter(s) in context (capital return for deposit-taking institutions, insurance capital return for insurers).",
     """VAR _depositTaking = DISTINCTCOUNT(fact_capital[institution_id])
VAR _insurers = DISTINCTCOUNT(fact_insurance_capital[institution_id])
RETURN
    _depositTaking + _insurers"""),
    ("dim_institution", "Institutions Expected", "Filing status", "#,0",
     "Number of institutions expected to file (all supervised institutions in context, 40 in total).",
     "COUNTROWS(dim_institution)"),
    ("dim_institution", "Filing Completeness %", "Filing status", PCT,
     "Institutions Reporting / Institutions Expected for the quarter in context. 2026 Q3 is 75% until the late filings are landed.",
     "DIVIDE([Institutions Reporting], [Institutions Expected])"),
    ("supervisory_watch_thresholds", "CET1 Watch Threshold", "Watch", "0.0%",
     "Internal CET1 watch threshold (illustrative, not an OSFI minimum) for the single institution_type in context, from supervisory_watch_thresholds. Blank when several institution types are in context.",
     """VAR _type = SELECTEDVALUE(dim_institution[institution_type])
RETURN
    CALCULATE(
        MAX(supervisory_watch_thresholds[watch_threshold]),
        supervisory_watch_thresholds[metric] = "CET1 ratio",
        supervisory_watch_thresholds[institution_type] = _type
    )"""),
    ("supervisory_watch_thresholds", "Institutions Below CET1 Watch", "Watch", "#,0",
     "Number of deposit-taking institutions whose CET1 Ratio is below the internal CET1 watch threshold for their institution_type, evaluated institution by institution. Use with one quarter selected (2026 Q3 is the current quarter).",
     """VAR _count =
    SUMX(
        VALUES(dim_institution[institution_id]),
        VAR _ratio = [CET1 Ratio]
        VAR _threshold = [CET1 Watch Threshold]
        RETURN
            IF(NOT ISBLANK(_ratio) && NOT ISBLANK(_threshold) && _ratio < _threshold, 1)
    )
RETURN
    IF(NOT ISEMPTY(fact_capital), COALESCE(_count, 0))"""),
    ("supervisory_watch_thresholds", "LICAT Watch Threshold", "Watch", "0.0%",
     "Internal LICAT total ratio watch threshold (illustrative, not an OSFI minimum) for life insurers, from supervisory_watch_thresholds.",
     """CALCULATE(
    MAX(supervisory_watch_thresholds[watch_threshold]),
    supervisory_watch_thresholds[metric] = "LICAT total",
    supervisory_watch_thresholds[institution_type] = "Life insurer"
)"""),
    ("supervisory_watch_thresholds", "Insurers Below Capital Watch", "Watch", "#,0",
     "Number of insurers whose Insurance Capital Ratio is below the internal watch threshold for their type (LICAT total for life insurers, MCT for P&C insurers). Use with one quarter selected.",
     """VAR _count =
    SUMX(
        VALUES(dim_institution[institution_id]),
        VAR _type = CALCULATE(SELECTEDVALUE(dim_institution[institution_type]))
        VAR _ratio = [Insurance Capital Ratio]
        VAR _threshold =
            CALCULATE(
                MAX(supervisory_watch_thresholds[watch_threshold]),
                supervisory_watch_thresholds[metric] IN {"LICAT total", "MCT"},
                supervisory_watch_thresholds[institution_type] = _type
            )
        RETURN
            IF(NOT ISBLANK(_ratio) && NOT ISBLANK(_threshold) && _ratio < _threshold, 1)
    )
RETURN
    IF(NOT ISEMPTY(fact_insurance_capital), COALESCE(_count, 0))"""),
    ("fact_mortgage_exposure", "Mortgage Balance", "Mortgages", "#,0",
     "Outstanding residential mortgage balance in CAD millions. A stock: select one quarter.",
     "SUM(fact_mortgage_exposure[balance])"),
    ("fact_mortgage_exposure", "Uninsured High-LTV Share", "Mortgages", PCT,
     "Share of mortgage balance that is uninsured with loan-to-value above 70% (bands 70-75% and 75-80%).",
     """DIVIDE(
    CALCULATE(
        [Mortgage Balance],
        fact_mortgage_exposure[insured_flag] = FALSE(),
        fact_mortgage_exposure[ltv_band] IN {"70-75%", "75-80%"}
    ),
    [Mortgage Balance]
)"""),
    ("fact_mortgage_exposure", "Arrears 90d Rate", "Mortgages", PCT,
     "Share of mortgage balance 90 or more days in arrears = sum of arrears_90d_balance / sum of balance.",
     "DIVIDE(SUM(fact_mortgage_exposure[arrears_90d_balance]), SUM(fact_mortgage_exposure[balance]))"),
]
MEASURE_NAMES = [m[1] for m in MEASURES]

RELATIONSHIPS = [
    *((f"{t}_institution", f"{t}.institution_id", "dim_institution.institution_id") for t in g.FACT_TABLES),
    *((f"{t}_quarter", f"{t}.quarter_key", "dim_quarter.quarter_key") for t in g.FACT_TABLES),
    ("fact_mortgage_exposure_province", "fact_mortgage_exposure.province_code", "dim_province.province_code"),
]


def _q(name: str) -> str:
    return f"'{name}'" if any(ch in name for ch in " %()-'.") else name


def _doc(text: str, indent: str) -> list:
    return [f"{indent}/// {text}"]


def _measure_lines(m) -> list:
    _t, name, folder, fmt, desc, dax = m
    out = _doc(desc, "\t")
    if "\n" in dax:
        out.append(f"\tmeasure {_q(name)} =")
        out += [("\t\t\t" + ln) if ln.strip() else "" for ln in dax.split("\n")]
    else:
        out.append(f"\tmeasure {_q(name)} = {dax}")
    out.append(f"\t\tformatString: {fmt}")
    out.append(f"\t\tdisplayFolder: {folder}")
    out.append("")
    return out


def table_tmdl(table: str, mode: str) -> str:
    L = [f"/// {TABLE_DESCRIPTIONS[table]} {BANNER}.", f"table {table}", ""]
    for m in MEASURES:
        if m[0] == table:
            L += _measure_lines(m)
    for col, typ in g.TABLE_SCHEMAS[table]:
        desc = COLUMN_DESCRIPTIONS.get((table, col))
        if desc:
            L += _doc(desc, "\t")
        L.append(f"\tcolumn {col}")
        L.append(f"\t\tdataType: {TMDL_TYPES[typ]}")
        if (table, col) in HIDDEN:
            L.append("\t\tisHidden")
        if typ == "date":
            L.append("\t\tformatString: yyyy-mm-dd")
        elif col == "watch_threshold":
            L.append("\t\tformatString: 0.0%")
        elif typ in COLUMN_FORMATS and not col.endswith(("_id", "_key", "_index", "_num", "_quarter")) and col not in ("year", "intervention_stage"):
            L.append(f"\t\tformatString: {COLUMN_FORMATS[typ]}")
        L.append("\t\tsummarizeBy: none")
        L.append(f"\t\tsourceColumn: {col}")
        if table == "dim_quarter" and col == "quarter_label":
            L.append("\t\tsortByColumn: quarter_key")
        if typ in ("double",) and table.startswith("fact_"):
            L.append("\t\tdisplayFolder: Components")
        L.append("")
    if mode == "directLake":
        L += [f"\tpartition {table} = entity", "\t\tmode: directLake", "\t\tsource",
              f"\t\t\tentityName: {table}", "\t\t\tschemaName: dbo", "\t\t\texpressionSource: DatabaseQuery", ""]
    else:
        L += [f"\tpartition {table} = m", "\t\tmode: import", "\t\tsource =",
              "\t\t\t\tlet",
              '\t\t\t\t    Source = Sql.Database(SqlEndpoint, "lh_supervisory"),',
              f'\t\t\t\t    Data = Source{{[Schema = "dbo", Item = "{table}"]}}[Data]',
              "\t\t\t\tin",
              "\t\t\t\t    Data", ""]
    return "\n".join(L).rstrip("\n") + "\n"


def expressions_tmdl(mode: str) -> str:
    if mode == "directLake":
        return "\n".join([
            "/// Direct Lake source: the lh_supervisory SQL analytics endpoint (server) and the endpoint item id.",
            "/// 01-Deploy-FdaEnvironment.ps1 replaces __SQL_ENDPOINT__ and __SQL_ENDPOINT_ID__ before upload.",
            "expression DatabaseQuery =",
            "\t\tlet",
            '\t\t    database = Sql.Database("__SQL_ENDPOINT__", "__SQL_ENDPOINT_ID__")',
            "\t\tin",
            "\t\t    database",
            "",
        ])
    return "\n".join([
        "/// Import source: the lh_supervisory SQL analytics endpoint server. Change it with a deployment-pipeline parameter rule.",
        "/// 01-Deploy-FdaEnvironment.ps1 replaces __SQL_ENDPOINT__ before upload.",
        'expression SqlEndpoint = "__SQL_ENDPOINT__" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]',
        "",
    ])


def model_tmdl(name: str, mode: str) -> str:
    desc = ("Supervisory analytics semantic model (Direct Lake on lh_supervisory)." if mode == "directLake"
            else "Supervisory analytics semantic model (Import copy of sm_fda_supervisory, for the storage-mode comparison).")
    # desc is kept for readers of this script only; TMDL "model" gets no doc comment (mirrors the reference kit).
    lines = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "",
        "\tannotation __PBI_TimeIntelligenceEnabled = 0",
        "",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def relationships_tmdl() -> str:
    L = []
    for name, f, t in RELATIONSHIPS:
        L += [f"relationship {name}", f"\tfromColumn: {f}", f"\ttoColumn: {t}", ""]
    return "\n".join(L).rstrip("\n") + "\n"


def build(root: str = HERE) -> dict:
    """Returns {relative_path: text} for both models and writes them under model/."""
    files = {}
    for name, mode in MODELS.items():
        base = name
        files[f"{base}/definition.pbism"] = '{\n  "version": "4.0",\n  "settings": {}\n}\n'
        files[f"{base}/definition/database.tmdl"] = "database\n\tcompatibilityLevel: 1604\n"
        files[f"{base}/definition/model.tmdl"] = model_tmdl(name, mode)
        files[f"{base}/definition/expressions.tmdl"] = expressions_tmdl(mode)
        files[f"{base}/definition/relationships.tmdl"] = relationships_tmdl()
        for t in g.TABLE_ORDER:
            files[f"{base}/definition/tables/{t}.tmdl"] = table_tmdl(t, mode)
    return files


def write(files: dict, root: str = HERE) -> None:
    for name in MODELS:
        shutil.rmtree(os.path.join(root, name), ignore_errors=True)
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


if __name__ == "__main__":
    out = build()
    write(out)
    print(f"wrote {len(out)} files for {', '.join(MODELS)}")
