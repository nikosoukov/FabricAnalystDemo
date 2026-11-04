# SYNTHETIC DATA · for training only · no OSFI data
"""
Local checks for the FDA demo kit. pytest-compatible; also runs without pytest:
    python tests/test_generator.py
Covers: generator counts/ranges/storylines/determinism, the FROZEN values quoted in the deck,
banned real-institution names, notebooks (nbformat + embedded generator), RDL XML, TMDL vs builder,
dataflow output schema, Excel files, JSON files, banners, and a PowerShell bracket/quote balance check
(pwsh is not available in the build environment).
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

import pandas as pd

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "data_gen"))
sys.path.insert(0, os.path.join(KIT, "model"))
sys.path.insert(0, os.path.join(KIT, "notebooks"))
sys.path.insert(0, os.path.join(KIT, "paginated"))
import gen_supervisory_data as g  # noqa: E402

BANNER = "SYNTHETIC DATA · for training only · no OSFI data"
_CACHE = {}


def data(kind="dev"):
    if kind not in _CACHE:
        if kind == "dev":
            _CACHE[kind] = g.generate_all(1.0)
        elif kind == "full":
            _CACHE[kind] = g.generate_all(1.0, include_late_filings=True)
        elif kind == "test":
            _CACHE[kind] = g.generate_all(0.25)
        elif kind == "late":
            _CACHE[kind] = g.generate_late_filings(1.0)
    return _CACHE[kind]


def expected():
    with open(os.path.join(KIT, "docs", "expected-values.json"), encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- banned names
BANNED_SUBSTRINGS = [
    "royal", "toronto-dominion", "montreal", "nova scotia", "scotia", "cibc", "imperial", "national bank",
    "desjardins", "laurentian", "equitable", "home trust", "manulife", "sun life", "canada life",
    "great-west", "great west", "industrial alliance", "intact", "aviva", "co-operators", "cooperators",
    "wawanesa", "concentra", "hsbc", "tangerine", "simplii", "mcan", "peoples", "haventree", "western",
    "versabank", "coast capital", "vancity", "meridian", "first national", "sagen", "canada guaranty",
    "definity", "beneva", "empire life", "foresters", "industrial", "rbc", "bmo", "atb", "cwb",
    "td bank", "dominion", "nova", "laurentide", "haven", "empire", "equi",
]
BANNED_WORDS = ["td", "eq", "ia", "rbc", "bmo", "atb", "cwb"]          # short acronyms: whole word
DISTINCTIVE = ["manulife", "desjardins", "scotiabank", "laurentian", "tangerine", "simplii", "wawanesa",
               "haventree", "versabank", "vancity", "definity", "beneva", "concentra", "co-operators",
               "home trust", "sun life", "canada life", "great-west", "first national", "canada guaranty",
               "coast capital", "hsbc", "cibc", "royal bank", "toronto-dominion", "bank of montreal",
               "national bank", "equitable bank", "empire life", "industrial alliance", "mcan", "sagen"]


def test_no_banned_names_in_institutions_or_leads():
    names = [r[0] for r in g.INSTITUTIONS] + list(g.SUPERVISORY_LEADS)
    for n in names:
        low = n.lower()
        for b in BANNED_SUBSTRINGS:
            assert b not in low, f"{n!r} contains banned {b!r}"
        words = re.findall(r"[a-z]+", low)
        for w in BANNED_WORDS:
            assert w not in words, f"{n!r} contains banned word {w!r}"
        if n in [r[0] for r in g.INSTITUTIONS]:   # institutions: even 2-letter tokens banned as substrings
            assert "ia" not in low and "td" not in low and "eq" not in low, f"{n!r} contains a short banned token"


def test_no_real_fi_names_anywhere_in_kit():
    for path in _kit_text_files():
        if path.endswith("test_generator.py"):
            continue
        text = open(path, encoding="utf-8", errors="ignore").read().lower()
        for b in DISTINCTIVE:
            assert b not in text, f"{path} mentions {b!r}"


# --------------------------------------------------------------------------- counts and shape
def test_institutions():
    inst = data()["dim_institution"]
    assert len(inst) == 40
    assert inst.institution_code.tolist() == [f"FI{i:03d}" for i in range(1, 41)]
    assert inst.institution_name.is_unique
    assert inst.institution_type.value_counts().to_dict() == {"D-SIB": 6, "Other bank": 10, "Trust and loan": 6, "Life insurer": 9, "P&C insurer": 9}
    assert int(inst.is_late_filer_2026q3.sum()) == 10
    assert inst[inst.is_late_filer_2026q3].institution_type.nunique() == 5
    assert (inst.intervention_stage == 2).sum() == 1 and (inst.intervention_stage == 1).sum() >= 2
    assert set(inst.sector) == {"Deposit-taking", "Insurance"}


def test_quarters_and_provinces():
    q = data()["dim_quarter"]
    assert len(q) == 31 and q.quarter_key.iloc[0] == 20191 and q.quarter_key.iloc[-1] == 20263
    assert q.quarter_label.iloc[-1] == "2026 Q3" and q.is_current.sum() == 1 and bool(q.is_current.iloc[-1])
    assert q.quarter_index.tolist() == list(range(1, 32))
    assert len(data()["dim_province"]) == 13


def test_row_counts_match_expected_json():
    ev = expected()["row_counts"]
    assert {k: len(v) for k, v in data().items()} == ev["dev_initial"]
    assert {k: len(v) for k, v in data("late").items()} == ev["late_filings_landed"]
    assert {k: len(v) for k, v in data("full").items()} == ev["dev_after_landing"]
    assert {k: len(v) for k, v in data("test").items()} == ev["test_initial_scale_0_25"]
    assert 1_000_000 <= ev["dev_initial"]["fact_mortgage_exposure"] <= 1_500_000


def test_schemas_and_dtypes():
    for name, df in data().items():
        assert list(df.columns) == [c for c, _ in g.TABLE_SCHEMAS[name]], name
        for c, t in g.TABLE_SCHEMAS[name]:
            assert str(df[c].dtype) == g._PANDAS_DTYPES[t], (name, c, df[c].dtype)


# --------------------------------------------------------------------------- ratio ranges
STORY_CET1 = {"Cedarline Bank", "Driftwood Bank", "Ashgrove Bank", "Larchmont Bank"}


def test_ratio_ranges():
    d = data("full")
    inst = d["dim_institution"].set_index("institution_id")
    cap = d["fact_capital"].join(inst, on="institution_id")
    cap["cet1"] = cap.cet1_capital / cap.rwa
    cap["lev"] = cap.tier1_capital / cap.leverage_exposure
    dsib = cap[cap.institution_type == "D-SIB"]
    assert dsib.cet1.between(0.12, 0.145).all()
    other = cap[(cap.institution_type != "D-SIB") & (~cap.institution_name.isin(STORY_CET1))]
    assert other.cet1.between(0.13 - 0.005, 0.18).all(), other.cet1.min()
    assert cap.lev.between(0.042, 0.058).all()
    assert (cap.cet1_capital < cap.tier1_capital).all() and (cap.tier1_capital < cap.total_capital).all()
    liq = d["fact_liquidity"]
    assert (liq.hqla / liq.net_cash_outflows_30d).between(1.15, 1.65).all()
    assert (liq.available_stable_funding / liq.required_stable_funding).between(1.08, 1.30).all()
    ins = d["fact_insurance_capital"]
    r = ins.capital_available / ins.capital_required
    assert r[ins.ratio_basis == "LICAT total"].between(1.15, 1.45).all()
    assert r[ins.ratio_basis == "MCT"].between(1.70, 2.60).all()
    m = d["fact_mortgage_exposure"]
    assert (m.balance > 0).all() and (m.loan_count >= 1).all() and (m.arrears_90d_balance >= 0).all()
    assert m[m.ltv_band == ">80% (insured)"].insured_flag.all()


# --------------------------------------------------------------------------- frozen deck values
def test_frozen_values_quoted_in_deck():
    ev = expected()
    r = ev["reporting_2026q3"]
    assert (r["before_landing"]["total"], r["after_landing"]["total"]) == (30, 40)
    assert (r["before_landing"]["filing_completeness_pct"], r["after_landing"]["filing_completeness_pct"]) == (75.0, 100.0)
    b = ev["below_cet1_watch_2026q3"]
    assert (b["before_landing_v1"]["count"], b["after_landing_v1"]["count"], b["after_landing_v2"]["count"]) == (1, 2, 4)
    i = ev["insurers_below_capital_watch_2026q3"]
    assert (i["after_landing_v1"]["count"], i["after_landing_v2"]["count"]) == (2, 4)
    assert round(ev["cedarline_bank"]["cet1"]["20263"] * 100, 2) == 11.38 and ev["cedarline_bank"]["threshold_v1"] == 0.115
    top = ev["top5_cet1_qoq_drops_q2_q3"]["after_landing"][0]
    assert top["institution"] == "Driftwood Bank" and top["pp"] == -1.41
    l0 = ev["lcr_drops_2026q3"][0]
    assert l0["institution"] == "Stonebridge Bank" and round(l0["q2"] * 100, 1) == 148.2 and round(l0["q3"] * 100, 1) == 118.7
    c = ev["cet1_ratio_by_type"]["2026 Q3 after landing"]
    assert [round(c[k] * 100, 2) for k in ("D-SIB", "Other bank", "Trust and loan")] == [13.09, 13.98, 14.96]


def test_expected_json_is_current():
    import expected_values as evm
    fresh = json.loads(json.dumps(evm.compute(), default=str))
    assert fresh == expected(), "docs/expected-values.json is stale: run python data_gen/expected_values.py"
    with open(os.path.join(KIT, "docs", "expected-values.md"), encoding="utf-8") as f:
        assert f.read() == evm.render_markdown(fresh), "docs/expected-values.md is stale"


def test_storylines():
    d, full = data(), data("full")
    inst = d["dim_institution"]
    late = set(inst[inst.is_late_filer_2026q3].institution_id)
    for t in g.FACT_TABLES:
        q3 = set(d[t][d[t].quarter_key == 20263].institution_id)
        assert not (q3 & late), t
        q2 = set(d[t][d[t].quarter_key == 20262].institution_id)
        assert q2 == (q2 | (set(full[t][full[t].quarter_key == 20262].institution_id)))
    # mortgage arrears rising in ON and BC
    m = full["fact_mortgage_exposure"]

    def rate(p, q):
        s = m[(m.province_code == p) & (m.quarter_key == q)]
        return s.arrears_90d_balance.sum() / s.balance.sum()
    for p in ("ON", "BC"):
        assert rate(p, 20263) > 2 * rate(p, 20243)
    ch = m[m.quarter_key == 20263]
    hl = (~ch.insured_flag) & ch.ltv_band.isin(g.HIGH_LTV_UNINSURED_BANDS)
    share = ch[hl].groupby("channel").balance.sum() / ch.groupby("channel").balance.sum()
    assert share["Broker"] > share["Branch"] and share["Broker"] > share["Digital"]


def test_landing_reproduces_full_run():
    d, late, full = data(), data("late"), data("full")
    for t in g.FACT_TABLES:
        a = pd.concat([d[t], late[t]], ignore_index=True)
        keys = list(a.columns)
        a = a.sort_values(keys).reset_index(drop=True)
        b = full[t].sort_values(keys).reset_index(drop=True)
        assert a.equals(b), t


def test_determinism():
    def digest(df):
        return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()
    a = g.generate_all(0.25)
    b = data("test")
    for t in a:
        assert digest(a[t]) == digest(b[t]), t


# --------------------------------------------------------------------------- thresholds, Excel, dataflow
def _dataflow_output_columns():
    pq = open(os.path.join(KIT, "dataflow", "df_fda_watch_thresholds", "mashup.pq"), encoding="utf-8").read()
    m = re.search(r"Result = Table\.SelectColumns\(AddedSourceFile, \{([^}]*)\}\)", pq)
    return [c.strip().strip('"') for c in m.group(1).split(",")]


def test_dataflow_output_matches_table_schema():
    assert _dataflow_output_columns() == [c for c, _ in g.TABLE_SCHEMAS["supervisory_watch_thresholds"]]
    pq = open(os.path.join(KIT, "dataflow", "df_fda_watch_thresholds", "mashup.pq"), encoding="utf-8").read()
    assert pq.startswith("// " + BANNER) and "section Section1;" in pq and "shared supervisory_watch_thresholds" in pq
    assert '{"effective_from_quarter", Int64.Type}' in pq and g.TABLE_SCHEMAS["supervisory_watch_thresholds"][3] == ("effective_from_quarter", "long")
    meta = json.load(open(os.path.join(KIT, "dataflow", "df_fda_watch_thresholds", "queryMetadata.json"), encoding="utf-8"))
    assert "supervisory_watch_thresholds" in meta["queriesMetadata"]


def test_excel_files_emulate_dataflow():
    import openpyxl
    for version in ("v1", "v2"):
        path = os.path.join(KIT, "excel", g.THRESHOLD_FILES[version])
        wb = openpyxl.load_workbook(path)
        ws = wb["Watch thresholds"]
        assert "Notes" in wb.sheetnames
        assert ws["A1"].value.startswith("Internal watch thresholds (illustrative)") and BANNER in ws["A1"].value
        assert ws["A2"].value == f"Last reviewed: {g.THRESHOLD_LAST_REVIEWED[version]}"
        rows = list(ws.iter_rows(values_only=True))
        assert all(v is None for v in rows[2])
        # emulate the dataflow: skip 3 rows, promote headers, unpivot, remove nulls, types, source_file
        hdr, body = rows[3], rows[4:]
        wide = pd.DataFrame(body, columns=hdr)
        long = wide.melt(id_vars=["institution_type", "effective_from_quarter"], var_name="metric", value_name="watch_threshold").dropna(subset=["watch_threshold"])
        long["source_file"] = os.path.basename(path)
        long = long[_dataflow_output_columns()]
        ref = g.build_watch_thresholds(version)
        key = ["institution_type", "metric"]
        a = long.sort_values(key).reset_index(drop=True)
        b = ref.sort_values(key).reset_index(drop=True)
        assert a[key].values.tolist() == b[key].values.tolist()
        assert (a.watch_threshold.astype(float).values == b.watch_threshold.values).all()
        assert (a.effective_from_quarter.astype(int).values == b.effective_from_quarter.values).all()
        assert (a.source_file.values == b.source_file.values).all()
        assert ws["B5"].number_format.endswith("%")


# --------------------------------------------------------------------------- notebooks
def test_notebooks():
    import build_notebooks as bn
    gen_cell = bn.embedded_generator_cell_source()
    for name in ("nb_fda_00_generate_data", "nb_fda_01_analyst_explore", "nb_fda_02_land_late_filings"):
        nb = json.load(open(os.path.join(KIT, "notebooks", f"{name}.ipynb"), encoding="utf-8"))
        assert nb["nbformat"] == 4 and nb["metadata"]["kernelspec"]["name"] == "synapse_pyspark"
        first = nb["cells"][0]
        assert first["cell_type"] == "markdown" and BANNER in "".join(first["source"]) and name in "".join(first["source"])
        for c in nb["cells"]:
            assert c["cell_type"] in ("markdown", "code") and isinstance(c["source"], list)
            if c["cell_type"] == "code":
                src = "".join(c["source"])
                if not src.startswith("%%"):
                    compile(src, name, "exec")
        if name != "nb_fda_01_analyst_explore":
            params = [c for c in nb["cells"] if "parameters" in c["metadata"].get("tags", [])]
            assert len(params) == 1
            assert any("".join(c["source"]) == gen_cell.strip("\n") for c in nb["cells"]), f"{name}: embedded generator is stale"
    try:
        import nbformat
        for p in glob.glob(os.path.join(KIT, "notebooks", "*.ipynb")):
            nbformat.validate(nbformat.read(p, as_version=4))
    except ImportError:
        pass   # nbformat not installed: structural checks above still apply


def test_embedded_generator_runs_standalone():
    import build_notebooks as bn
    ns = {"__name__": "embedded"}
    exec(bn.embedded_generator_cell_source(), ns)
    assert {k: len(v) for k, v in ns["generate_late_filings"]().items()} == expected()["row_counts"]["late_filings_landed"]


def test_nb01_uses_exact_measure_names():
    nb = json.load(open(os.path.join(KIT, "notebooks", "nb_fda_01_analyst_explore.ipynb"), encoding="utf-8"))
    src = "".join("".join(c["source"]) for c in nb["cells"])
    assert 'list_measures("sm_fda_supervisory")' in src
    assert 'measure=["CET1 Ratio", "Institutions Reporting"]' in src
    assert 'groupby_columns=["dim_quarter[quarter_label]", "dim_institution[institution_type]"]' in src
    assert "analyst_outliers" in src and "%%sql" in src


# --------------------------------------------------------------------------- semantic models
SPEC_MEASURES = ["CET1 Ratio", "Tier 1 Ratio", "Total Capital Ratio", "Leverage Ratio", "LCR", "NSFR",
                 "Insurance Capital Ratio", "CET1 Ratio QoQ Change (pp)", "Institutions Reporting",
                 "Institutions Expected", "Filing Completeness %", "CET1 Watch Threshold",
                 "Institutions Below CET1 Watch", "LICAT Watch Threshold", "Insurers Below Capital Watch",
                 "Mortgage Balance", "Uninsured High-LTV Share", "Arrears 90d Rate"]


def test_tmdl_matches_builder_and_spec():
    import build_models as bm
    files = bm.build()
    on_disk = {}
    for model in bm.MODELS:
        for p in glob.glob(os.path.join(KIT, "model", model, "**", "*"), recursive=True):
            if os.path.isfile(p):
                on_disk[os.path.relpath(p, os.path.join(KIT, "model")).replace(os.sep, "/")] = open(p, encoding="utf-8").read()
    assert on_disk == files, "model/ output is stale: run python model/build_models.py"
    assert sorted(bm.MEASURE_NAMES) == sorted(SPEC_MEASURES)
    for model, mode in bm.MODELS.items():
        assert "compatibilityLevel: 1604" in files[f"{model}/definition/database.tmdl"]
        assert "discourageImplicitMeasures" in files[f"{model}/definition/model.tmdl"]
        assert files[f"{model}/definition/relationships.tmdl"].count("relationship ") == 9
        for t in g.TABLE_ORDER:
            text = files[f"{model}/definition/tables/{t}.tmdl"]
            lines = text.splitlines()
            assert lines[0].startswith("/// ") and lines[1] == f"table {t}"
            for i, ln in enumerate(lines):
                if ln.startswith("\tmeasure "):
                    assert lines[i - 1].startswith("\t/// "), f"{model}/{t}: measure without description: {ln}"
            if mode == "directLake":
                assert "mode: directLake" in text and "schemaName: dbo" in text and "expressionSource: DatabaseQuery" in text
            else:
                assert "mode: import" in text and 'Sql.Database(SqlEndpoint, "lh_supervisory")' in text and f'Item = "{t}"' in text
        assert "sortByColumn: quarter_key" in files[f"{model}/definition/tables/dim_quarter.tmdl"]
    assert "__SQL_ENDPOINT_ID__" in files["sm_fda_supervisory/definition/expressions.tmdl"]
    assert "IsParameterQuery = true" in files["sm_fda_supervisory_import/definition/expressions.tmdl"]


def test_tmdl_indentation_is_tabs():
    for p in glob.glob(os.path.join(KIT, "model", "**", "*.tmdl"), recursive=True):
        for n, ln in enumerate(open(p, encoding="utf-8").read().splitlines(), 1):
            lead = ln[: len(ln) - len(ln.lstrip(" \t"))]
            assert " " not in lead or lead.startswith("\t"), f"{p}:{n} space indentation (TMDL structure must use tabs)"


# --------------------------------------------------------------------------- paginated report
def test_rdl():
    path = os.path.join(KIT, "paginated", "rpt_fda_institution_return.rdl")
    text = open(path, encoding="utf-8").read()
    root = ET.fromstring(text.encode("utf-8"))
    ns = {"r": "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"}
    assert root.tag.endswith("Report")
    assert root.find(".//r:DataProvider", ns).text == "PBIDATASET"
    cs = root.find(".//r:ConnectString", ns).text
    assert "__TENANT_ID__" in cs and "sobe_wowvirtualserver-__DATASET_ID__" in cs and "Integrated Security=ClaimsToken" in cs
    p = root.find(".//r:ReportParameter", ns)
    assert p.get("Name") == "Institution" and p.find("r:MultiValue", ns).text == "true"
    assert p.find(".//r:Value", ns).text == "FI007" and g.INSTITUTIONS[6][0] == "Cedarline Bank"
    assert root.find(".//r:PageWidth", ns).text == "8.5in" and root.find(".//r:PageHeight", ns).text == "11in"
    assert root.find(".//r:BreakLocation", ns).text == "Between"
    footer = root.find(".//r:PageFooter", ns)
    assert BANNER in ET.tostring(footer, encoding="unicode") and "Globals!TotalPages" in ET.tostring(footer, encoding="unicode")
    assert "Quarterly supervisory return — " in text and "#C00000" in text
    for m in ("[CET1 Ratio]", "[Institutions Reporting]", "[CET1 Watch Threshold]", "[Insurance Capital Ratio]"):
        assert m in text
    import build_rdl
    assert build_rdl.build() == text, "RDL is stale: run python paginated/build_rdl.py"


# --------------------------------------------------------------------------- JSON, banners, docs
def test_json_files_load():
    for p in glob.glob(os.path.join(KIT, "**", "*.json"), recursive=True) + glob.glob(os.path.join(KIT, "**", "*.ipynb"), recursive=True):
        if os.sep + "out" + os.sep in p:
            continue
        json.load(open(p, encoding="utf-8"))
    theme = json.load(open(os.path.join(KIT, "theme", "osfi-dark-theme.json"), encoding="utf-8"))
    assert theme["background"] == "#000000" and "#1FB58F" in theme["dataColors"] and "#2DD4A7" in theme["dataColors"]
    cfg = json.load(open(os.path.join(KIT, "scripts", "config.sample.json"), encoding="utf-8"))
    for k in ("tenantId", "capacityId", "presenterUpn", "devWorkspaceName", "testWorkspaceName", "scaleFactor", "testScaleFactor"):
        assert k in cfg
    assert cfg["devWorkspaceName"] == "FDA-Analyst-Dev" and cfg["testWorkspaceName"] == "FDA-Analyst-Test"


def _kit_text_files():
    exts = (".py", ".ps1", ".sql", ".pq", ".md", ".rdl", ".tmdl", ".json", ".ipynb", ".pbism")
    out = []
    for root, dirs, files in os.walk(KIT):
        dirs[:] = [d for d in dirs if d not in ("out", "__pycache__", ".git")]
        out += [os.path.join(root, f) for f in files if f.endswith(exts)]
    return out


def test_banners():
    for p in _kit_text_files():
        if p.endswith((".py", ".ps1", ".sql", ".pq", ".rdl")) or os.path.basename(p) == "README.md":
            head = open(p, encoding="utf-8").read()[:600]
            assert BANNER in head, f"banner missing at top of {p}"


def test_docs_quote_expected_values():
    ev = expected()
    readme = open(os.path.join(KIT, "README.md"), encoding="utf-8").read()
    cheat = open(os.path.join(KIT, "docs", "demo-script-cheatsheet.md"), encoding="utf-8").read()
    for text in (readme, cheat):
        for s in ("30", "40", "75.00%", "100.00%", "11.38%", "Cedarline Bank", "Driftwood Bank", "Stonebridge Bank", "148.2%", "118.7%"):
            assert s in text, f"missing {s!r}"
    for s in ("13.09%", "13.98%", "14.96%", "1,211,265", "1,218,393", "302,936", "0.47%", "0.44%", "0.16%", "0.17%"):
        assert s in readme, f"README missing {s!r}"
    for d in ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"):
        assert f"### {d} " in readme
    for name in ("FDA-Analyst-Dev", "FDA-Analyst-Test", "lh_supervisory", "wh_analyst_sandbox", "nb_fda_00_generate_data",
                 "nb_fda_01_analyst_explore", "nb_fda_02_land_late_filings", "sm_fda_supervisory", "sm_fda_supervisory_import",
                 "rpt_fda_supervisory_overview", "rpt_fda_institution_return", "df_fda_watch_thresholds", "dp_fda_analyst",
                 "supervisory_watch_thresholds.xlsx", "supervisory_watch_thresholds_v2.xlsx", "fabric-analyst-workshop"):
        assert name in readme, name
    assert "internal watch thresholds (illustrative)" in readme.lower()
    assert ev["below_cet1_watch_2026q3"]["after_landing_v2"]["count"] == 4


# --------------------------------------------------------------------------- PowerShell (static)
def _ps_balance(text, path):
    """Bracket/quote balance for PowerShell: comments, '..', "..", $( ) inside "..", backtick escapes."""
    stack, i, n, line = [], 0, len(text), 1
    pairs = {")": "(", "}": "{", "]": "["}

    def err(msg):
        raise AssertionError(f"{path}:{line}: {msg}")

    def scan_code(i, stop=None):
        nonlocal line
        while i < n:
            ch = text[i]
            if ch == "\n":
                line += 1
            if text.startswith("<#", i):
                j = text.find("#>", i)
                if j < 0:
                    err("unclosed block comment")
                line += text.count("\n", i, j)
                i = j + 2
                continue
            if ch == "#":
                j = text.find("\n", i)
                i = n if j < 0 else j
                continue
            if ch == "'":
                j = i + 1
                while True:
                    k = text.find("'", j)
                    if k < 0:
                        err("unclosed single-quoted string")
                    if text.startswith("''", k):
                        j = k + 2
                        continue
                    break
                line += text.count("\n", i, k)
                i = k + 1
                continue
            if ch == '"':
                i = scan_dq(i + 1)
                continue
            if ch == "`":
                i += 2
                continue
            if ch in "({[":
                stack.append((ch, line))
            elif ch in ")}]":
                if stop is not None and ch == ")" and len(stack) == stop:
                    return i + 1
                if not stack or stack[-1][0] != pairs[ch]:
                    err(f"unbalanced {ch}")
                stack.pop()
            i += 1
        return i

    def scan_dq(i):
        nonlocal line
        while i < n:
            ch = text[i]
            if ch == "\n":
                line += 1
            if ch == "`":
                i += 2
                continue
            if ch == '"':
                if text.startswith('""', i):
                    i += 2
                    continue
                return i + 1
            if text.startswith("$(", i):
                depth = len(stack)
                i = scan_code(i + 2, stop=depth)
                continue
            i += 1
        err("unclosed double-quoted string")

    scan_code(0)
    if stack:
        err(f"unclosed {stack[-1][0]} opened at line {stack[-1][1]}")


BUILTIN_CMDLETS = {"Get-AzContext", "Get-Item", "Get-ChildItem", "Get-Content", "Set-Content", "New-Item", "Test-Path",
                   "Get-Date", "Get-Command", "Get-Module", "Invoke-WebRequest", "Invoke-RestMethod", "Invoke-Sqlcmd",
                   "Get-AzAccessToken", "Write-Host", "Read-Host", "Start-Sleep", "ConvertTo-Json", "ConvertFrom-Json"}


def test_powershell_static():
    for p in glob.glob(os.path.join(KIT, "scripts", "*.ps1")):
        text = open(p, encoding="utf-8").read()
        assert text.lstrip("\ufeff").startswith(("#Requires", "<#")), p
        _ps_balance(text, p)
        assert "******" not in text and "Bearer" not in text.replace("'Bearer '", ""), f"{p}: inline bearer token text"
    common = open(os.path.join(KIT, "scripts", "FdaCommon.ps1"), encoding="utf-8").read()
    deploy = open(os.path.join(KIT, "scripts", "01-Deploy-FdaEnvironment.ps1"), encoding="utf-8").read()
    for sw in ("SkipTest", "SkipImportModel", "SkipPaginated", "SkipDataflow", "SkipPipeline", "ScaleFactor"):
        assert f"[switch]${sw}" in deploy or f"${sw} =" in deploy, sw
    defined = set(re.findall(r"^function\s+([\w-]+)", common, re.M)) | set(re.findall(r"^function\s+([\w-]+)", deploy, re.M))
    for fn in ("Invoke-Fabric", "Set-ItemWithDefinition", "Get-NotebookDefinition", "Start-NotebookRun", "Invoke-FabricSql", "Update-SqlEndpointMetadata", "Start-DatasetRefresh"):
        assert fn in defined, fn
    for p in glob.glob(os.path.join(KIT, "scripts", "*.ps1")):
        text = open(p, encoding="utf-8").read()
        used = set(re.findall(r"\b((?:Get|Set|New|Invoke|Start|Find|Test|Update|Read|Assert|Connect|Write|ConvertTo|ConvertFrom|Wait)-Fda\w*|(?:Get|Set|New|Invoke|Start|Find|Test|Update|Wait)-(?:Fabric|Lakehouse|OneLake|SqlEndpoint|Notebook|Dataset|PowerBI|Workspace|OrNew|OrGet|Model|Item|Id|Token|AuthHeader)\w*)\b", text))
        for u in used:
            assert u in defined or u in BUILTIN_CMDLETS, f"{p}: {u} is not defined"


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
