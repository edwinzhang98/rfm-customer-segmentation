"""Keep the numbers in the Markdown docs identical to the data.

Any Markdown file in docs/ (and README.md) can contain a block

    <!-- BEGIN:table_name -->
    (anything - replaced on every run)
    <!-- END:table_name -->

`python run.py --steps docs` regenerates the block from the marts. Hand-written prose stays untouched;
tables never have to be retyped, so they cannot drift from the analysis.
"""

from __future__ import annotations

import re
from typing import Callable

import numpy as np
import pandas as pd

from . import campaign as CP
from . import data as D
from .config import ROOT, get_paths
from .segments import SEGMENT_INFO, SEGMENT_ORDER


def _n(v, nd: int = 0) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "-"
    return f"{v:,.{nd}f}"


def _p(v, nd: int = 1) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{100 * v:.{nd}f}%"


def _md(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False, disable_numparse=True)


# ----------------------------------------------------------------------------- tables
def t_segment_summary() -> str:
    prof = D.mart("segment_profile")
    rows = []
    for r in prof.itertuples():
        rows.append({"Segment": r.segment, "Rule (scores)": SEGMENT_INFO[r.segment]["rule"],
                     "In plain words": SEGMENT_INFO[r.segment]["plain"], "Customers": _n(r.customers),
                     "% customers": _p(r.pct_customers), "% 12m revenue": _p(r.pct_revenue_12m),
                     "AOV (CU)": _n(r.aov_12m_cu if pd.notna(r.aov_12m_cu) else r.aov_2y_cu, 1),
                     "Orders / 12m": _n(r.avg_orders_12m, 1), "Email reach": _p(r.pct_newsletter, 0)})
    tot = prof[["customers", "pct_customers", "pct_revenue_12m"]].sum()
    rows.append({"Segment": "**Total**", "Rule (scores)": "", "In plain words": "all customers with an order 2018-09-20 to 2020-09-22",
                 "Customers": f"**{_n(tot.customers)}**", "% customers": f"**{_p(tot.pct_customers)}**",
                 "% 12m revenue": f"**{_p(tot.pct_revenue_12m)}**", "AOV (CU)": "", "Orders / 12m": "", "Email reach": ""})
    return _md(pd.DataFrame(rows))


def t_segment_counts() -> str:
    """Expected counts per segment: the reconciliation check for anyone rebuilding the audiences."""
    prof = D.mart("segment_profile")
    m = D.metrics()["data"]
    df = pd.DataFrame({"Segment": prof.segment, "Customers": prof.customers.map(_n),
                       "12-month revenue (CU)": prof.revenue_12m_cu.map(_n), "Two-year revenue (CU)": prof.revenue_2y_cu.map(_n)})
    total = pd.DataFrame([{"Segment": "**Total with an order**", "Customers": f"**{_n(prof.customers.sum())}**",
                           "12-month revenue (CU)": f"**{_n(prof.revenue_12m_cu.sum())}**",
                           "Two-year revenue (CU)": f"**{_n(prof.revenue_2y_cu.sum())}**"},
                          {"Segment": "Registered, no order in the window (not scored)", "Customers": _n(m["customers_without_orders"]),
                           "12-month revenue (CU)": "0", "Two-year revenue (CU)": "0"},
                          {"Segment": "**All customers in customers.csv**", "Customers": f"**{_n(m['customers_in_customer_file'])}**",
                           "12-month revenue (CU)": "", "Two-year revenue (CU)": ""}])
    return _md(pd.concat([df, total], ignore_index=True))


def t_value_grid() -> str:
    g = D.mart("value_grid")
    tiers = ["VIP", "High", "Mid", "Low", "None"]
    piv = g.pivot_table(index="segment", columns="value_tier", values="customers", aggfunc="sum").reindex(columns=tiers).fillna(0)
    piv = piv.reindex([s for s in SEGMENT_ORDER if s in piv.index])
    rev = g.pivot_table(index="value_tier", values="revenue_12m_cu", aggfunc="sum").reindex(tiers).fillna(0)["revenue_12m_cu"]
    out = piv.map(lambda v: _n(v)).reset_index().rename(columns={"segment": "Segment", "VIP": "VIP (1,000+ CU)",
                                                                  "High": "High (400-999)", "Mid": "Mid (200-399)", "Low": "Low (< 200)",
                                                                  "None": "None (no 12m spend)"})
    total = {"Segment": "**% of 12-month revenue**"}
    for t, col in zip(tiers, out.columns[1:]):
        total[col] = f"**{_p(rev[t] / rev.sum())}**"
    return _md(pd.concat([out, pd.DataFrame([total])], ignore_index=True))


def t_audience_spec() -> str:
    inp = D.mart("campaign_inputs")
    aud = CP.audience_frame().set_index("key")
    plan = CP.plan_frame()
    reach = CP.audience_reach(plan)
    rows = []
    for r in inp.itertuples():
        paid = bool(reach.get(r.audience, False))
        rows.append({"Audience": r.audience_label, "Rule": aud.loc[r.audience, "rule"], "Customers": _n(r.customers),
                     "Reachable": "everyone (email + paid social)" if paid else f"email only ({_p(r.newsletter_share, 0)})",
                     "AOV (CU)": _n(r.aov_cu, 1),
                     "Buy again within 90 days, BAU (2019 / 2020 backtest)": f"{_p(r.baseline_rate_seasonal)} / {_p(r.baseline_rate_recent)}"})
    return _md(pd.DataFrame(rows))


def t_campaign_table() -> str:
    econ = D.mart("campaign_economics")
    rows = []
    for r in econ.itertuples():
        rows.append({"Audience": r.audience_label, "Arm": r.arm, "Role": r.role, "Action": r.action, "Timing": r.timing,
                     "Channel": r.channels, "Discount": "none" if r.discount_rate == 0 else f"{100 * r.discount_rate:.0f}% off one order",
                     "Assumed lift": f"+{r.uplift_pp:.1f} pp", "Primary KPI": r.kpi, "Decision rule": r.decision_rule})
    for seg, why in CP.NO_CAMPAIGN.items():
        rows.append({"Audience": seg, "Arm": "No autumn campaign", "Role": "-", "Action": why, "Timing": "-", "Channel": "-",
                     "Discount": "-", "Assumed lift": "-", "Primary KPI": "-", "Decision rule": "-"})
    return _md(pd.DataFrame(rows))


def t_campaign_short() -> str:
    """Compact version for the README and readout."""
    econ = D.mart("campaign_economics")
    focus = CP.audience_category_focus()
    rows = []
    for r in econ[econ.role != "Not run"].itertuples():
        channel = ("Email + paid social" if r.use_paid_social else
                   "Email only" if "subscribers only" in r.channels.lower() else "Email + member app")
        rows.append({"Audience": r.audience_label, "Action": r.arm + (" (test cell)" if r.role == "Test cell" else ""),
                     "When": r.timing.split(";")[0], "Channel": channel,
                     "Category focus": focus.get(r.audience, "-"),
                     "Discount": "none" if r.discount_rate == 0 else f"{100 * r.discount_rate:.0f}%",
                     "Expected net (CU)": _n(r.net_profit_cu)})
    for seg, why in CP.NO_CAMPAIGN.items():
        rows.append({"Audience": seg, "Action": "no autumn spend", "When": "-", "Channel": "-", "Category focus": "-", "Discount": "-",
                     "Expected net (CU)": "-"})
    return _md(pd.DataFrame(rows))


def t_campaign_economics() -> str:
    econ = D.mart("campaign_economics")
    df = pd.DataFrame({
        "Audience": econ.audience_label, "Arm": econ.arm, "Role": econ.role, "Contacted": econ.contacted.map(_n),
        "Buys anyway": econ.baseline_rate.map(_p), "Assumed lift (pp)": econ.uplift_pp.map(lambda v: _n(v, 1)),
        "Break-even lift (pp)": econ.breakeven_uplift_pp.map(lambda v: _n(v, 2)),
        "Incremental revenue (CU)": econ.incremental_revenue_cu.map(_n), "Discount cost (CU)": econ.discount_cost_cu.map(_n),
        "Contact cost (CU)": econ.contact_cost_cu.map(_n), "Net profit (CU)": econ.net_profit_cu.map(_n)})
    return _md(df)


def t_scenarios() -> str:
    s = D.mart("campaign_scenarios")
    df = pd.DataFrame({"Scenario": s.scenario, "Arms": s.role, "Contacted": s.contacted.map(_n), "Cost (CU)": s.total_cost_cu.map(_n),
                       "Incremental revenue (CU)": s.incremental_revenue_cu.map(_n), "Net profit (CU)": s.net_profit_cu.map(_n)})
    return _md(df)


def t_budget() -> str:
    b = D.mart("campaign_budget")
    return _md(pd.DataFrame({"Line": b.line, "CU": b.cost_cu.map(_n), "How it is calculated": b.note}))


def t_measurement() -> str:
    econ = D.mart("campaign_economics")
    e = econ[econ.role != "Not run"]
    df = pd.DataFrame({
        "Audience": e.audience_label, "Arm": e.arm, "Role": e.role, "Reachable population": e.experiment_population.map(_n),
        "Holdout": e.holdout.map(_n), "Arm size": e.contacted.map(_n), "Assumed lift (pp)": e.uplift_pp.map(lambda v: _n(v, 1)),
        "Break-even (pp)": e.breakeven_uplift_pp.map(lambda v: _n(v, 2)), "Detectable lift (pp)": e.mde_rate_pp.map(lambda v: _n(v, 2)),
        "Detectable revenue lift (CU/customer)": e.mde_revenue_cu.map(lambda v: _n(v, 1)),
        "Readable alone": [("yes" if ok else ("no - decided vs its content cell" if role == "Test cell" else "no - pooled read"))
                           for ok, role in zip(e.readable_alone, e.role)],
        "Sized for its decision": np.where(e.role == "Test cell", e.powered_for_decision.map({True: "yes", False: "no"}), "-")})
    return _md(df)


def t_revenue_at_risk() -> str:
    r = D.mart("revenue_at_risk")
    df = pd.DataFrame({
        "Segment": r.segment, "Customers": r.customers.map(_n), "Usual 90-day pace (CU)": r.run_rate_90d_cu.map(_n),
        "Expected, do nothing (CU)": r.expected_90d_cu_base.map(_n), "Gap vs pace (CU)": r.gap_90d_cu_base.map(_n),
        "Gap range (CU)": [f"{_n(lo)} to {_n(hi)}" if pd.notna(lo) else "-" for lo, hi in zip(r.gap_90d_cu_low, r.gap_90d_cu_high)],
        "Buy again in 90 days": r.repurchase_rate_base.map(_p), "Expected non-buyers": r.expected_non_buyers_base.map(_n),
        "Plan's incremental revenue (CU)": r.addressable_90d_cu.map(_n)})
    return _md(df)


def t_dq_checks() -> str:
    dq = D.mart("dq_checks")
    return _md(pd.DataFrame({"#": dq.check_id.astype(str), "Area": dq.area, "Check": dq.check_name, "Status": dq.status,
                             "Observed": dq.observed, "Expected": dq.expectation, "Handling": dq.handling}))


def t_reconciliation() -> str:
    rc = D.mart("reconciliation_checks")
    return _md(pd.DataFrame({"Check": rc.check_name, "Left": rc.left_value.map(lambda v: _n(v, 2)),
                             "Right": rc.right_value.map(lambda v: _n(v, 2)), "Difference": rc.difference.map(lambda v: _n(v, 2)),
                             "Result": rc.passed.map({True: "PASS", False: "FAIL"})}))


def t_threshold_sensitivity() -> str:
    s = D.mart("threshold_sensitivity")
    piv = s[s.variant != "Default"].pivot(index="segment", columns="variant", values="pct_change")
    piv = piv.reindex([x for x in SEGMENT_ORDER if x in piv.index and x not in ("Lost", "Review List", "New Customers")])
    return _md(piv.map(lambda v: f"{100 * v:+.0f}%").reset_index().rename(columns={"segment": "Segment"}))


def t_run_timings() -> str:
    t = D.metrics().get("timings_s", {})
    keys = [k for k in t if k.startswith("step:")]
    df = pd.DataFrame({"Step": [k.split(":", 1)[1] for k in keys], "Seconds": [f"{t[k]:.1f}" for k in keys]})
    return _md(df)


TABLES: dict[str, Callable[[], str]] = {
    "segment_summary": t_segment_summary,
    "segment_counts": t_segment_counts,
    "value_grid": t_value_grid,
    "audience_spec": t_audience_spec,
    "campaign_table": t_campaign_table,
    "campaign_short": t_campaign_short,
    "campaign_economics": t_campaign_economics,
    "scenarios": t_scenarios,
    "budget": t_budget,
    "measurement": t_measurement,
    "revenue_at_risk": t_revenue_at_risk,
    "dq_checks": t_dq_checks,
    "reconciliation": t_reconciliation,
    "threshold_sensitivity": t_threshold_sensitivity,
    "run_timings": t_run_timings,
}

_BLOCK = re.compile(r"(<!-- BEGIN:(?P<name>[a-z_]+) -->)(.*?)(<!-- END:(?P=name) -->)", re.S)


def render(text: str, cache: dict[str, str]) -> tuple[str, list[str]]:
    used = []

    def repl(m: re.Match) -> str:
        name = m.group("name")
        if name not in TABLES:
            raise KeyError(f"Unknown generated table '{name}' (known: {sorted(TABLES)})")
        if name not in cache:
            cache[name] = TABLES[name]()
        used.append(name)
        return f"{m.group(1)}\n{cache[name]}\n\n<sub>Generated from the pipeline outputs by `python run.py --steps docs`; do not edit by hand.</sub>\n{m.group(4)}"

    return _BLOCK.sub(repl, text), used


def update_all(log: Callable[[str], None] = print) -> None:
    files = sorted(get_paths().docs.glob("*.md")) + [ROOT / "README.md"]
    cache: dict[str, str] = {}
    for f in files:
        text = f.read_text()
        new, used = render(text, cache)
        if used:
            if new != text:
                f.write_text(new)
            log(f"  {f.relative_to(ROOT)}: {', '.join(used)}")
