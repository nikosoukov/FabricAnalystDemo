# SYNTHETIC DATA · for training only · no OSFI data
"""
expected_values.py - computes the numbers the runbook, cheat sheet and deck quote.

Emulates the sm_fda_supervisory measures in pandas (same SUM/SUM ratio logic as the DAX)
and writes docs/expected-values.json. docs/expected-values.md is written by hand from it;
tests/test_generator.py checks that the markdown and the runbook still quote these numbers.

Run:  python data_gen/expected_values.py
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_supervisory_data as g  # noqa: E402

Q3, Q2, Q1 = 20263, 20262, 20261


def _thresholds(version: str) -> dict:
    t = g.build_watch_thresholds(version)
    return {(r.institution_type, r.metric): r.watch_threshold for r in t.itertuples()}


def cet1_by_institution(cap: pd.DataFrame, inst: pd.DataFrame) -> pd.DataFrame:
    d = cap.merge(inst[["institution_id", "institution_name", "institution_code", "institution_type", "peer_group"]], on="institution_id")
    d["cet1_ratio"] = d.cet1_capital / d.rwa
    return d


def cet1_by_type(cap, inst, qk):
    d = cap[cap.quarter_key == qk].merge(inst[["institution_id", "institution_type"]], on="institution_id")
    s = d.groupby("institution_type")[["cet1_capital", "rwa"]].sum()
    return {k: round(float(v), 6) for k, v in (s.cet1_capital / s.rwa).items()}


def below_cet1(cap, inst, qk, version):
    thr = _thresholds(version)
    d = cet1_by_institution(cap[cap.quarter_key == qk], inst)
    d["thr"] = [thr.get((t, "CET1 ratio")) for t in d.institution_type]
    hit = d[d.cet1_ratio < d.thr].sort_values("cet1_ratio")
    return int(len(hit)), [f"{r.institution_name} {r.cet1_ratio:.2%} < {r.thr:.1%}" for r in hit.itertuples()]


def below_ins(ins, inst, qk, version):
    thr = _thresholds(version)
    d = ins[ins.quarter_key == qk].merge(inst[["institution_id", "institution_name", "institution_type"]], on="institution_id")
    d["ratio"] = d.capital_available / d.capital_required
    d["thr"] = [thr.get((t, b)) for t, b in zip(d.institution_type, d.ratio_basis)]
    hit = d[d.ratio < d.thr].sort_values("ratio")
    return int(len(hit)), [f"{r.institution_name} ({r.ratio_basis}) {r.ratio:.2%} < {r.thr:.0%}" for r in hit.itertuples()]


def reporting(cap, ins, qk):
    dt = cap[cap.quarter_key == qk].institution_id.nunique()
    it = ins[ins.quarter_key == qk].institution_id.nunique()
    return {"total": int(dt + it), "deposit_taking": int(dt), "insurers": int(it),
            "filing_completeness_pct": round(100.0 * (dt + it) / 40, 2)}


def qoq_drops(cap, inst, n=5):
    d = cet1_by_institution(cap[cap.quarter_key.isin([Q2, Q3])], inst)
    p = d.pivot_table(index=["institution_name", "institution_type"], columns="quarter_key", values="cet1_ratio").dropna()
    p["pp"] = (p[Q3] - p[Q2]) * 100
    p = p.sort_values("pp").head(n)
    return [{"institution": i[0], "type": i[1], "q2": round(r[Q2], 6), "q3": round(r[Q3], 6), "pp": round(r.pp, 2)}
            for i, r in p.iterrows()]


def outliers(cap, inst):
    return [x for x in qoq_drops(cap, inst, n=40) if x["pp"] < -0.5]


def arrears(m, provs, qks):
    out = {}
    for p in provs:
        for qk in qks:
            s = m[(m.province_code == p) & (m.quarter_key == qk)]
            out[f"{p} {qk}"] = round(float(s.arrears_90d_balance.sum() / s.balance.sum()), 6)
    return out


def mortgage_summary(m, qk):
    s = m[m.quarter_key == qk]
    hl = s[(~s.insured_flag) & s.ltv_band.isin(g.HIGH_LTV_UNINSURED_BANDS)]
    by_ch = {}
    for ch in g.CHANNELS:
        sc = s[s.channel == ch]
        hc = sc[(~sc.insured_flag) & sc.ltv_band.isin(g.HIGH_LTV_UNINSURED_BANDS)]
        by_ch[ch] = round(float(hc.balance.sum() / sc.balance.sum()), 6)
    return {"rows": int(len(s)), "balance_cad_m": round(float(s.balance.sum()), 1),
            "arrears_90d_rate": round(float(s.arrears_90d_balance.sum() / s.balance.sum()), 6),
            "uninsured_high_ltv_share": round(float(hl.balance.sum() / s.balance.sum()), 6),
            "uninsured_high_ltv_share_by_channel": by_ch}


def compute() -> dict:
    dev = g.generate_all(1.0)
    late = g.generate_late_filings(1.0)
    after = {k: (pd.concat([dev[k], late[k]], ignore_index=True) if k in late else dev[k]) for k in dev}
    full = g.generate_all(1.0, include_late_filings=True)
    # landing must reproduce exactly the rows of a full run
    for k in g.FACT_TABLES:
        a = after[k].sort_values(list(after[k].columns[:2]) + ([] if k != "fact_mortgage_exposure" else ["province_code", "ltv_band", "insured_flag", "amortization_band", "channel", "balance"])).reset_index(drop=True)
        b = full[k].sort_values(list(a.columns[:2]) + ([] if k != "fact_mortgage_exposure" else ["province_code", "ltv_band", "insured_flag", "amortization_band", "channel", "balance"])).reset_index(drop=True)
        assert a.equals(b), k
    test = g.generate_all(0.25)
    inst = dev["dim_institution"]

    ev = {"_banner": g.BANNER, "seed": g.SEED, "generator_version": g.GENERATOR_VERSION}
    ev["row_counts"] = {
        "dev_initial": {k: int(len(v)) for k, v in dev.items()},
        "late_filings_landed": {k: int(len(v)) for k, v in late.items()},
        "dev_after_landing": {k: int(len(v)) for k, v in after.items()},
        "test_initial_scale_0_25": {k: int(len(v)) for k, v in test.items()},
    }
    ev["late_filers"] = inst[inst.is_late_filer_2026q3][["institution_code", "institution_name", "institution_type"]].to_dict("records")
    ev["reporting_2026q3"] = {"before_landing": reporting(dev["fact_capital"], dev["fact_insurance_capital"], Q3),
                              "after_landing": reporting(after["fact_capital"], after["fact_insurance_capital"], Q3)}
    ev["reporting_2026q2"] = reporting(dev["fact_capital"], dev["fact_insurance_capital"], Q2)
    ev["cet1_ratio_by_type"] = {
        "2026 Q2": cet1_by_type(dev["fact_capital"], inst, Q2),
        "2026 Q3 before landing": cet1_by_type(dev["fact_capital"], inst, Q3),
        "2026 Q3 after landing": cet1_by_type(after["fact_capital"], inst, Q3),
    }
    ev["below_cet1_watch_2026q3"] = {}
    for label, cap, ver in [("before_landing_v1", dev, "v1"), ("after_landing_v1", after, "v1"),
                            ("after_landing_v2", after, "v2"), ("before_landing_v2", dev, "v2")]:
        n, who = below_cet1(cap["fact_capital"], inst, Q3, ver)
        ev["below_cet1_watch_2026q3"][label] = {"count": n, "institutions": who}
    n, who = below_cet1(dev["fact_capital"], inst, Q2, "v1")
    ev["below_cet1_watch_2026q2_v1"] = {"count": n, "institutions": who}
    ev["insurers_below_capital_watch_2026q3"] = {}
    for label, d, ver in [("before_landing_v1", dev, "v1"), ("after_landing_v1", after, "v1"), ("after_landing_v2", after, "v2")]:
        n, who = below_ins(d["fact_insurance_capital"], inst, Q3, ver)
        ev["insurers_below_capital_watch_2026q3"][label] = {"count": n, "institutions": who}

    c = cet1_by_institution(after["fact_capital"], inst)
    ced = c[c.institution_name == "Cedarline Bank"].set_index("quarter_key").cet1_ratio
    ev["cedarline_bank"] = {"code": inst.set_index("institution_name").loc["Cedarline Bank", "institution_code"],
                            "cet1": {str(k): round(float(ced[k]), 6) for k in (20254, Q1, Q2, Q3)},
                            "threshold_v1": 0.115, "threshold_v2": 0.120}
    drift = c[c.institution_name == "Driftwood Bank"].set_index("quarter_key").cet1_ratio
    ev["driftwood_bank"] = {"code": inst.set_index("institution_name").loc["Driftwood Bank", "institution_code"],
                            "cet1": {str(k): round(float(drift[k]), 6) for k in (Q1, Q2, Q3)}}
    liq = after["fact_liquidity"].merge(inst[["institution_id", "institution_name", "institution_type"]], on="institution_id")
    liq["lcr"] = liq.hqla / liq.net_cash_outflows_30d
    p = liq[liq.quarter_key.isin([Q2, Q3])].pivot_table(index=["institution_name", "institution_type"], columns="quarter_key", values="lcr").dropna()
    p["chg"] = p[Q3] - p[Q2]
    worst = p.sort_values("chg").head(3)
    ev["lcr_drops_2026q3"] = [{"institution": i[0], "type": i[1], "q2": round(r[Q2], 4), "q3": round(r[Q3], 4), "pp": round(r.chg * 100, 1)} for i, r in worst.iterrows()]
    s = liq[liq.quarter_key == Q3].groupby("institution_type")[["hqla", "net_cash_outflows_30d"]].sum()
    ev["lcr_by_type_2026q3_after"] = {k: round(float(v), 4) for k, v in (s.hqla / s.net_cash_outflows_30d).items()}
    ev["top5_cet1_qoq_drops_q2_q3"] = {"after_landing": qoq_drops(after["fact_capital"], inst),
                                      "before_landing": qoq_drops(dev["fact_capital"], inst)}
    ev["analyst_outliers_2026q3"] = {"before_landing": outliers(dev["fact_capital"], inst),
                                     "after_landing": outliers(after["fact_capital"], inst)}
    m_after = after["fact_mortgage_exposure"]
    ev["arrears_90d_rate"] = {"after_landing": arrears(m_after, ["ON", "BC"], [20243, Q3]),
                              "before_landing": arrears(dev["fact_mortgage_exposure"], ["ON", "BC"], [Q3]),
                              "all_provinces_after": {str(qk): round(float(m_after[m_after.quarter_key == qk].arrears_90d_balance.sum() / m_after[m_after.quarter_key == qk].balance.sum()), 6) for qk in (20243, Q3)}}
    ev["mortgage"] = {"dev_2026q2": mortgage_summary(dev["fact_mortgage_exposure"], Q2),
                      "dev_2026q3_before_landing": mortgage_summary(dev["fact_mortgage_exposure"], Q3),
                      "dev_2026q3_after_landing": mortgage_summary(m_after, Q3),
                      "test_2026q2": mortgage_summary(test["fact_mortgage_exposure"], Q2),
                      "test_2026q3": mortgage_summary(test["fact_mortgage_exposure"], Q3),
                      "dev_total_rows_initial": int(len(dev["fact_mortgage_exposure"])),
                      "test_total_rows": int(len(test["fact_mortgage_exposure"]))}
    ev["thresholds_v1"] = {f"{k[0]} | {k[1]}": v for k, v in _thresholds("v1").items()}
    ev["thresholds_v2_changes"] = {f"{k[0]} | {k[1]}": [v, _thresholds("v2")[k]] for k, v in _thresholds("v1").items() if _thresholds("v2")[k] != v}
    ev["watchlist_2026q3_rows_after_landing_v1"] = ev["below_cet1_watch_2026q3"]["after_landing_v1"]["count"]
    return ev


def _pct(x, d=2):
    return f"{x * 100:.{d}f}%"


def render_markdown(ev: dict) -> str:
    rc = ev["row_counts"]
    r3b, r3a = ev["reporting_2026q3"]["before_landing"], ev["reporting_2026q3"]["after_landing"]
    L = []
    a = L.append
    a("# Expected values (quote these in the deck)")
    a("")
    a(f"> **{ev['_banner']}.** All institutions are fictitious. Watch thresholds are *internal watch thresholds (illustrative)*, not OSFI regulatory minimums.")
    a(f"> Generated by `data_gen/expected_values.py` from `data_gen/gen_supervisory_data.py` (seed {ev['seed']}, version {ev['generator_version']}). Machine-readable copy: `docs/expected-values.json`.")
    a("> Ratios are aggregated as SUM(numerator) / SUM(denominator), exactly like the measures in `sm_fda_supervisory`. Mortgage amounts are CAD millions.")
    a("")
    a("**Demo states:** *initial* = after setup (10 late filers missing 2026 Q3) · *after landing* = after `nb_fda_02_land_late_filings` (D2) · *v2* = after the Dataflow Gen2 refresh with `supervisory_watch_thresholds_v2.xlsx` (D5).")
    a("")
    a("## 1. Row counts (lh_supervisory, dbo)")
    a("")
    a("| Table | FDA-Analyst-Dev initial | Landed by nb_fda_02 | Dev after landing | FDA-Analyst-Test (scale 0.25) |")
    a("|---|---:|---:|---:|---:|")
    for t in rc["dev_initial"]:
        a(f"| {t} | {rc['dev_initial'][t]:,} | {rc['late_filings_landed'].get(t, 0):,} | {rc['dev_after_landing'][t]:,} | {rc['test_initial_scale_0_25'][t]:,} |")
    a("")
    a("## 2. Filing status, 2026 Q3")
    a("")
    a("| Measure | Initial (before landing) | After landing (nb_fda_02) |")
    a("|---|---:|---:|")
    a(f"| Institutions Reporting | **{r3b['total']}** | **{r3a['total']}** |")
    a(f"| … deposit-taking (fact_capital) | {r3b['deposit_taking']} | {r3a['deposit_taking']} |")
    a(f"| … insurers (fact_insurance_capital) | {r3b['insurers']} | {r3a['insurers']} |")
    a(f"| Institutions Expected | 40 | 40 |")
    a(f"| Filing Completeness % | **{r3b['filing_completeness_pct']:.2f}%** | **{r3a['filing_completeness_pct']:.2f}%** |")
    a("")
    a(f"2026 Q2 and every earlier quarter: {ev['reporting_2026q2']['total']} reporting, 100.00%.")
    a("")
    a("Late filers (2026 Q3), mixed types: " + ", ".join(f"{x['institution_code']} {x['institution_name']} ({x['institution_type']})" for x in ev["late_filers"]) + ".")
    a("")
    a('D2 DAX query (`SUMMARIZECOLUMNS(dim_quarter[quarter_label], TREATAS({"2026 Q3"}, dim_quarter[quarter_label]), "Reporting", [Institutions Reporting])`): '
      f"**{r3b['total']}** on both models → after nb_fda_02: **{r3a['total']}** on sm_fda_supervisory (Direct Lake), still **{r3b['total']}** on sm_fda_supervisory_import until it is refreshed.")
    a("")
    a("## 3. CET1 Ratio by institution_type")
    a("")
    cb = ev["cet1_ratio_by_type"]
    a("| institution_type | 2026 Q2 | 2026 Q3 initial | 2026 Q3 after landing |")
    a("|---|---:|---:|---:|")
    for t in ("D-SIB", "Other bank", "Trust and loan"):
        a(f"| {t} | {_pct(cb['2026 Q2'][t])} | {_pct(cb['2026 Q3 before landing'][t])} | {_pct(cb['2026 Q3 after landing'][t])} |")
    a("")
    a("Insurers have no CET1 rows (blank), by design.")
    a("")
    a("## 4. Watch counts, 2026 Q3")
    a("")
    bc, bi = ev["below_cet1_watch_2026q3"], ev["insurers_below_capital_watch_2026q3"]
    a("| Measure | Initial, v1 | After landing, v1 | After landing, v2 |")
    a("|---|---:|---:|---:|")
    a(f"| Institutions Below CET1 Watch | **{bc['before_landing_v1']['count']}** | **{bc['after_landing_v1']['count']}** | **{bc['after_landing_v2']['count']}** |")
    a(f"| Insurers Below Capital Watch | **{bi['before_landing_v1']['count']}** | **{bi['after_landing_v1']['count']}** | **{bi['after_landing_v2']['count']}** |")
    a("")
    a(f"- Initial, v1: {'; '.join(bc['before_landing_v1']['institutions'])}.")
    a(f"- After landing, v1: {'; '.join(bc['after_landing_v1']['institutions'])}.")
    a(f"- After landing, v2 (Other bank CET1 watch 11.5% → 12.0%): {'; '.join(bc['after_landing_v2']['institutions'])}.")
    a(f"- If v2 is loaded *before* landing: {bc['before_landing_v2']['count']} ({'; '.join(bc['before_landing_v2']['institutions'])}).")
    a(f"- 2026 Q2 (v1): {ev['below_cet1_watch_2026q2_v1']['count']} ({'; '.join(ev['below_cet1_watch_2026q2_v1']['institutions'])}).")
    a(f"- Insurers v1: {'; '.join(bi['after_landing_v1']['institutions'])}. Late-filing insurers are all above watch, so landing does not change this count.")
    a(f"- Insurers v2 (Life insurer LICAT total watch 120% → 125%): {'; '.join(bi['after_landing_v2']['institutions'])}.")
    a(f"- `dbo.watchlist_2026q3` (sql/21 block E, CTAS, after landing, v1): **{ev['watchlist_2026q3_rows_after_landing_v1']} rows**.")
    a("")
    a("Watch thresholds v1 → v2 (internal, illustrative): " + "; ".join(f"{k}: {v[0]:.3f} → {v[1]:.3f}" for k, v in ev["thresholds_v2_changes"].items()) + ".")
    a("")
    a("## 5. Storylines")
    a("")
    c = ev["cedarline_bank"]
    a(f"**Cedarline Bank ({c['code']}, Other bank)**: CET1 Ratio 2025 Q4 {_pct(c['cet1']['20254'])} · 2026 Q1 **{_pct(c['cet1']['20261'])}** · 2026 Q2 **{_pct(c['cet1']['20262'])}** · 2026 Q3 **{_pct(c['cet1']['20263'])}**; "
      f"CET1 Watch Threshold v1 **{_pct(c['threshold_v1'], 1)}** (v2 {_pct(c['threshold_v2'], 1)}). Default value of the paginated report parameter.")
    a("")
    d = ev["driftwood_bank"]
    a(f"**Driftwood Bank ({d['code']}, Other bank, late filer)**: 2026 Q1 {_pct(d['cet1']['20261'])} · Q2 {_pct(d['cet1']['20262'])} · Q3 (landed by nb_fda_02) **{_pct(d['cet1']['20263'])}**, below the 11.5% watch.")
    a("")
    l0 = ev["lcr_drops_2026q3"][0]
    a(f"**LCR drop (Copilot \"what changed?\")**: **{l0['institution']}** ({l0['type']}) LCR 2026 Q2 **{_pct(l0['q2'], 1)}** → 2026 Q3 **{_pct(l0['q3'], 1)}** ({l0['pp']:+.1f} pp; still above the 110% watch). Next largest drops: "
      + "; ".join(f"{x['institution']} {_pct(x['q2'], 1)} → {_pct(x['q3'], 1)}" for x in ev["lcr_drops_2026q3"][1:]) + ".")
    a("")
    a("**Top 5 CET1 Ratio drops, 2026 Q2 → 2026 Q3** (D7 DAX query view Copilot prompt):")
    a("")
    a("| # | After landing | Q2 → Q3 | Change (pp) | Initial (before landing) | Change (pp) |")
    a("|---|---|---|---:|---|---:|")
    for i, (x, y) in enumerate(zip(ev["top5_cet1_qoq_drops_q2_q3"]["after_landing"], ev["top5_cet1_qoq_drops_q2_q3"]["before_landing"]), start=1):
        a(f"| {i} | {x['institution']} ({x['type']}) | {_pct(x['q2'])} → {_pct(x['q3'])} | {x['pp']:+.2f} | {y['institution']} | {y['pp']:+.2f} |")
    a("")
    o = ev["analyst_outliers_2026q3"]
    a(f"**analyst_outliers** (nb_fda_01, CET1 Ratio fell > 0.5 pp QoQ in 2026 Q3): **{len(o['after_landing'])} rows** after landing ({', '.join(x['institution'] for x in o['after_landing'])}); {len(o['before_landing'])} before landing.")
    a("")
    ar = ev["arrears_90d_rate"]["after_landing"]
    allp = ev["arrears_90d_rate"]["all_provinces_after"]
    a("**Arrears 90d Rate** (all deposit-taking institutions, after landing):")
    a("")
    a("| Province | 2024 Q3 | 2026 Q3 |")
    a("|---|---:|---:|")
    a(f"| ON | {_pct(ar['ON 20243'])} | **{_pct(ar['ON 20263'])}** |")
    a(f"| BC | {_pct(ar['BC 20243'])} | **{_pct(ar['BC 20263'])}** |")
    a(f"| All provinces | {_pct(allp['20243'])} | {_pct(allp['20263'])} |")
    a("")
    bl = ev["arrears_90d_rate"]["before_landing"]
    a(f"Before landing, 2026 Q3: ON {_pct(bl['ON 20263'])}, BC {_pct(bl['BC 20263'])}.")
    a("")
    m = ev["mortgage"]
    a("## 6. Mortgage exposure, Dev vs Test")
    a("")
    a("| | Rows | Mortgage Balance (CAD M) | Arrears 90d Rate | Uninsured High-LTV Share | … Branch | … Broker | … Digital |")
    a("|---|---:|---:|---:|---:|---:|---:|---:|")
    for k, lab in [("dev_2026q2", "Dev 2026 Q2"), ("dev_2026q3_before_landing", "Dev 2026 Q3 initial"), ("dev_2026q3_after_landing", "Dev 2026 Q3 after landing"),
                   ("test_2026q2", "Test 2026 Q2 (scale 0.25)"), ("test_2026q3", "Test 2026 Q3 (scale 0.25)")]:
        x = m[k]
        ch = x["uninsured_high_ltv_share_by_channel"]
        a(f"| {lab} | {x['rows']:,} | {x['balance_cad_m']:,.1f} | {_pct(x['arrears_90d_rate'])} | {_pct(x['uninsured_high_ltv_share'])} | {_pct(ch['Branch'])} | {_pct(ch['Broker'])} | {_pct(ch['Digital'])} |")
    a("")
    a(f"fact_mortgage_exposure total rows: Dev **{m['dev_total_rows_initial']:,}** initial ({rc['dev_after_landing']['fact_mortgage_exposure']:,} after landing) vs Test **{m['test_total_rows']:,}** (≈ {m['test_total_rows'] / m['dev_total_rows_initial']:.0%}).")
    a("In D9, after deploying sm_fda_supervisory to FDA-Analyst-Test, the same report shows the Test numbers (Mortgage Balance 2026 Q2 "
      f"{m['test_2026q2']['balance_cad_m']:,.1f} vs {m['dev_2026q2']['balance_cad_m']:,.1f} in Dev) and Institutions Reporting 2026 Q3 = {r3b['total']} (late filers are never landed in Test).")
    a("Capital, liquidity and insurance tables are identical in Dev and Test (the scale factor only thins mortgage pools).")
    a("")
    a("LCR by institution_type, 2026 Q3 after landing: " + ", ".join(f"{k} {_pct(v, 1)}" for k, v in ev["lcr_by_type_2026q3_after"].items()) + ".")
    a("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(os.path.dirname(here), "docs", "expected-values.json")
    ev = compute()
    with open(out, "w", encoding="utf-8") as f:
        json.dump(ev, f, indent=2, ensure_ascii=False, default=str)
    with open(os.path.join(os.path.dirname(here), "docs", "expected-values.md"), "w", encoding="utf-8") as f:
        f.write(render_markdown(ev))
    print("wrote docs/expected-values.json and docs/expected-values.md")
