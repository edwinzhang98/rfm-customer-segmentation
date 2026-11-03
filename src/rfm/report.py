"""Standalone HTML deliverables (`python run.py --steps report`).

reports/report.html       full analysis report: question, data, method, results, recommendations, limitations.
                          Charts are the same Plotly figures as the dashboard, with plotly.js embedded once, so the
                          file opens offline with a double-click.
reports/action_plan.html  one printable page for the CRM Manager: the answer, the plan table, budget, measurement.
"""

from __future__ import annotations

import base64
import datetime as dt
from typing import Callable

import pandas as pd
import plotly.io as pio
from jinja2 import Template
from plotly.offline import get_plotlyjs

from . import campaign as CP
from . import charts as C
from . import data as D
from .config import get_paths
from .segments import SEGMENT_INFO, SEGMENT_ORDER

fmt_cu, fmt_n, pct = D.fmt_cu, D.fmt_n, D.pct

CSS = """
:root { --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --grid:#e1e0d9; --surface:#fcfcfb; --accent:#2a78d6; --panel:#f3f2ee; }
* { box-sizing: border-box; }
body { margin:0; background:var(--surface); color:var(--ink); font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
main { max-width: 1120px; margin: 0 auto; padding: 32px 20px 80px; }
h1 { font-size: 30px; margin: 0 0 6px; letter-spacing: -0.01em; }
h2 { font-size: 22px; margin: 44px 0 10px; padding-top: 10px; border-top: 1px solid var(--grid); }
h3 { font-size: 17px; margin: 26px 0 8px; }
p, li { color: var(--ink); max-width: 880px; }
.sub { color: var(--ink2); margin: 0 0 18px; }
.tldr { background: var(--panel); border-radius: 8px; padding: 16px 22px; margin: 18px 0 8px; }
.tldr li { margin: 6px 0; }
.kpis { display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0; }
.kpi { border: 1px solid var(--grid); border-radius: 8px; padding: 12px 14px; background: #fff; }
.kpi .l { color: var(--ink2); font-size: 13px; } .kpi .v { font-size: 24px; font-weight: 600; margin-top: 2px; } .kpi .d { color: var(--muted); font-size: 12.5px; }
.note { color: var(--muted); font-size: 13px; max-width: 880px; }
.callout { border-left: 3px solid var(--accent); padding: 8px 0 8px 14px; margin: 14px 0; color: var(--ink); max-width: 900px; }
.fig { margin: 10px 0 4px; }
.takeaway { color: var(--ink2); font-size: 14px; margin: 0 0 18px; }
table.t { border-collapse: collapse; width: 100%; font-size: 13px; margin: 8px 0 14px; }
table.t th { text-align: left; color: var(--ink2); font-weight: 600; border-bottom: 1px solid var(--ink2); padding: 6px 8px; vertical-align: bottom; }
table.t td { border-bottom: 1px solid var(--grid); padding: 6px 8px; vertical-align: top; font-variant-numeric: tabular-nums; }
.tablewrap { overflow-x: auto; }
nav.toc { columns: 2; font-size: 14px; margin: 10px 0 0; } nav.toc a { color: var(--accent); text-decoration: none; }
code { background: var(--panel); padding: 1px 5px; border-radius: 4px; font-size: 13px; }
@media (max-width: 700px) { nav.toc { columns: 1; } h1 { font-size: 24px; } }
@media print { nav.toc { display:none; } h2 { page-break-before: auto; } }
"""

REPORT = Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RFM Segmentation Report</title>
<style>{{ css }}</style>
<script>{{ plotlyjs }}</script>
</head><body><main>
<h1>RFM segmentation and the autumn CRM campaign</h1>
<p class="sub">CRM / Marketing Analytics &middot; data 2018-09-20 to 2020-09-22, snapshot {{ snapshot }} &middot; report built {{ built }}</p>
<div class="tldr"><b>TL;DR</b><ul>{% for b in tldr %}<li>{{ b }}</li>{% endfor %}</ul></div>
<div class="kpis">{% for k in kpis %}<div class="kpi"><div class="l">{{ k[0] }}</div><div class="v">{{ k[1] }}</div><div class="d">{{ k[2] }}</div></div>{% endfor %}</div>
<nav class="toc">{% for s in sections %}<div><a href="#{{ s.id }}">{{ loop.index }}. {{ s.title }}</a></div>{% endfor %}</nav>
{% for s in sections %}
<h2 id="{{ s.id }}">{{ loop.index }}. {{ s.title }}</h2>
{% for block in s.blocks %}{{ block }}{% endfor %}
{% endfor %}
<p class="note" style="margin-top:40px">Reproduce: <code>make all</code> (or <code>python run.py</code>) rebuilds every table, chart and this file from the raw CSVs.
Money is in CU (price x 590, currency undisclosed), gross demand before returns.</p>
</main></body></html>""")

ACTION = Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Autumn Campaign Action Plan</title>
<style>{{ css }} main{max-width:1000px} table.t{font-size:12.5px} h2{margin-top:26px}</style></head><body><main>
<h1>Autumn campaign: action plan</h1>
<p class="sub">For the CRM Manager &middot; audiences from the {{ snapshot }} snapshot, re-scored on launch day {{ launch }} &middot; final read {{ read }}</p>
<div class="tldr"><b>The answer</b><ul>{% for b in answer %}<li>{{ b }}</li>{% endfor %}</ul></div>
<h2>Who gets what</h2>
<div class="tablewrap">{{ plan_table }}</div>
<p class="note">Focus: the categories an audience over-indexes on. The number in brackets compares the category's share of the audience's
spend with its share for all customers (100 = average, 126 = 26% higher). App messages go to the same email subscribers.</p>
<h2>Budget</h2>
<div class="tablewrap">{{ budget_table }}</div>
<p class="note">If the budget is cut, drop in this order: (1) the At Risk 10% test cell, (2) paid social for the New Customers journey,
(3) the New Customers coupon cell. Content arms and email stay.</p>
<h2>How we will know it worked</h2>
<ul>{% for b in measure %}<li>{{ b }}</li>{% endfor %}</ul>
<h2>Decisions needed</h2>
<ul>{% for b in asks %}<li>{{ b }}</li>{% endfor %}</ul>
<img alt="Share of customers vs share of revenue by segment" src="data:image/png;base64,{{ chart_png }}" style="width:100%;margin-top:18px">
</main></body></html>""")


# ----------------------------------------------------------------------------- helpers
_FIG_COUNTER = [0]


def _fig(fig) -> str:
    """Plotly div; plotly.js is embedded once in <head>, so every figure uses include_plotlyjs=False.
    Div ids are numbered (not random) so the report is byte-identical between runs."""
    _FIG_COUNTER[0] += 1
    return '<div class="fig">' + pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=f"fig-{_FIG_COUNTER[0]:02d}",
                                              config={"displaylogo": False, "responsive": True}) + "</div>"


def _p(text: str) -> str:
    return f"<p>{text}</p>"


def _take(text: str) -> str:
    return f'<p class="takeaway">{text}</p>'


def _note(text: str) -> str:
    return f'<p class="note">{text}</p>'


def _call(text: str) -> str:
    return f'<div class="callout">{text}</div>'


def _ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def _fmt_col(s: pd.Series) -> pd.Series:
    """Readable numbers: thousands separators, no spurious decimals, yes/no for flags."""
    if pd.api.types.is_bool_dtype(s):
        return s.map({True: "yes", False: "no"})
    if not pd.api.types.is_numeric_dtype(s):
        return s
    vals = s.dropna()
    whole = len(vals) > 0 and (vals.round(0) == vals).all()
    big = len(vals) > 0 and vals.abs().median() >= 100
    fmt = "{:,.0f}" if (whole or big) else "{:,.2f}"
    return s.map(lambda v: "-" if pd.isna(v) else fmt.format(v))


def _table(df: pd.DataFrame) -> str:
    out = df.copy()
    for c in out.columns:
        out[c] = _fmt_col(out[c])
    return '<div class="tablewrap">' + out.to_html(index=False, classes="t", border=0, escape=True, na_rep="-") + "</div>"


# ----------------------------------------------------------------------------- report
def build_report() -> str:
    _FIG_COUNTER[0] = 0
    m = D.metrics()
    d, h, camp, km = m["data"], m["headline"], m["campaign"], m["kmeans"]
    seg = m["segments"]
    sc = camp["scenarios"]
    F = _fig

    prof = D.mart("segment_profile")
    so = D.mart("segment_outcomes_90d")
    rar = D.mart("revenue_at_risk")
    econ = D.mart("campaign_economics")
    mix = D.mart("segment_mix")

    tldr = [
        f"<b>Keep:</b> Champions are {pct(h['champions_pct_customers'], 0)} of customers and {pct(h['champions_pct_revenue_12m'], 0)} of 12-month revenue; "
        f"{fmt_n(h['vip_customers'])} VIPs (1,000+ CU a year) bring in {pct(h['vip_pct_revenue_12m'], 0)}. {pct(seg['Champions']['repurchase_rate_90d_base'], 0)} "
        "of Champions buy again within 90 days anyway, so they get early access and service, not discounts.",
        f"<b>Win back:</b> {fmt_n(h['at_risk_customers'])} At Risk customers ({pct(h['at_risk_pct_customers'])}) are expected to spend about "
        f"{fmt_cu(h['at_risk_expected_90d_cu'])} in the next 90 days with business-as-usual contact only, {fmt_cu(h['at_risk_gap_90d_cu'])} below their "
        f"usual pace; {fmt_n(h['slipping_customers'])} Slipping Regulars are the early warning (gap {fmt_cu(h['slipping_gap_90d_cu'])}). The plan expects "
        f"about {fmt_cu(h['at_risk_addressable_90d_cu'])} of incremental revenue from At Risk, {fmt_cu(h['at_risk_addressable_content_90d_cu'])} of it from "
        "content emails: most of the gap is natural slowdown.",
        f"<b>Online-only:</b> {fmt_n(h['online_only_active_customers'])} active customers ({pct(h['pct_online_only_active'], 0)}) had no identified store "
        "purchase in 12 months. Their bigger baskets are an online-channel effect and they come back slightly less often; nothing supports paying "
        "to push them into stores. Channel decides the message.",
        f"<b>Plan:</b> content-led rollout ({fmt_cu(sc['Base | Rollout']['total_cost_cu'])}), discounts only in two test cells, budget ask "
        f"{fmt_cu(camp['budget_total_cu'])}; expected rollout net {D.fmt_k(sc['Base | Rollout']['net_profit_cu'])} CU on planning assumptions "
        f"(pessimistic {D.fmt_k(sc['Pessimistic | Rollout']['net_profit_cu'])}, optimistic {D.fmt_k(sc['Optimistic | Rollout']['net_profit_cu'])}).",
        f"<b>Measurement:</b> the same 10% holdout in every audience; the campaign-wide lift is detectable from {camp['pooled_read']['mde_rate_pp']:.2f} pp; "
        f"the two discount cells are sized to give a clear yes/no by {camp['read_date']}.",
    ]
    kpis = [
        ("Customers with a purchase", fmt_n(d["customers_with_orders"], 2), f"{fmt_n(d['transaction_rows'])} item rows"),
        ("Active in 12 months", fmt_n(d["active_12m_customers"]), f"{pct(d['pct_active_12m'])} of customers"),
        ("12-month revenue", fmt_cu(d["revenue_12m_cu"]), "gross demand"),
        ("At Risk: expected 90 days", fmt_cu(h["at_risk_expected_90d_cu"]), f"vs usual pace {fmt_cu(h['at_risk_run_rate_90d_cu'])}"),
        ("Budget ask", fmt_cu(camp["budget_total_cu"]), "autumn wave incl. test cells"),
    ]

    sections = []
    # 1 question ---------------------------------------------------------------
    sections.append({"id": "question", "title": "The question", "blocks": [
        _p("The CRM Manager asked: <i>\"The autumn campaign budget is limited. Who are the high-value customers we need to keep, who is about to "
           "churn and needs winning back, and who only buys online and never comes into a store? Give me segments, a recommendation per segment, "
           "and how we will measure whether this campaign worked.\"</i>"),
        _p("Turned into analysis questions: (1) which customers bought recently, often and for a lot, and what share of revenue do they drive; "
           "(2) which valuable customers have gone quiet, how likely they are to come back on their own and what they are expected to spend if we do nothing; "
           "(3) who only buys online, and does that matter; (4) what each segment should get, at what cost; (5) how to measure the campaign. "
           "Decision maker: the CRM Manager; consulted: e-commerce, retail operations, finance."),
    ]})
    # 2 data ------------------------------------------------------------------
    dq = D.mart("dq_checks")
    sections.append({"id": "data", "title": "Data and sanity checks", "blocks": [
        _p(f"H&M transactions (public H&M Personalized Fashion Recommendations dataset): {fmt_n(d['transaction_rows'])} item rows from 2018-09-20 to "
           f"2020-09-22, {d['customers_with_orders']:,} customers with an order, plus the customer and article files. Staged to Parquet with DuckDB and "
           f"processed in full (no sampling). {d['dq_pass']} checks pass, {d['dq_flag']} are flagged as known issues with a documented handling, none fail; "
           f"{d['reconciliation_checks_passed']} of {d['reconciliation_checks_total']} reconciliation checks confirm units, revenue and customers add up "
           "exactly from raw rows to segments."),
        F(C.weekly_channel(D.mart("weekly_channel_trend"))),
        _take("The data only says channel 1 or 2. Channel 1 disappears for the weeks stores were closed in spring 2020 (2020-03-20 to 2020-05-05) "
              "while channel 2 jumps, so 1 = store and 2 = online."),
        F(C.price_points(D.mart("price_points"))),
        _take("Prices are scaled in the public file; multiplying by 590 recovers shelf prices for every row, so money is reported in CU "
              "(currency units, currency undisclosed). Revenue is gross demand: the file has no returns."),
        _ul(["Identical rows (2.97M, 9.4%) are extra units of the same item, kept as a <code>units</code> column, not deleted.",
             "An order is one customer, one day, one channel (there is no order id).",
             f"{d['review_list_customers']} accounts with bulk or near-daily buying go on a Review List: kept in every total, no offers or paid "
             "media until reviewed (0.5% of revenue).",
             "Store purchases are only visible when the shopper identifies as a member; 'online only' means 'no identified store purchase'."]),
        _table(dq[["check_id", "area", "check_name", "status", "observed"]].rename(columns={"check_id": "#", "check_name": "check"})),
    ]})
    # 3 method ----------------------------------------------------------------
    rules = pd.DataFrame([{"Segment": s, "Rule": SEGMENT_INFO[s]["rule"], "In plain words": SEGMENT_INFO[s]["plain"]} for s in SEGMENT_ORDER])
    sections.append({"id": "method", "title": "Method: RFM scores and segment rules", "blocks": [
        _p("Snapshot 2020-09-22 (the last day in the data). <b>Recency</b> = days since the last order; <b>Frequency</b> = orders in the 365 days up to the "
           "snapshot; <b>Monetary</b> = CU spent in the same 365 days. Scores use fixed thresholds: R 0-30 / 31-60 / 61-120 / 121-180 / 181-364 days "
           "(365+ = Lost); F 1 / 2 / 3-4 / 5-9 / 10+ orders; M under 50 / 50-99 / 100-199 / 200-399 / 400+ CU."),
        F(C.return_curve(D.mart("recency_return_curve"))),
        _take("The chance of buying again falls smoothly with time since the last order: recency is the right main axis, and the cut-offs are a "
              "business choice placed on a smooth curve (30 / 60 days = a purchase cycle, 120 = a season, 180 = two seasons, 365 = a year)."),
        _p("Why fixed thresholds rather than quintiles: the R and M cut-offs sit near the active-customer quintiles (R 23 / 60 / 112 / 215 days, "
           "M 40 / 85 / 166 / 352 CU) and are set to business periods and round amounts the CRM team plans with; Frequency is set by hand because 34% of active customers have exactly one order, so quintile edges tie (the bands either merge or "
           "split identical customers arbitrarily); fixed numbers keep an audience's meaning stable month to month. Segments are assigned in order, "
           "first match wins:"),
        _table(rules),
        F(C.kmeans_crosstab(D.mart("kmeans_crosstab"), D.mart("kmeans_profile"))),
        _take(f"A K-Means check on the same three measures finds no natural clusters (separation is best at k = 2 and falls with k), recovers the Champions "
              f"({pct(km['top_cluster_champion_share'], 0)} of the top cluster) and reassigns {pct(km['share_reassigned_by_refit'])} of customers when refit "
              "a quarter later. Its middle cluster mixes customers the campaign must treat differently, which is why the rules (plus a value tier) are used."),
    ]})
    # 4 segments ----------------------------------------------------------------
    pv = prof.assign(**{"% customers": (100 * prof.pct_customers).round(1), "% 12m revenue": (100 * prof.pct_revenue_12m).round(1),
                        "AOV (CU)": prof.aov_12m_cu.fillna(prof.aov_2y_cu).round(1), "orders / 12m": prof.avg_orders_12m.round(1),
                        "% email reach": (100 * prof.pct_newsletter).round(0), "% online only (12m)": (100 * prof.pct_online_only_12m).round(0)})
    sections.append({"id": "segments", "title": "Segments: size, value, behaviour", "blocks": [
        F(C.segment_share(prof)),
        _take(f"Champions and Loyal and Slipping Regulars together are {pct(h['high_value_pct_customers'], 0)} of customers and "
              f"{pct(h['high_value_pct_revenue_12m'], 0)} of 12-month revenue."),
        _table(pv[["segment", "customers", "% customers", "% 12m revenue", "AOV (CU)", "orders / 12m", "% online only (12m)", "% email reach"]]),
        F(C.value_grid(D.mart("value_grid"))),
        _take("Value is a second axis: lifecycle says what to do, value tier says how much effort a customer is worth."),
        F(C.segment_outcomes(so)),
        _take("Applied at two past dates, the same rules rank what customers did next in the same order at both dates: the segments predict behaviour."),
        F(C.segment_flow(D.mart("segment_flow"))),
        _take(f"{pct(h['customers_changed_segment_one_quarter'], 0)} of customers changed segment in one quarter; the segmentation is re-run monthly "
              "and audiences are re-scored on launch day."),
    ]})
    # 5 drill-down ----------------------------------------------------------------
    sections.append({"id": "drilldown", "title": "What segments buy, and the online-only question", "blocks": [
        F(C.category_affinity(mix, "At Risk")),
        _take("At Risk as a whole over-indexes on knitwear and outerwear, but the skew belongs to the customers quiet for 181-364 days, who last "
              "bought in autumn / winter 2019-20 (outdoor 165, knitwear 155 for those spending 200+ CU); the 121-180-day group last bought during "
              "the spring 2020 closure and under-indexes on both. The autumn win-back therefore leads with knitwear and outerwear only for the "
              "long-lapsed group and with each customer's own top categories for the rest. Affinity reflects when a group last bought as much as "
              "what it likes."),
        F(C.channel_mix(mix)),
        F(C.channel_value(D.mart("channel_value"))),
        F(C.channel_forward(D.mart("channel_forward"))),
        _take(f"An online order is about twice a store order even for the same omnichannel customers ({h['aov_online_order_omni']:.0f} vs "
              f"{h['aov_store_order_omni']:.0f} CU), so online-only customers show more gross demand at equal order counts, but they come back slightly less "
              f"often ({pct(h['repurchase_5_9_online_only'], 0)} vs {pct(h['repurchase_5_9_omni'], 0)} at 5-9 orders). Nothing shows a store push would raise "
              "their value: channel sets the message (online creative for online-only, store-led creative for store-only)."),
    ]})
    # 6 if we do nothing --------------------------------------------------------
    rr = rar[["segment", "customers", "run_rate_90d_cu", "expected_90d_cu_base", "gap_90d_cu_base", "gap_90d_cu_low", "gap_90d_cu_high",
              "addressable_90d_cu"]].copy()
    rr.columns = ["Segment", "Customers", "Usual 90-day pace (CU)", "Expected, do nothing (CU)", "Gap vs pace (CU)", "Gap low", "Gap high",
                  "Plan's incremental revenue (CU)"]
    for c in rr.columns[1:]:
        rr[c] = rr[c].round(0)
    sections.append({"id": "do-nothing", "title": "If we do nothing", "blocks": [
        F(C.run_rate_vs_expected(rar)),
        _p("Method: customers who looked like today's segments on 2019-09-22 (same season, one year earlier) are followed for 90 days; the share of their "
           "usual pace they actually spent is applied to today's customers, separately for each type of customer (recency x frequency x spend x channel) "
           f"so that today's mix is respected. {pct(h['at_risk_lockdown_share'], 0)} of today's At Risk customers last bought during the March-May 2020 "
           "lockdown, which no past period mirrors; scenarios use the 2020-06-24 quarter and, per customer type, the worse of the two."),
        _table(rr),
        _call(f"The gap vs usual pace is not money a campaign can recover: groups chosen for a strong year fall back (Champions spending 400+ CU realised "
              f"{pct(h['champions_realisation_m5'], 0)} of their pace, those at 200-399 CU {pct(h['champions_realisation_m4'], 0)}), and groups chosen for "
              f"going quiet keep slowing. The plan expects about {fmt_cu(h['at_risk_addressable_90d_cu'])} of incremental revenue from At Risk "
              f"({fmt_cu(h['at_risk_addressable_content_90d_cu'])} from the content emails; the rest from the 10% offer test cell, which is expected "
              "to lose money on its own), a few percent of its gap; that measured lift, not the gap, is what we report."),
    ]})
    # 7 campaign ----------------------------------------------------------------
    plan_tbl = econ[["audience_label", "arm", "role", "action", "timing", "discount_rate", "uplift_pp", "breakeven_uplift_pp", "net_profit_cu"]].copy()
    plan_tbl["discount_rate"] = plan_tbl.discount_rate.map(lambda v: "none" if v == 0 else f"{100 * v:.0f}%")
    plan_tbl = plan_tbl.round({"breakeven_uplift_pp": 2, "net_profit_cu": 0})
    plan_tbl.columns = ["Audience", "Arm", "Role", "Action", "Timing", "Discount", "Assumed lift (pp)", "Break-even (pp)", "Net (CU, base)"]
    budget = D.mart("campaign_budget")
    sections.append({"id": "plan", "title": "The autumn plan and its economics", "blocks": [
        _table(plan_tbl),
        _note("The Review List gets no offers or paid media until reviewed. 'Not run' rows were considered and rejected. "
              "Net is the base case under planning assumptions, not a measurement."),
        F(C.net_profit_by_arm(econ)),
        F(C.breakeven_vs_assumed(econ)),
        _take("A coupon is paid on every redeemed order, including orders from customers who would have bought anyway, and an extra buyer is worth "
              "about one order. Where a quarter or more of an audience buys anyway, a coupon needs a lift of 5+ points to break even. Content costs "
              "almost nothing, so small lifts pay. The two discount cells measure this instead of assuming it."),
        F(C.scenario_bars(D.mart("campaign_scenarios"))),
        _table(budget.rename(columns={"line": "Budget line", "cost_cu": "CU", "note": "How"})),
    ]})
    # 8 measurement -------------------------------------------------------------
    meas = econ[econ.role != "Not run"][["audience_label", "arm", "role", "experiment_population", "holdout", "contacted", "uplift_pp",
                                         "breakeven_uplift_pp", "mde_rate_pp", "readable_alone", "powered_for_decision"]].copy()
    meas = meas.round({"experiment_population": 0, "holdout": 0, "contacted": 0, "breakeven_uplift_pp": 2, "mde_rate_pp": 2})
    meas.columns = ["Audience", "Arm", "Role", "Reachable", "Holdout", "Arm size", "Assumed lift (pp)", "Break-even (pp)", "Detectable lift (pp)",
                    "Readable alone", "Sized for decision"]
    pr = camp["pooled_read"]
    sections.append({"id": "measurement", "title": "Measurement plan", "blocks": [
        _ul([
            "Control: in every audience 10% of reachable customers are held out by a salted hash of customer id (stratified, balance-checked). "
            "They get no autumn campaign communication (no campaign emails, app messages, early-access links; excluded from paid-social audiences and "
            "lookalike seeds) but keep the business-as-usual newsletters, Black Friday and Christmas sends.",
            "Estimand: intention-to-treat on everyone assigned. Primary KPI: 90-day repurchase rate. Secondary: revenue per customer (winsorised, "
            "adjusted for 12-month spend) and net profit.",
            f"Campaign-wide read: {fmt_n(pr['holdout_customers'])} holdout customers; detectable lift {pr['mde_rate_pp']:.2f} pp vs "
            f"{pr['expected_lift_pp']:.2f} pp expected.",
            "Test cells are sized so the detectable lift is at most two thirds of their break-even: a 'no' is informative. Content arms are read only "
            "in the pooled result. Day 30: guardrails only. Decision on day 90: scale an offer only if the 95% lower bound of its lift over the "
            "content cell clears its break-even (Holm-adjusted within At Risk).",
        ]),
        _table(meas),
    ]})
    # 9 cohorts -----------------------------------------------------------------
    coh = D.mart("cohort_retention")
    sections.append({"id": "cohorts", "title": "Cohorts and lifetime value", "blocks": [
        F(C.cohort_heatmap(coh)),
        _take("Late-2018 cohorts look stronger because they include existing customers whose first order in the data fell in that month (the data starts "
              "2018-09-20); from 2019-03 on, cohorts are mostly genuinely new customers."),
        F(C.ltv_curves(coh)),
        F(C.order_ladder(D.mart("order_ladder"))),
        _take("The second order is the biggest hurdle, which is why the New Customers journey is always-on and its coupon is the most likely discount "
              "to pay back (and is tested, not assumed)."),
    ]})
    # 10 recommendations, limitations ---------------------------------------------
    sections.append({"id": "recommendations", "title": "Recommendations", "blocks": [_ul([
        "Approve the content-led autumn plan and the two discount test cells; no discounts for Champions, Loyal or Slipping Regulars.",
        "Reach online-only customers online; use channel to choose the creative, not to push store visits.",
        "Run every audience against the same 10% holdout; decide on offers only on the day-90 read.",
        "Make the Slipping Regulars reminder and the New Customers journey always-on triggers if the pooled read is positive.",
        "Re-run the segmentation monthly with the same SQL; alert if Champions retention per quarter falls below 65% or At Risk -> Lost exceeds 10%.",
        "Ask Finance to confirm the 40% contribution margin and Retail Ops to review the Review List before any offer reaches those accounts.",
    ])]})
    sections.append({"id": "limitations", "title": "Limitations", "blocks": [_ul([
        "Revenue is gross demand: there are no returns in the data, and online returns are typically higher than store returns.",
        "Store purchases are only recorded when the member identifies; anonymous store shopping is invisible.",
        "Autumn 2020 is a COVID autumn; the backtests are autumn 2019 and the reopening summer of 2020. A second wave would change behaviour.",
        "Lifts, margin, coupon use and paid-social costs are planning assumptions until the holdout measures them.",
        "No order id: several online orders on one day count as one order, so a CRM tool with order ids will count slightly more orders.",
        "Left-censoring: the first order in the data is not always a customer's first order ever.",
    ])]})

    return REPORT.render(css=CSS, plotlyjs=get_plotlyjs(), snapshot=d["snapshot_date"], built=dt.date.today().isoformat(),
                         tldr=tldr, kpis=kpis, sections=sections)


def build_action_plan() -> str:
    m = D.metrics()
    h, camp, seg = m["headline"], m["campaign"], m["segments"]
    sc = camp["scenarios"]
    econ = D.mart("campaign_economics")
    focus = CP.audience_category_focus()
    rows = []
    for r in econ[econ.role != "Not run"].itertuples():
        rows.append({"Audience": r.audience_label, "Action": r.arm + (" (test cell)" if r.role == "Test cell" else ""),
                     "When": r.timing.split(";")[0], "Channel": CP.channel_label(r.channels, r.use_paid_social),
                     "Focus": focus.get(r.audience, "-"),
                     "Discount": "none" if r.discount_rate == 0 else f"{100 * r.discount_rate:.0f}%", "KPI": r.kpi.split("(")[0].strip()})
    for s, why in CP.NO_CAMPAIGN.items():
        rows.append({"Audience": s, "Action": "No offers or paid media until reviewed" if s == "Review List" else "No autumn spend",
                     "When": "-", "Channel": "-", "Focus": "-", "Discount": "-", "KPI": "-"})
    budget = D.mart("campaign_budget")
    answer = [
        f"Keep: Champions ({fmt_n(seg['Champions']['customers'])}, {pct(seg['Champions']['pct_revenue_12m'], 0)} of revenue) with early access, no discount.",
        f"Win back: At Risk ({fmt_n(h['at_risk_customers'])}) and Slipping Regulars ({fmt_n(h['slipping_customers'])}) with personalised content; "
        "offers only in test cells.",
        f"Online-only ({fmt_n(h['online_only_active_customers'])} active): reach them online; no paid push into stores.",
        f"Budget ask {fmt_cu(camp['budget_total_cu'])}; expected rollout net {D.fmt_k(sc['Base | Rollout']['net_profit_cu'])} CU on planning "
        f"assumptions (pessimistic {D.fmt_k(sc['Pessimistic | Rollout']['net_profit_cu'])}, optimistic {D.fmt_k(sc['Optimistic | Rollout']['net_profit_cu'])}).",
    ]
    measure = [
        "Same 10% holdout in every audience (no campaign communication; business-as-usual newsletters continue).",
        f"Primary KPI: 90-day repurchase rate vs holdout. Campaign-wide lift detectable from {camp['pooled_read']['mde_rate_pp']:.2f} pp.",
        f"Offers scale in the next wave only if their measured lift clears break-even. Final read {camp['read_date']}; day 30 = guardrails only.",
    ]
    asks = ["Sign off the plan and the budget.", "Finance: confirm the 40% contribution margin on incremental orders.",
            "Retail ops: review the 864 Review List accounts.", "Agree that offers scale only on measured results."]
    C.start_static_export()
    try:
        png = C.segment_share(D.mart("segment_profile")).to_image(format="png", width=1000, height=480, scale=1.5)
    finally:
        C.stop_static_export()
    return ACTION.render(css=CSS, snapshot=m["data"]["snapshot_date"], launch=camp["launch_date"], read=camp["read_date"], answer=answer,
                         plan_table=_table(pd.DataFrame(rows)),
                         budget_table=_table(budget.rename(columns={"line": "Line", "cost_cu": "CU", "note": "How it is calculated"})),
                         measure=measure, asks=asks, chart_png=base64.b64encode(png).decode())


def build_all(log: Callable[[str], None] = print) -> None:
    out = get_paths().reports
    (out / "report.html").write_text(build_report())
    log(f"  wrote reports/report.html ({(out / 'report.html').stat().st_size / 1e6:.1f} MB, opens offline)")
    (out / "action_plan.html").write_text(build_action_plan())
    log("  wrote reports/action_plan.html")
