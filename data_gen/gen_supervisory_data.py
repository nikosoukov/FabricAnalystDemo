# SYNTHETIC DATA · for training only · no OSFI data
"""
gen_supervisory_data.py - deterministic synthetic supervisory data for the
"Microsoft Fabric for Data Analysts" demo kit (prefix fda).

Pure Python (numpy + pandas, openpyxl only for the Excel file). The SAME code:
  * runs locally (tests/test_generator.py, data_gen/expected_values.py), and
  * is embedded verbatim in notebooks nb_fda_00_generate_data and
    nb_fda_02_land_late_filings (notebooks/build_notebooks.py copies it),
so the numbers quoted in docs/expected-values.md are the numbers you see in Fabric.

Every institution, person and value is invented. The watch thresholds are
"internal watch thresholds (illustrative)", NOT OSFI regulatory minimums.

Determinism: every random draw comes from numpy.random.default_rng seeded with
[SEED, <stream>, <institution_id>(, <quarter_index>)]. Because each slice has its
own stream, nb_fda_02 can regenerate ONLY the late filers' 2026 Q3 rows and get
values identical to a full run.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd

SEED = 20261105
BANNER = "SYNTHETIC DATA · for training only · no OSFI data"
GENERATOR_VERSION = "1.0.0"

FIRST_YEAR = 2019
N_QUARTERS = 31                      # 2019 Q1 .. 2026 Q3
CURRENT_QUARTER_KEY = 20263          # 2026 Q3 (late filers missing until nb_fda_02 runs)
PREVIOUS_QUARTER_KEY = 20262         # 2026 Q2 (complete for all 40)
CURRENT_QUARTER_INDEX = N_QUARTERS

DEPOSIT_TAKING_TYPES = ("D-SIB", "Other bank", "Trust and loan")
INSURER_TYPES = ("Life insurer", "P&C insurer")
LTV_BANDS = ("<=60%", "60-65%", "65-70%", "70-75%", "75-80%", ">80% (insured)")
AMORTIZATION_BANDS = ("<=25y", "25-30y", ">30y")
CHANNELS = ("Branch", "Broker", "Digital")
HIGH_LTV_UNINSURED_BANDS = ("70-75%", "75-80%")

# ----------------------------------------------------------------------------- schemas
# One source of truth for column names/types: used for pandas dtypes here, Spark
# StructTypes in the notebooks and TMDL dataTypes in model/build_models.py.
# int = 32-bit, long = 64-bit (matches Dataflow Gen2 Int64.Type output), date = DateType.
TABLE_SCHEMAS = {
    "dim_institution": [
        ("institution_id", "int"), ("institution_code", "string"), ("institution_name", "string"),
        ("institution_type", "string"), ("sector", "string"), ("peer_group", "string"),
        ("head_office_province", "string"), ("size_band", "string"), ("supervisory_lead", "string"),
        ("intervention_stage", "int"), ("is_late_filer_2026q3", "boolean"),
    ],
    "dim_quarter": [
        ("quarter_key", "int"), ("quarter_label", "string"), ("quarter_end_date", "date"),
        ("year", "int"), ("quarter_num", "int"), ("quarter_index", "int"), ("is_current", "boolean"),
    ],
    "dim_province": [
        ("province_code", "string"), ("province_name", "string"),
        ("province_name_fr", "string"), ("region", "string"),
    ],
    "fact_capital": [
        ("institution_id", "int"), ("quarter_key", "int"), ("cet1_capital", "double"),
        ("tier1_capital", "double"), ("total_capital", "double"), ("rwa", "double"),
        ("leverage_exposure", "double"),
    ],
    "fact_liquidity": [
        ("institution_id", "int"), ("quarter_key", "int"), ("hqla", "double"),
        ("net_cash_outflows_30d", "double"), ("available_stable_funding", "double"),
        ("required_stable_funding", "double"),
    ],
    "fact_insurance_capital": [
        ("institution_id", "int"), ("quarter_key", "int"), ("ratio_basis", "string"),
        ("capital_available", "double"), ("capital_required", "double"),
    ],
    "fact_mortgage_exposure": [
        ("institution_id", "int"), ("quarter_key", "int"), ("province_code", "string"),
        ("ltv_band", "string"), ("insured_flag", "boolean"), ("amortization_band", "string"),
        ("channel", "string"), ("balance", "double"), ("loan_count", "int"),
        ("arrears_90d_balance", "double"),
    ],
    "supervisory_watch_thresholds": [
        ("institution_type", "string"), ("metric", "string"), ("watch_threshold", "double"),
        ("effective_from_quarter", "long"), ("source_file", "string"),
    ],
}
FACT_TABLES = ("fact_capital", "fact_liquidity", "fact_insurance_capital", "fact_mortgage_exposure")
TABLE_ORDER = ("dim_institution", "dim_quarter", "dim_province") + FACT_TABLES + ("supervisory_watch_thresholds",)
_PANDAS_DTYPES = {"int": "int32", "long": "int64", "double": "float64", "string": "object", "boolean": "bool", "date": "object"}

# ----------------------------------------------------------------------------- reference data
# (code, English name, French name, region, population weight for mortgage balances)
PROVINCES = [
    ("NL", "Newfoundland and Labrador", "Terre-Neuve-et-Labrador", "Atlantic", 0.013),
    ("PE", "Prince Edward Island", "Île-du-Prince-Édouard", "Atlantic", 0.004),
    ("NS", "Nova Scotia", "Nouvelle-Écosse", "Atlantic", 0.026),
    ("NB", "New Brunswick", "Nouveau-Brunswick", "Atlantic", 0.021),
    ("QC", "Quebec", "Québec", "Central", 0.220),
    ("ON", "Ontario", "Ontario", "Central", 0.390),
    ("MB", "Manitoba", "Manitoba", "Prairies", 0.036),
    ("SK", "Saskatchewan", "Saskatchewan", "Prairies", 0.030),
    ("AB", "Alberta", "Alberta", "Prairies", 0.120),
    ("BC", "British Columbia", "Colombie-Britannique", "West Coast", 0.137),
    ("YT", "Yukon", "Yukon", "North", 0.001),
    ("NT", "Northwest Territories", "Territoires du Nord-Ouest", "North", 0.001),
    ("NU", "Nunavut", "Nunavut", "North", 0.001),
]

# All names are FICTITIOUS (checked against a banned list of real Canadian FI names in tests).
# (name, institution_type, head_office_province, intervention_stage, is_late_filer_2026q3)
INSTITUTIONS = [
    ("Granitecrest Bank", "D-SIB", "ON", 0, False),
    ("Borealis Bank Group", "D-SIB", "QC", 0, True),
    ("Stonebridge Bank", "D-SIB", "ON", 0, False),           # storyline (e): LCR drop in 2026 Q3
    ("Aurora Ridge Bank", "D-SIB", "AB", 0, False),
    ("Twin Rivers Bank", "D-SIB", "ON", 0, False),
    ("Silverpine Bank", "D-SIB", "BC", 0, False),
    ("Cedarline Bank", "Other bank", "BC", 1, False),        # storyline (b): CET1 drifts under watch
    ("Larchmont Bank", "Other bank", "ON", 0, False),        # storyline (c): caught by v2 threshold
    ("Bluewater Bank", "Other bank", "NS", 0, False),
    ("Kingsmere Bank", "Other bank", "ON", 0, False),
    ("Driftwood Bank", "Other bank", "BC", 1, True),         # storyline (b): late filer, Q3 below watch
    ("Ashgrove Bank", "Other bank", "AB", 0, False),         # storyline (c): caught by v2 threshold
    ("Pembrook Bank", "Other bank", "MB", 0, True),
    ("Saltmarsh Bank", "Other bank", "NB", 2, False),
    ("Juniper Point Bank", "Other bank", "SK", 0, False),
    ("Ironwood Bank", "Other bank", "QC", 0, False),
    ("Northgate Trust", "Trust and loan", "ON", 0, False),
    ("Old Mill Trust", "Trust and loan", "ON", 0, True),
    ("Riverbend Trust and Loan", "Trust and loan", "QC", 0, False),
    ("Clearwater Loan Company", "Trust and loan", "AB", 0, False),
    ("Hollowbrook Trust", "Trust and loan", "NS", 0, False),
    ("Sandstone Mortgage and Loan", "Trust and loan", "BC", 0, True),
    ("Prairie Crown Life", "Life insurer", "SK", 1, False),  # below LICAT watch (v1)
    ("Lighthouse Life Assurance", "Life insurer", "NS", 0, False),
    ("Evergreen Mutual Life", "Life insurer", "ON", 0, False),  # caught by v2 LICAT threshold
    ("Summit Peak Life", "Life insurer", "AB", 0, False),       # caught by v2 LICAT threshold
    ("Northwind Life", "Life insurer", "MB", 0, True),
    ("Glacier Bay Life", "Life insurer", "BC", 0, False),
    ("Tamarack Life", "Life insurer", "ON", 0, True),
    ("Copperleaf Life", "Life insurer", "QC", 0, False),
    ("Bayfield Life Assurance", "Life insurer", "ON", 0, False),
    ("Harbourview Assurance", "P&C insurer", "NS", 0, False),
    ("Stormguard Insurance", "P&C insurer", "ON", 0, True),
    ("Kettle Lake General", "P&C insurer", "BC", 1, False),  # below MCT watch
    ("Mapleton Property and Casualty", "P&C insurer", "ON", 0, False),
    ("Blue Heron Insurance", "P&C insurer", "QC", 0, False),
    ("Ridgeline General Insurance", "P&C insurer", "AB", 0, False),
    ("Snowfield Insurance", "P&C insurer", "QC", 0, True),
    ("Falcon Crest Insurance", "P&C insurer", "ON", 0, False),
    ("Timberline Mutual", "P&C insurer", "BC", 0, True),
]

SUPERVISORY_LEADS = [
    "Amara Okafor", "Liang Wei", "Sofia Marchetti", "Rajiv Mehta", "Élise Gagnon",
    "Daniel Whitehorse", "Fatima Haddad", "Kenji Sato", "Priya Raman", "Mateo Alvarez",
]

# Internal watch thresholds (illustrative) - NOT OSFI regulatory minimums.
# Wide layout = the Excel file; None = not applicable.
THRESHOLD_METRICS = ("CET1 ratio", "Leverage ratio", "LCR", "NSFR", "LICAT total", "MCT")
THRESHOLDS_WIDE = {
    "v1": [
        # institution_type, CET1, Leverage, LCR, NSFR, LICAT total, MCT, effective_from_quarter
        ("D-SIB", 0.120, 0.040, 1.10, 1.05, None, None, 20251),
        ("Other bank", 0.115, 0.035, 1.10, 1.05, None, None, 20251),
        ("Trust and loan", 0.115, 0.035, 1.10, 1.05, None, None, 20251),
        ("Life insurer", None, None, None, None, 1.20, None, 20251),
        ("P&C insurer", None, None, None, None, None, 1.80, 20251),
    ],
    "v2": [
        ("D-SIB", 0.120, 0.040, 1.10, 1.05, None, None, 20251),
        ("Other bank", 0.120, 0.035, 1.10, 1.05, None, None, 20263),     # raised 11.5% -> 12.0%
        ("Trust and loan", 0.115, 0.035, 1.10, 1.05, None, None, 20251),
        ("Life insurer", None, None, None, None, 1.25, None, 20263),      # raised 120% -> 125%
        ("P&C insurer", None, None, None, None, None, 1.80, 20251),
    ],
}
THRESHOLD_FILES = {"v1": "supervisory_watch_thresholds.xlsx", "v2": "supervisory_watch_thresholds_v2.xlsx"}
THRESHOLD_LAST_REVIEWED = {"v1": "2026-09-30", "v2": "2026-11-04"}

# Storyline overrides: exact ratios for the last quarters (quarter_index -> ratio).
# Before each override the series glides linearly from its generated value to the first override.
_CET1_STORY = {
    "Cedarline Bank": {25: 0.1215, 29: 0.1162, 30: 0.1146, 31: 0.1138},
    "Driftwood Bank": {29: 0.1268, 30: 0.1262, 31: 0.1121},
    "Ashgrove Bank": {27: 0.1236, 30: 0.1195, 31: 0.1178},
    "Larchmont Bank": {27: 0.1242, 30: 0.1208, 31: 0.1191},
    "Stonebridge Bank": {30: 0.1338, 31: 0.1274},
    "Riverbend Trust and Loan": {30: 0.1452, 31: 0.1394},
}
_LCR_STORY = {"Stonebridge Bank": {30: 1.482, 31: 1.187}}
_INS_STORY = {
    "Prairie Crown Life": {27: 1.255, 29: 1.214, 30: 1.193, 31: 1.171},
    "Evergreen Mutual Life": {28: 1.262, 31: 1.222},
    "Summit Peak Life": {28: 1.271, 31: 1.236},
    "Kettle Lake General": {28: 1.905, 30: 1.842, 31: 1.761},
}


# ----------------------------------------------------------------------------- helpers
def _rng(*stream: int) -> np.random.Generator:
    return np.random.default_rng([SEED, *stream])


def quarter_key(index: int) -> int:
    """quarter_index 1..31 -> YYYYQ int (1 -> 20191, 31 -> 20263)."""
    year = FIRST_YEAR + (index - 1) // 4
    return year * 10 + (index - 1) % 4 + 1


def quarter_label(index: int) -> str:
    k = quarter_key(index)
    return f"{k // 10} Q{k % 10}"


def _apply_schema(df: pd.DataFrame, table: str) -> pd.DataFrame:
    cols = [c for c, _ in TABLE_SCHEMAS[table]]
    df = df[cols].copy()
    for c, t in TABLE_SCHEMAS[table]:
        df[c] = df[c].astype(_PANDAS_DTYPES[t])
    return df.reset_index(drop=True)


def _glide(series: np.ndarray, story: dict) -> np.ndarray:
    """Overwrite a 1-based quarter series with storyline anchor points, gliding linearly into them."""
    s = series.copy()
    anchors = sorted(story.items())
    first_idx, first_val = anchors[0]
    start_idx = max(1, first_idx - 6)
    start_val = s[start_idx - 1]
    for i in range(start_idx, first_idx + 1):
        w = (i - start_idx) / max(1, first_idx - start_idx)
        s[i - 1] = start_val + w * (first_val - start_val)
    for (i0, v0), (i1, v1) in zip(anchors, anchors[1:]):
        for i in range(i0, i1 + 1):
            s[i - 1] = v0 + (i - i0) / (i1 - i0) * (v1 - v0)
    return s


def _ar_path(rng: np.random.Generator, level: float, sd: float, lo: float, hi: float, trend: float = 0.0) -> np.ndarray:
    """Mean-reverting AR(1) path around a (slowly trending) level, clipped to a plausible band."""
    x = np.empty(N_QUARTERS)
    prev = level
    for t in range(N_QUARTERS):
        target = level + trend * t
        prev = target + 0.6 * (prev - target) + rng.normal(0.0, sd)
        x[t] = prev
    return np.clip(x, lo, hi)


# ----------------------------------------------------------------------------- dimensions
def build_dim_quarter() -> pd.DataFrame:
    rows = []
    for i in range(1, N_QUARTERS + 1):
        k = quarter_key(i)
        y, q = k // 10, k % 10
        end_month = q * 3
        end_day = 31 if end_month in (3, 12) else 30
        rows.append({
            "quarter_key": k, "quarter_label": quarter_label(i),
            "quarter_end_date": _dt.date(y, end_month, end_day), "year": y, "quarter_num": q,
            "quarter_index": i, "is_current": k == CURRENT_QUARTER_KEY,
        })
    return _apply_schema(pd.DataFrame(rows), "dim_quarter")


def build_dim_province() -> pd.DataFrame:
    df = pd.DataFrame(PROVINCES, columns=["province_code", "province_name", "province_name_fr", "region", "w"])
    return _apply_schema(df, "dim_province")


def _institution_base(inst_id: int, itype: str) -> dict:
    """Static size parameters per institution (own random stream)."""
    rng = _rng(1, inst_id)
    if itype == "D-SIB":
        size = rng.uniform(180_000, 520_000)      # RWA, CAD millions, 2019 Q1
    elif itype == "Other bank":
        size = rng.uniform(6_000, 45_000)
    elif itype == "Trust and loan":
        size = rng.uniform(1_500, 12_000)
    elif itype == "Life insurer":
        size = rng.uniform(2_000, 15_000)         # capital required, CAD millions
    else:
        size = rng.uniform(500, 4_000)
    return {"size": size, "growth": rng.uniform(0.008, 0.016)}


def build_dim_institution() -> pd.DataFrame:
    rows = []
    for n, (name, itype, prov, stage, late) in enumerate(INSTITUTIONS, start=1):
        base = _institution_base(n, itype)
        if itype == "D-SIB":
            peer, band = "D-SIB", "Large"
        elif itype == "Other bank":
            peer, band = ("Mid-size bank", "Medium") if base["size"] > 20_000 else ("Small bank", "Small")
        elif itype == "Trust and loan":
            peer, band = "Trust and loan", ("Medium" if base["size"] > 6_000 else "Small")
        elif itype == "Life insurer":
            peer, band = ("Large life", "Large") if base["size"] > 9_000 else ("Mid-size life", "Medium")
        else:
            peer, band = ("Large P&C", "Large") if base["size"] > 2_500 else ("Mid-size P&C", "Medium")
        rows.append({
            "institution_id": n, "institution_code": f"FI{n:03d}", "institution_name": name,
            "institution_type": itype,
            "sector": "Deposit-taking" if itype in DEPOSIT_TAKING_TYPES else "Insurance",
            "peer_group": peer, "head_office_province": prov, "size_band": band,
            "supervisory_lead": SUPERVISORY_LEADS[(n - 1) % len(SUPERVISORY_LEADS)],
            "intervention_stage": stage, "is_late_filer_2026q3": late,
        })
    return _apply_schema(pd.DataFrame(rows), "dim_institution")


def late_filer_ids() -> list:
    return [n for n, row in enumerate(INSTITUTIONS, start=1) if row[4]]


def institution_id(name: str) -> int:
    for n, row in enumerate(INSTITUTIONS, start=1):
        if row[0] == name:
            return n
    raise KeyError(name)


# ----------------------------------------------------------------------------- capital / liquidity / insurance
def _deposit_taker_series(inst_id: int, name: str, itype: str) -> tuple:
    """Full 31-quarter capital + liquidity series for one deposit-taking institution."""
    base = _institution_base(inst_id, itype)
    rng = _rng(11, inst_id)
    t = np.arange(N_QUARTERS)
    rwa = base["size"] * (1 + base["growth"]) ** t * np.exp(rng.normal(0, 0.006, N_QUARTERS))
    if itype == "D-SIB":
        cet1 = _ar_path(rng, rng.uniform(0.128, 0.140), 0.0010, 0.123, 0.145)
    elif itype == "Other bank":
        cet1 = _ar_path(rng, rng.uniform(0.136, 0.165), 0.0012, 0.128, 0.180)
    else:
        cet1 = _ar_path(rng, rng.uniform(0.140, 0.172), 0.0012, 0.130, 0.180)
    if name in _CET1_STORY:
        cet1 = _glide(cet1, _CET1_STORY[name])
    at1 = rng.uniform(0.010, 0.016) + rng.normal(0, 0.0004, N_QUARTERS)
    t2 = rng.uniform(0.015, 0.025) + rng.normal(0, 0.0005, N_QUARTERS)
    lev = _ar_path(rng, rng.uniform(0.045, 0.055), 0.0006, 0.042, 0.058)
    lcr = _ar_path(rng, rng.uniform(1.25, 1.52), 0.035, 1.15, 1.65)
    if name in _LCR_STORY:
        lcr = _glide(lcr, _LCR_STORY[name])
    nsfr = _ar_path(rng, rng.uniform(1.12, 1.24), 0.012, 1.08, 1.30)
    ncof_share = rng.uniform(0.08, 0.12)
    rsf_share = rng.uniform(0.70, 0.90)

    cet1_cap = np.round(cet1 * rwa, 1)
    tier1 = np.round(cet1_cap + at1 * rwa, 1)
    total = np.round(tier1 + t2 * rwa, 1)
    rwa = np.round(rwa, 1)
    ncof = np.round(rwa * ncof_share * np.exp(rng.normal(0, 0.02, N_QUARTERS)), 1)
    rsf = np.round(rwa * rsf_share * np.exp(rng.normal(0, 0.01, N_QUARTERS)), 1)
    capital = {
        "cet1_capital": cet1_cap, "tier1_capital": tier1, "total_capital": total, "rwa": rwa,
        "leverage_exposure": np.round(tier1 / lev, 1),
    }
    liquidity = {
        "hqla": np.round(lcr * ncof, 1), "net_cash_outflows_30d": ncof,
        "available_stable_funding": np.round(nsfr * rsf, 1), "required_stable_funding": rsf,
    }
    return capital, liquidity


def _insurer_series(inst_id: int, name: str, itype: str) -> dict:
    base = _institution_base(inst_id, itype)
    rng = _rng(13, inst_id)
    t = np.arange(N_QUARTERS)
    required = base["size"] * (1 + base["growth"] / 2) ** t * np.exp(rng.normal(0, 0.008, N_QUARTERS))
    if itype == "Life insurer":
        ratio = _ar_path(rng, rng.uniform(1.30, 1.40), 0.012, 1.28, 1.45)
    else:
        ratio = _ar_path(rng, rng.uniform(1.98, 2.40), 0.035, 1.90, 2.60)
    if name in _INS_STORY:
        ratio = _glide(ratio, _INS_STORY[name])
    required = np.round(required, 1)
    return {"capital_available": np.round(ratio * required, 1), "capital_required": required}


def _keep_mask(inst_id: int, include_late_filings: bool, only_late_filings: bool) -> np.ndarray:
    """Which of the 31 quarters to emit for an institution."""
    idx = np.arange(1, N_QUARTERS + 1)
    late = inst_id in late_filer_ids()
    if only_late_filings:
        return (idx == CURRENT_QUARTER_INDEX) & late
    if late and not include_late_filings:
        return idx != CURRENT_QUARTER_INDEX
    return np.ones(N_QUARTERS, dtype=bool)


def build_capital_tables(include_late_filings: bool = False, only_late_filings: bool = False) -> dict:
    qkeys = np.array([quarter_key(i) for i in range(1, N_QUARTERS + 1)])
    cap_rows, liq_rows, ins_rows = [], [], []
    for n, (name, itype, _p, _s, _l) in enumerate(INSTITUTIONS, start=1):
        keep = _keep_mask(n, include_late_filings, only_late_filings)
        if not keep.any():
            continue
        if itype in DEPOSIT_TAKING_TYPES:
            cap, liq = _deposit_taker_series(n, name, itype)
            cap_rows.append(pd.DataFrame({"institution_id": n, "quarter_key": qkeys, **cap})[keep])
            liq_rows.append(pd.DataFrame({"institution_id": n, "quarter_key": qkeys, **liq})[keep])
        else:
            ins = _insurer_series(n, name, itype)
            basis = "LICAT total" if itype == "Life insurer" else "MCT"
            ins_rows.append(pd.DataFrame({"institution_id": n, "quarter_key": qkeys, "ratio_basis": basis, **ins})[keep])

    def _cat(parts, table):
        df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame({c: [] for c, _ in TABLE_SCHEMAS[table]})
        return _apply_schema(df, table)

    return {
        "fact_capital": _cat(cap_rows, "fact_capital"),
        "fact_liquidity": _cat(liq_rows, "fact_liquidity"),
        "fact_insurance_capital": _cat(ins_rows, "fact_insurance_capital"),
    }


# ----------------------------------------------------------------------------- mortgages
_LTV_INSURED = [  # (ltv_band, insured_flag, balance weight)
    ("<=60%", False, 0.20), ("<=60%", True, 0.04),
    ("60-65%", False, 0.09), ("60-65%", True, 0.02),
    ("65-70%", False, 0.10), ("65-70%", True, 0.02),
    ("70-75%", False, 0.10), ("70-75%", True, 0.02),
    ("75-80%", False, 0.12), ("75-80%", True, 0.03),
    (">80% (insured)", True, 0.26),
]
_POOLS_PER_CELL = {"D-SIB": 4.0, "Other bank": 1.0, "Trust and loan": 1.0}
_POOL_BALANCE = {"D-SIB": 21.0, "Other bank": 5.5, "Trust and loan": 3.0}   # CAD millions, mean pool at weight 1
_ARREARS_BASE = {"NL": 0.0024, "PE": 0.0017, "NS": 0.0019, "NB": 0.0021, "QC": 0.0016, "ON": 0.0012,
                 "MB": 0.0022, "SK": 0.0030, "AB": 0.0027, "BC": 0.0013, "YT": 0.0018, "NT": 0.0020, "NU": 0.0022}
_ARREARS_RISE = {"ON": 0.00034, "BC": 0.00029}   # per quarter after 2024 Q4 (quarter_index 24)
_RISE_FROM_INDEX = 24


def province_footprint(inst_id: int, itype: str) -> list:
    """Provinces where an institution has a mortgage book (D-SIBs: all 13)."""
    codes = [p[0] for p in PROVINCES]
    if itype == "D-SIB":
        return codes
    rng = _rng(3, inst_id)
    hq = INSTITUTIONS[inst_id - 1][2]
    k = int(rng.integers(4, 10)) if itype == "Other bank" else int(rng.integers(2, 7))
    others = [c for c in codes if c != hq]
    w = np.array([p[4] for p in PROVINCES if p[0] != hq])
    picked = rng.choice(others, size=k - 1, replace=False, p=w / w.sum())
    return [c for c in codes if c == hq or c in set(picked)]


def _arrears_rate(prov: np.ndarray, q_index: int) -> np.ndarray:
    base = np.array([_ARREARS_BASE[p] for p in prov])
    rise = np.array([_ARREARS_RISE.get(p, 0.0) for p in prov]) * max(0, q_index - _RISE_FROM_INDEX)
    return base + rise


def _mortgage_slice(inst_id: int, itype: str, q_index: int, scale_factor: float) -> dict:
    rng = _rng(7, inst_id, q_index)
    provs = province_footprint(inst_id, itype)
    pw = {p[0]: p[4] for p in PROVINCES}
    # Cartesian product of the cell attributes (vectorised)
    n_li, n_am, n_ch = len(_LTV_INSURED), len(AMORTIZATION_BANDS), len(CHANNELS)
    P, L, A, C = np.meshgrid(np.arange(len(provs)), np.arange(n_li), np.arange(n_am), np.arange(n_ch), indexing="ij")
    P, L, A, C = P.ravel(), L.ravel(), A.ravel(), C.ravel()
    prov = np.array(provs)[P]
    ltv = np.array([x[0] for x in _LTV_INSURED])[L]
    insured = np.array([x[1] for x in _LTV_INSURED])[L]
    w_ltv = np.array([x[2] for x in _LTV_INSURED])[L]
    # longer amortizations grow after the 2022-2023 rate rise
    long_share = 0.07 + 0.06 * min(1.0, max(0.0, (q_index - 14) / 8))
    w_am = np.array([0.93 - long_share - 0.29, 0.29, long_share])[A]
    w_am = np.where(insured & (A == 2), w_am * 0.15, w_am)            # few insured >30y
    high_ltv_unins = (~insured) & np.isin(ltv, HIGH_LTV_UNINSURED_BANDS)
    w_ch = np.array([0.50, 0.30, 0.20])[C]
    w_ch = np.where(high_ltv_unins & (C == 1), w_ch * 1.8, w_ch)        # broker skews to uninsured high-LTV
    w_ch = np.where(high_ltv_unins & (C == 2), w_ch * 1.15, w_ch)
    weight = np.array([pw[p] for p in prov]) * w_ltv * w_am * w_ch * (13 * 11 * 9)

    expected = _POOLS_PER_CELL[itype] * scale_factor
    n_pools = np.floor(expected).astype(int) + (rng.random(P.size) < (expected - np.floor(expected))).astype(int)
    rep = np.repeat(np.arange(P.size), n_pools)
    if rep.size == 0:
        return {}
    growth = (1 + 0.011) ** (q_index - 1)
    balance = _POOL_BALANCE[itype] * growth * weight[rep] * np.exp(rng.normal(0, 0.35, rep.size))
    balance = np.round(np.maximum(balance, 0.05), 4)
    avg_loan = np.where(np.isin(prov[rep], ("ON", "BC")), 0.42, 0.26) * np.exp(rng.normal(0, 0.08, rep.size))
    loan_count = np.maximum(1, np.round(balance / avg_loan)).astype(np.int32)
    mult = np.ones(rep.size)
    mult *= np.where(A[rep] == 2, 1.45, 1.0)
    mult *= np.where(C[rep] == 1, 1.25, 1.0)
    mult *= np.where(high_ltv_unins[rep], 1.35, 1.0)
    mult *= np.where(ltv[rep] == ">80% (insured)", 1.15, 1.0)
    rate = _arrears_rate(prov[rep], q_index) * mult * np.exp(rng.normal(0, 0.25, rep.size))
    arrears = np.round(balance * rate, 4)
    return {
        "institution_id": np.full(rep.size, inst_id, dtype=np.int32),
        "quarter_key": np.full(rep.size, quarter_key(q_index), dtype=np.int32),
        "province_code": prov[rep], "ltv_band": ltv[rep], "insured_flag": insured[rep],
        "amortization_band": np.array(AMORTIZATION_BANDS)[A[rep]], "channel": np.array(CHANNELS)[C[rep]],
        "balance": balance, "loan_count": loan_count, "arrears_90d_balance": arrears,
    }


def build_fact_mortgage_exposure(scale_factor: float = 1.0, include_late_filings: bool = False,
                                 only_late_filings: bool = False) -> pd.DataFrame:
    cols = {c: [] for c, _ in TABLE_SCHEMAS["fact_mortgage_exposure"]}
    for n, (_name, itype, _p, _s, _l) in enumerate(INSTITUTIONS, start=1):
        if itype not in DEPOSIT_TAKING_TYPES:
            continue
        keep = _keep_mask(n, include_late_filings, only_late_filings)
        for q_index in np.flatnonzero(keep) + 1:
            part = _mortgage_slice(n, itype, int(q_index), scale_factor)
            for c in cols:
                if part:
                    cols[c].append(part[c])
    data = {c: (np.concatenate(v) if v else np.array([])) for c, v in cols.items()}
    return _apply_schema(pd.DataFrame(data), "fact_mortgage_exposure")


# ----------------------------------------------------------------------------- thresholds
def build_watch_thresholds(version: str = "v1") -> pd.DataFrame:
    """LONG table, identical in shape to what df_fda_watch_thresholds writes."""
    rows = []
    for rec in THRESHOLDS_WIDE[version]:
        itype, values, eff = rec[0], rec[1:7], rec[7]
        for metric, v in zip(THRESHOLD_METRICS, values):
            if v is not None:
                rows.append({"institution_type": itype, "metric": metric, "watch_threshold": float(v),
                             "effective_from_quarter": eff, "source_file": THRESHOLD_FILES[version]})
    return _apply_schema(pd.DataFrame(rows), "supervisory_watch_thresholds")


def build_thresholds_workbook(version: str, path: str) -> str:
    """Write the styled WIDE Excel file the Dataflow Gen2 demo reads (row 4 = headers)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Watch thresholds"
    headers = ["institution_type", *THRESHOLD_METRICS, "effective_from_quarter"]
    teal, dark, grey = "1FB58F", "1F1F1F", "D9D9D9"
    ws["A1"] = ("Internal watch thresholds (illustrative) — Supervision Analytics · " + BANNER)
    ws["A1"].font = Font(bold=True, size=13, color=dark)
    ws["A2"] = f"Last reviewed: {THRESHOLD_LAST_REVIEWED[version]}"
    ws["A2"].font = Font(italic=True, color="595959")
    thin = Side(style="thin", color=grey)
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=4, column=col, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=teal)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    for r, rec in enumerate(THRESHOLDS_WIDE[version], start=5):
        for col, v in enumerate(rec, start=1):
            c = ws.cell(row=r, column=col, value=v)
            c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            if 2 <= col <= 7 and v is not None:
                c.number_format = "0.0%"
                c.alignment = Alignment(horizontal="right")
            if col == 8:
                c.number_format = "0"
                c.alignment = Alignment(horizontal="center")
        if r % 2 == 0:
            for col in range(1, len(headers) + 1):
                ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor="F2F2F2")
    widths = [18, 12, 14, 9, 9, 12, 9, 22]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "B5"

    notes = wb.create_sheet("Notes")
    lines = [
        ("Notes", True),
        (BANNER, True),
        ("These are INTERNAL WATCH THRESHOLDS (ILLUSTRATIVE) for a training demo. They are NOT OSFI regulatory minimums, targets or guidance.", False),
        ("Every institution in the demo data is fictitious.", False),
        ("Layout: one row per institution_type (wide). Blank = not applicable to that institution type.", False),
        ("Ratios are stored as decimals and formatted as %, e.g. 11.5% is stored as 0.115.", False),
        ("Dataflow Gen2 df_fda_watch_thresholds reads the sheet 'Watch thresholds': skip 3 rows, promote headers,", False),
        ("unpivot the metric columns, remove nulls, set types, add source_file -> LONG table supervisory_watch_thresholds.", False),
        ("effective_from_quarter is kept for audit; the semantic model applies the thresholds currently loaded.", False),
        (f"Version: {version} ({THRESHOLD_FILES[version]}), last reviewed {THRESHOLD_LAST_REVIEWED[version]}.", False),
    ]
    if version == "v2":
        lines.append(("Changes vs v1: Other bank CET1 ratio 11.5% -> 12.0%; Life insurer LICAT total 120% -> 125% (effective 2026 Q3).", True))
    for r, (text, bold) in enumerate(lines, start=1):
        notes.cell(row=r, column=1, value=text).font = Font(bold=bold)
    notes.column_dimensions["A"].width = 120
    wb.save(path)
    return path


# ----------------------------------------------------------------------------- entry points
def generate_all(scale_factor: float = 1.0, include_late_filings: bool = False, thresholds_version: str = "v1") -> dict:
    """All tables as pandas DataFrames. Default = the deploy state (late filers' 2026 Q3 missing)."""
    tables = {
        "dim_institution": build_dim_institution(),
        "dim_quarter": build_dim_quarter(),
        "dim_province": build_dim_province(),
    }
    tables.update(build_capital_tables(include_late_filings=include_late_filings))
    tables["fact_mortgage_exposure"] = build_fact_mortgage_exposure(scale_factor, include_late_filings=include_late_filings)
    tables["supervisory_watch_thresholds"] = build_watch_thresholds(thresholds_version)
    return {k: tables[k] for k in TABLE_ORDER}


def generate_late_filings(scale_factor: float = 1.0) -> dict:
    """Only the 10 late filers' 2026 Q3 rows (what nb_fda_02_land_late_filings appends)."""
    tables = build_capital_tables(only_late_filings=True)
    tables["fact_mortgage_exposure"] = build_fact_mortgage_exposure(scale_factor, only_late_filings=True)
    return {k: tables[k] for k in FACT_TABLES}


if __name__ == "__main__":
    import time
    t0 = time.time()
    data = generate_all()
    for name, df in data.items():
        print(f"{name:32s} {len(df):>10,d}")
    print(f"generated in {time.time() - t0:.1f}s")
