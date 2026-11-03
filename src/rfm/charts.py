"""Every chart in the project, built once and reused by the dashboard, the HTML report and the
notebooks, so the three always show identical figures.

Style follows a quiet internal-tool look: one sans typeface, hairline grids, thin marks,
at most three categorical colours (blue / orange / aqua, validated for colour-blind
separation), grey for de-emphasis, blue <-> red only for "above / below" polarity.
Each figure's title is the one-line conclusion; the subtitle says what is plotted and the unit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from .segments import SEGMENT_ORDER

# ----------------------------------------------------------------------------- tokens
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"      # categorical slot 1 / accent
ORANGE = "#eb6834"    # slot 2
AQUA = "#1baf7a"      # slot 3
GREY = "#c3c2b7"      # de-emphasis
RED = "#e34948"       # negative pole of the blue <-> red diverging pair
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
SEQ_SCALE = [[i / (len(BLUE_RAMP) - 1), c] for i, c in enumerate(BLUE_RAMP)]
CHANNEL_COLORS = {"Online only": BLUE, "Omnichannel": ORANGE, "Store only": AQUA}

pio.templates["rfm"] = go.layout.Template(
    layout=dict(
        font=dict(family=FONT, size=13, color=INK2),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=[BLUE, ORANGE, AQUA],
        title=dict(x=0.0, xanchor="left", y=0.97, yanchor="top", font=dict(size=16, color=INK),
                   subtitle=dict(font=dict(size=12.5, color=MUTED))),
        xaxis=dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, showline=True, ticks="",
                   tickfont=dict(color=MUTED), title=dict(font=dict(color=INK2, size=12.5)), automargin=True),
        yaxis=dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, showline=False, ticks="",
                   tickfont=dict(color=MUTED), title=dict(font=dict(color=INK2, size=12.5)), automargin=True),
        legend=dict(orientation="h", x=0, xanchor="left", y=1.0, yanchor="bottom", font=dict(color=INK2, size=12),
                    bgcolor="rgba(0,0,0,0)", itemclick="toggleothers"),
        margin=dict(l=10, r=30, t=110, b=50),
        hoverlabel=dict(bgcolor="white", bordercolor=GRID, font=dict(family=FONT, color=INK, size=12)),
        bargap=0.35,
        bargroupgap=0.08,
        barcornerradius=4,
    )
)
pio.templates.default = "simple_white+rfm"


def _finish(fig: go.Figure, title: str, subtitle: str, height: int = 420) -> go.Figure:
    fig.update_layout(title=dict(text=f"<b>{title}</b>", subtitle=dict(text=subtitle)), height=height)
    return fig


def _segments_present(values) -> list[str]:
    present = set(map(str, values))
    return [s for s in SEGMENT_ORDER if s in present]


def _k(v: float) -> str:
    return f"{v / 1e6:.1f}M" if abs(v) >= 1e6 else (f"{v / 1e3:.0f}K" if abs(v) >= 1e3 else f"{v:.0f}")


# ============================================================================= overview / segments
def segment_share(prof: pd.DataFrame) -> go.Figure:
    """% of customers vs % of 12-month revenue per segment (the headline chart)."""
    p = prof.set_index("segment").reindex(_segments_present(prof["segment"]))
    p = p.iloc[::-1]  # Champions on top
    fig = go.Figure()
    fig.add_bar(y=p.index, x=100 * p["pct_customers"], orientation="h", name="% of customers", marker_color=GREY,
                text=[f"{v:.1f}%" for v in 100 * p["pct_customers"]], textposition="outside", cliponaxis=False,
                textfont=dict(color=INK2, size=11),
                hovertemplate="%{y}<br>%{x:.1f}% of customers<extra></extra>")
    fig.add_bar(y=p.index, x=100 * p["pct_revenue_12m"], orientation="h", name="% of 12-month revenue",
                marker_color=BLUE, text=[f"{v:.1f}%" for v in 100 * p["pct_revenue_12m"]], textposition="outside",
                cliponaxis=False, textfont=dict(color=INK, size=11),
                hovertemplate="%{y}<br>%{x:.1f}% of 12-month revenue<extra></extra>")
    fig.update_layout(barmode="group", xaxis=dict(title="% of total", ticksuffix="%", range=[0, 62]),
                      yaxis=dict(title=None), legend=dict(traceorder="reversed"))
    ch = prof.set_index("segment").loc["Champions"]
    return _finish(fig, f"Champions are {100 * ch.pct_customers:.0f}% of customers but {100 * ch.pct_revenue_12m:.0f}% of 12-month revenue",
                   "Share of the 1.36M customers with a purchase vs share of revenue, 12 months to 2020-09-22", height=500)


def segment_outcomes(seg_out: pd.DataFrame) -> go.Figure:
    """Backtest validation: share of each segment that bought again within 90 days."""
    d = seg_out[seg_out["segment"] != "Review List"].copy()
    segs = _segments_present(d["segment"])
    fig = go.Figure()
    for basis, name, color in (("backtest_seasonal", "Segments as of 2019-09-22 (same season)", BLUE),
                               ("backtest_recent", "Segments as of 2020-06-24 (last quarter)", ORANGE)):
        s = d[d.snapshot_name == basis].set_index("segment").reindex(segs)
        fig.add_bar(x=segs, y=100 * s["repurchase_rate"], name=name, marker_color=color,
                    text=[f"{v:.0f}%" for v in 100 * s["repurchase_rate"]], textposition="outside",
                    textfont=dict(color=INK2, size=11), cliponaxis=False,
                    customdata=np.stack([s["customers"]], axis=-1),
                    hovertemplate="%{x}<br>%{y:.1f}% bought again within 90 days<br>%{customdata[0]:,} customers<extra></extra>")
    fig.update_layout(barmode="group", yaxis=dict(title="Bought again within 90 days", ticksuffix="%", range=[0, 100]),
                      xaxis=dict(title=None))
    s = d[d.snapshot_name == "backtest_seasonal"].set_index("segment")
    return _finish(fig, f"The segments predict behaviour: {100 * s.loc['Champions', 'repurchase_rate']:.0f}% of Champions bought again within 90 days, "
                        f"{100 * s.loc['At Risk', 'repurchase_rate']:.0f}% of At Risk",
                   "Same rules applied at two past dates; % of each segment with at least one order in the following 90 days", 440)


# ============================================================================= data & sanity checks
def weekly_channel(trend: pd.DataFrame) -> go.Figure:
    d = trend[~trend["is_partial_week"]].copy()
    d["week_start"] = pd.to_datetime(d["week_start"])
    weeks = pd.date_range(d["week_start"].min(), d["week_start"].max(), freq="7D")
    fig = go.Figure()
    for ch, color in (("Online", BLUE), ("Store", ORANGE)):
        # weeks with no store orders have no row: fill them with 0 so the closure shows as a flat zero
        s = (d[d.channel == ch].set_index("week_start")[["orders"]].reindex(weeks, fill_value=0)
             .rename_axis("week_start").reset_index())
        fig.add_scatter(x=s["week_start"], y=s["orders"] / 1e3, mode="lines", name=f"Channel {'2' if ch == 'Online' else '1'} ({ch.lower()})",
                        line=dict(color=color, width=2), hovertemplate="Week of %{x|%Y-%m-%d}<br>%{y:.1f}K orders<extra></extra>")
    fig.add_vrect(x0="2020-03-20", x1="2020-05-05", fillcolor=GREY, opacity=0.25, line_width=0)
    fig.add_annotation(x="2020-04-12", y=1.0, yref="paper", text="Stores closed<br>(COVID)", showarrow=False,
                       font=dict(size=11, color=INK2), yanchor="top")
    fig.update_layout(yaxis=dict(title="Orders per week (thousands)", rangemode="tozero"), xaxis=dict(title=None))
    return _finish(fig, "Channel 1 drops to zero while stores were closed in spring 2020, so 1 = store, 2 = online",
                   "Orders per week by sales channel (order = one customer, one day, one channel); partial first/last weeks dropped", 400)


def price_points(pp: pd.DataFrame) -> go.Figure:
    d = pp.sort_values("units").tail(15)
    labels = [f"{v:.2f}" for v in d["price_cu"]]
    fig = go.Figure(go.Bar(x=d["units"] / 1e6, y=labels, orientation="h", marker_color=BLUE,
                           text=[f"{v:.1f}M" for v in d["units"] / 1e6], textposition="outside", cliponaxis=False,
                           textfont=dict(color=INK2, size=11),
                           hovertemplate="Price %{y} CU<br>%{x:.2f}M items<extra></extra>"))
    fig.update_layout(xaxis=dict(title="Items sold (millions)"), yaxis=dict(title="price x 590", type="category"))
    share = pp.sort_values("units", ascending=False).head(15)["units"].sum() / pp["units_total"].iloc[0]
    return _finish(fig, "Multiplying the scaled price by 590 recovers familiar retail price points (9.99, 19.99, 14.99 ...)",
                   f"15 most common prices after x 590; together {100 * share:.0f}% of all items sold. Money in this project = CU (currency undisclosed)", 470)


# ============================================================================= RFM scoring
def return_curve(curve: pd.DataFrame, snapshot: str = "backtest_seasonal",
                 cuts: tuple[int, ...] = (30, 60, 120, 180, 365)) -> go.Figure:
    d = curve[curve.snapshot_name == snapshot]
    fig = go.Figure()
    names = {"2+ orders": "2+ orders in the 12 months before", "1 order": "1 order in the 12 months before",
             "No order in 12 months": "No order in the 12 months before (lapsed)"}
    for grp, color in (("2+ orders", BLUE), ("1 order", ORANGE), ("No order in 12 months", GREY)):
        s = d[(d.frequency_group == grp) & (d.customers >= 500)].sort_values("recency_bucket_start")
        if s.empty:
            continue
        fig.add_scatter(x=s["recency_bucket_start"] + 7, y=100 * s["return_rate_90d"], mode="lines+markers",
                        name=names[grp], line=dict(color=color, width=2),
                        marker=dict(size=6, color=color, line=dict(color=SURFACE, width=1)),
                        customdata=np.stack([s["recency_bucket_start"], s["recency_bucket_end"], s["customers"]], axis=-1),
                        hovertemplate="Last order %{customdata[0]}-%{customdata[1]} days ago<br>%{y:.1f}% bought within the next 90 days"
                                      "<br>%{customdata[2]:,} customers<extra></extra>")
    labels = ["R5 | R4", "R4 | R3", "R3 | R2", "R2 | R1", "Lost"]
    for c, lab in zip(cuts, labels):
        fig.add_vline(x=c, line_width=1, line_color=AXIS)
        fig.add_annotation(x=c, y=1.0, yref="paper", text=lab, showarrow=False, font=dict(size=10, color=MUTED),
                           yanchor="bottom", xanchor="center")
    when = "2019-09-22" if snapshot == "backtest_seasonal" else "2020-06-24"
    fig.update_layout(xaxis=dict(title="Days since last order at the snapshot", range=[0, 740 if snapshot == "backtest_recent" else 370]),
                      yaxis=dict(title="Bought again within 90 days", ticksuffix="%", rangemode="tozero"),
                      legend=dict(y=1.08))
    return _finish(fig, "The chance of buying again falls steadily with days since the last order: no single cliff, so thresholds are a business choice",
                   f"Customers grouped in 15-day recency buckets at {when}; vertical lines = R-score cut-offs", 450)


def score_distribution(scores: pd.DataFrame, method: str) -> go.Figure:
    fig = make_subplots(rows=1, cols=3, subplot_titles=("Recency score", "Frequency score", "Monetary score"),
                        horizontal_spacing=0.08)
    for i, col in enumerate(["r", "f", "m"], start=1):
        vc = scores[col].value_counts(normalize=True).reindex(range(1, 6), fill_value=0)
        fig.add_bar(x=[str(k) for k in vc.index], y=100 * vc.values, marker_color=BLUE, showlegend=False,
                    text=[f"{v:.0f}%" for v in 100 * vc.values], textposition="outside", cliponaxis=False,
                    textfont=dict(size=10, color=INK2), row=1, col=i,
                    hovertemplate="Score %{x}<br>%{y:.1f}% of active customers<extra></extra>")
    fig.update_yaxes(ticksuffix="%", range=[0, 60], gridcolor=GRID)
    fig.update_annotations(font=dict(size=12, color=INK2))
    fig.update_layout(margin=dict(t=120))
    return _finish(fig, f"Score distribution with {method}",
                   "Share of 12-month-active customers per score (1 = worst, 5 = best)", 360)


def rf_heatmap(grid: pd.DataFrame, value: str = "customers") -> go.Figure:
    """R score (rows) x F score (columns) for 12-month-active customers."""
    piv = grid.pivot_table(index="r_score", columns="f_score", values=value, aggfunc="sum").reindex(
        index=[5, 4, 3, 2, 1], columns=[1, 2, 3, 4, 5]).fillna(0)
    total = piv.values.sum()
    txt = [[f"{_k(v)}<br>{100 * v / total:.1f}%" for v in row] for row in piv.values]
    fig = go.Figure(go.Heatmap(z=piv.values, x=[f"F{c}" for c in piv.columns], y=[f"R{r}" for r in piv.index],
                               colorscale=SEQ_SCALE, text=txt, texttemplate="%{text}", textfont=dict(size=11),
                               xgap=2, ygap=2, colorbar=dict(title=dict(text="customers" if value == "customers" else "CU", side="right"), thickness=10),
                               hovertemplate="%{y} x %{x}<br>%{z:,.0f}<extra></extra>"))
    fig.update_layout(xaxis=dict(title="Frequency score (orders in 12 months)", showline=False, side="bottom"),
                      yaxis=dict(title="Recency score", autorange="reversed"), plot_bgcolor=SURFACE)
    what = "customers" if value == "customers" else "12-month revenue"
    return _finish(fig, f"Where the {what} sit on the Recency x Frequency grid",
                   "12-month-active customers; R5 = bought in the last 30 days, F5 = 10+ orders", 420)


def segment_size_compare(base: pd.DataFrame, new: pd.DataFrame) -> go.Figure:
    """Default vs user-adjusted segment sizes (interactive threshold page)."""
    segs = _segments_present(base["segment"])
    b = base.set_index("segment").reindex(segs)
    n = new.set_index("segment").reindex(segs)
    fig = go.Figure()
    fig.add_bar(x=segs, y=b["customers"] / 1e3, name="Default thresholds", marker_color=GREY,
                hovertemplate="%{x}<br>%{y:.1f}K customers (default)<extra></extra>")
    fig.add_bar(x=segs, y=n["customers"] / 1e3, name="Your thresholds", marker_color=BLUE,
                text=[f"{(nv - bv) / 1e3:+.1f}K" if abs(nv - bv) >= 50 else "" for nv, bv in zip(n["customers"], b["customers"])],
                textposition="outside", cliponaxis=False, textfont=dict(size=11, color=INK2),
                hovertemplate="%{x}<br>%{y:.1f}K customers (yours)<extra></extra>")
    fig.update_layout(barmode="group", yaxis=dict(title="Customers (thousands)"), xaxis=dict(title=None))
    moved = int((n["customers"] - b["customers"]).clip(lower=0).sum())
    return _finish(fig, f"{moved:,} customers change segment with your thresholds" if moved else "Same segment sizes as the default rules",
                   "Customers per segment at 2020-09-22: default business thresholds vs the values set above", 400)


def quantile_vs_business(edges: dict, business: dict) -> pd.DataFrame:
    """Table, not a chart: the two cut methods side by side."""
    rows = []
    for metric, label in (("recency_days", "Recency (days)"), ("frequency_12m", "Frequency (orders, 12m)"),
                          ("monetary_12m_cu", "Monetary (CU, 12m)")):
        rows.append({"metric": label,
                     "quintile cut points (20/40/60/80%)": " / ".join(f"{v:,.0f}" for v in edges[metric]),
                     "business thresholds": business[metric]})
    return pd.DataFrame(rows)


# ============================================================================= k-means
def kmeans_selection(sel: pd.DataFrame, k_final: int) -> go.Figure:
    fig = go.Figure(go.Scatter(x=sel["k"], y=sel["silhouette"], mode="lines+markers", line=dict(color=BLUE, width=2),
                               marker=dict(size=9, color=[ORANGE if k == k_final else BLUE for k in sel["k"]],
                                           line=dict(color=SURFACE, width=2)),
                               hovertemplate="k = %{x}<br>silhouette %{y:.3f}<extra></extra>"))
    best = sel.loc[sel["silhouette"].idxmax()]
    fig.add_annotation(x=k_final, y=float(sel.set_index("k").loc[k_final, "silhouette"]), text=f"k = {k_final} used for the comparison",
                       showarrow=True, arrowhead=0, ax=40, ay=-30, font=dict(size=11, color=INK2), arrowcolor=AXIS)
    fig.update_layout(xaxis=dict(title="Number of clusters k", dtick=1), yaxis=dict(title="Silhouette score (higher = better separated)"))
    return _finish(fig, f"No natural clusters: separation is best at k = {int(best.k)} and falls as k grows",
                   "K-Means on log Recency, Frequency, Monetary (standardised), 12-month-active customers; silhouette on a 20K sample", 380)


def kmeans_crosstab(ct: pd.DataFrame, prof: pd.DataFrame) -> go.Figure:
    piv = ct.pivot_table(index="cluster", columns="segment", values="customers", aggfunc="sum").fillna(0)
    piv = piv[[s for s in SEGMENT_ORDER if s in piv.columns and s not in ("Lost", "Review List")]]
    share = piv.div(piv.sum(axis=1), axis=0)
    names = {r.cluster: f"Cluster {r.cluster}: median {r.median_orders_12m:.0f} orders, {r.median_recency_days:.0f} days, {r.median_revenue_12m_cu:.0f} CU"
             for r in prof.itertuples()}
    fig = go.Figure(go.Heatmap(z=100 * share.values, x=share.columns, y=[names[c] for c in share.index], colorscale=SEQ_SCALE,
                               text=[[f"{v:.0f}%" if v >= 1 else "" for v in row] for row in 100 * share.values],
                               texttemplate="%{text}", textfont=dict(size=11), xgap=2, ygap=2, zmin=0, zmax=100,
                               colorbar=dict(title=dict(text="% of cluster", side="right"), thickness=10),
                               hovertemplate="%{y}<br>%{x}: %{z:.1f}% of the cluster<extra></extra>"))
    fig.update_layout(xaxis=dict(title=None, showline=False), yaxis=dict(title=None, autorange="reversed"))
    return _finish(fig, "K-Means finds the Champions but blends segments that need different actions",
                   "Each row = one K-Means cluster; cells = % of the cluster's customers in each rule-based segment", 420)


# ============================================================================= drill-down
def category_affinity(mix: pd.DataFrame, segment: str, dimension: str = "garment_group",
                      min_overall_share: float = 0.01) -> go.Figure:
    d = mix[(mix.segment == segment) & (mix.dimension == dimension) & (mix.overall_share >= min_overall_share)
            & (mix.value != "Unknown")].copy()
    d = d.sort_values("affinity_index")
    colors = [BLUE if v >= 100 else RED for v in d["affinity_index"]]
    fig = go.Figure(go.Bar(x=d["affinity_index"] - 100, y=d["value"], base=100, orientation="h", marker_color=colors,
                           customdata=np.stack([100 * d["segment_share"], 100 * d["overall_share"]], axis=-1),
                           text=[f"{v:.0f}" for v in d["affinity_index"]], textposition="outside", cliponaxis=False,
                           textfont=dict(size=11, color=INK2),
                           hovertemplate="%{y}<br>index %{x:.0f}<br>%{customdata[0]:.1f}% of this segment's revenue"
                                         "<br>%{customdata[1]:.1f}% across all customers<extra></extra>"))
    fig.add_vline(x=100, line_width=1, line_color=INK2)
    label = {"garment_group": "garment group", "index_group": "department", "product_group": "product group"}[dimension]
    top = d.sort_values("affinity_index", ascending=False).head(2)
    fig.update_layout(xaxis=dict(title="Affinity index (100 = same share as all customers)"), yaxis=dict(title=None))
    return _finish(fig, f"{segment} over-index on {top['value'].iloc[0]} ({top['affinity_index'].iloc[0]:.0f}) and {top['value'].iloc[1]} ({top['affinity_index'].iloc[1]:.0f})",
                   f"Revenue share by {label} vs all customers; categories with at least {100 * min_overall_share:.0f}% of total revenue", 520)


def channel_mix(mix: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    d = mix[(mix.dimension == "channel_12m") & ~mix.segment.isin(["Review List", "Lost"]) & (mix.value != "No 12m orders")]
    segs = _segments_present(d["segment"])[::-1]
    fig = go.Figure()
    for ch in ("Online only", "Omnichannel", "Store only"):
        s = d[d.value == ch].set_index("segment").reindex(segs)
        fig.add_bar(y=segs, x=100 * s["segment_share"], orientation="h", name=ch, marker_color=CHANNEL_COLORS[ch],
                    marker_line=dict(color=SURFACE, width=2),
                    text=[f"{v:.0f}%" if v >= 8 else "" for v in 100 * s["segment_share"]], textposition="inside",
                    insidetextanchor="middle", textfont=dict(size=11, color="#ffffff"),
                    hovertemplate="%{y}<br>" + ch + ": %{x:.1f}% of customers<extra></extra>")
    fig.update_layout(barmode="stack", barcornerradius=0, xaxis=dict(title="% of the segment's customers", ticksuffix="%", range=[0, 100]),
                      yaxis=dict(title=None), legend=dict(traceorder="normal"))
    ch_ = d[(d.value == "Online only")].set_index("segment")["segment_share"]
    return _finish(fig, f"Online-only shoppers are {100 * ch_['Champions']:.0f}% of Champions but {100 * ch_['New Customers']:.0f}% of New Customers",
                   "Channel use in the last 12 months: online only / both / store only (store = identified member purchases only); Lost not shown", 470)


def age_mix(mix: pd.DataFrame, segment: str) -> go.Figure:
    d = mix[(mix.dimension == "age_band") & (mix.segment == segment)].set_index("value")
    order = ["16-24", "25-34", "35-44", "45-54", "55-64", "65+", "Unknown"]
    d = d.reindex([o for o in order if o in d.index])
    fig = go.Figure()
    fig.add_bar(x=d.index, y=100 * d["overall_share"], name="All customers", marker_color=GREY,
                hovertemplate="%{x}<br>%{y:.1f}% of all customers<extra></extra>")
    fig.add_bar(x=d.index, y=100 * d["segment_share"], name=segment, marker_color=BLUE,
                hovertemplate="%{x}<br>%{y:.1f}% of " + segment + "<extra></extra>")
    fig.update_layout(barmode="group", yaxis=dict(title="% of customers", ticksuffix="%"), xaxis=dict(title="Age band"))
    top = d["segment_share"].idxmax()
    return _finish(fig, f"{segment}: largest age band is {top} ({100 * d.loc[top, 'segment_share']:.0f}%)",
                   "Age distribution of the segment vs all customers (age from the customer file)", 380)


def channel_value(cv: pd.DataFrame, net_of_returns: bool = False) -> go.Figure:
    bands = ["1 order", "2 orders", "3-4 orders", "5-9 orders", "10+ orders"]
    col = "revenue_net_of_returns_cu" if net_of_returns else "revenue_per_customer_cu"
    fig = go.Figure()
    for ch in ("Online only", "Omnichannel", "Store only"):
        s = cv[cv.channel == ch].set_index("order_band").reindex(bands)
        fig.add_bar(x=bands, y=s[col], name=ch, marker_color=CHANNEL_COLORS[ch],
                    customdata=np.stack([s["customers"].fillna(0), s["aov_cu"]], axis=-1),
                    hovertemplate="%{x}, " + ch + "<br>%{y:.0f} CU per customer in 12 months<br>AOV %{customdata[1]:.1f} CU"
                                  "<br>%{customdata[0]:,.0f} customers<extra></extra>")
    fig.update_layout(barmode="group", yaxis=dict(title="12-month revenue per customer (CU)"), xaxis=dict(title="Orders in the last 12 months"))
    what = "after an illustrative returns haircut (25% online, 8% store)" if net_of_returns else "gross demand, before returns (no returns in the data)"
    return _finish(fig, "At equal order counts online-only customers buy bigger baskets, so they show more gross demand per customer",
                   f"12-month-active customers, channel = last 12 months; {what}", 430)


def channel_forward(fw: pd.DataFrame, snapshot: str = "backtest_seasonal") -> go.Figure:
    bands = ["1 order", "2 orders", "3-4 orders", "5-9 orders", "10+ orders"]
    d = fw[fw.snapshot_name == snapshot]
    fig = go.Figure()
    for ch in ("Online only", "Omnichannel", "Store only"):
        s = d[d.channel == ch].set_index("order_band").reindex(bands)
        fig.add_bar(x=bands, y=100 * s["repurchase_rate_90d"], name=ch, marker_color=CHANNEL_COLORS[ch],
                    customdata=np.stack([s["customers"].fillna(0), s["revenue_next_90d_per_customer_cu"]], axis=-1),
                    hovertemplate="%{x}, " + ch + "<br>%{y:.1f}% bought again within 90 days<br>%{customdata[1]:.0f} CU per customer"
                                  "<br>%{customdata[0]:,.0f} customers<extra></extra>")
    fig.update_layout(barmode="group", yaxis=dict(title="Bought again within 90 days", ticksuffix="%", range=[0, 100]),
                      xaxis=dict(title="Orders in the 12 months before the backtest date"))
    g = d[d.order_band == "5-9 orders"].set_index("channel")["repurchase_rate_90d"]
    return _finish(fig, f"Looking forward, online-only customers come back slightly less often (5-9 orders: {100 * g['Online only']:.0f}% vs "
                        f"{100 * g['Omnichannel']:.0f}% omnichannel)",
                   "Backtest 2019-09-22: channel measured on the 12 months before the date, behaviour in the 90 days after", 430)


# ============================================================================= revenue at risk
def run_rate_vs_expected(rar: pd.DataFrame) -> go.Figure:
    d = rar[(rar.run_rate_90d_cu > 0) & (rar.segment.astype(str) != "Review List")].copy()
    segs = _segments_present(d["segment"])[::-1]
    d = d.set_index(d["segment"].astype(str)).reindex(segs)
    fig = go.Figure()
    fig.add_bar(y=segs, x=d["run_rate_90d_cu"] / 1e6, orientation="h", name="At their usual 12-month pace", marker_color=GREY,
                hovertemplate="%{y}<br>%{x:.2f}M CU per 90 days at their usual pace<extra></extra>")
    fig.add_bar(y=segs, x=d["expected_90d_cu_base"] / 1e6, orientation="h", name="Expected if we do nothing (backtest)",
                marker_color=BLUE, text=[f"{(-s / 1e6):+.2f}M" if s > 0 else f"+{-s / 1e6:.2f}M" for s in d["gap_90d_cu_base"]],
                textposition="outside", cliponaxis=False, textfont=dict(size=11, color=INK2),
                hovertemplate="%{y}<br>%{x:.2f}M CU expected in the next 90 days<extra></extra>")
    fig.update_layout(barmode="group", xaxis=dict(title="Revenue in the next 90 days (million CU)"), yaxis=dict(title=None),
                      legend=dict(traceorder="reversed"))
    ar = rar.set_index(rar["segment"].astype(str)).loc["At Risk"]
    return _finish(fig, f"If we do nothing, At Risk spends about {100 * (1 - ar.realisation_base):.0f}% below its usual pace: "
                        f"{ar.expected_90d_cu_base / 1e6:.1f}M CU instead of {ar.run_rate_90d_cu / 1e6:.1f}M in the next 90 days",
                   "Usual pace = 12-month revenue x 90/365; expected = usual pace x what look-alike customers spent after 2019-09-22 "
                   "(re-weighted to today's mix); labels = gap vs usual pace", 470)


def shortfall_waterfall(run_rate: float, expected: float, segment: str) -> go.Figure:
    gap = run_rate - expected
    fig = go.Figure(go.Waterfall(
        x=["Usual 90-day pace", "Shortfall if we do nothing", "Expected next 90 days"],
        measure=["absolute", "relative", "total"], y=[run_rate / 1e6, -gap / 1e6, 0],
        text=[f"{run_rate / 1e6:.2f}M", f"-{gap / 1e6:.2f}M", f"{expected / 1e6:.2f}M"], textposition="outside",
        connector=dict(line=dict(color=AXIS, width=1)),
        increasing=dict(marker=dict(color=BLUE)), decreasing=dict(marker=dict(color=RED)), totals=dict(marker=dict(color=BLUE)),
        hovertemplate="%{x}<br>%{y:.2f}M CU<extra></extra>"))
    fig.update_layout(yaxis=dict(title="Million CU", rangemode="tozero"), showlegend=False)
    return _finish(fig, f"{segment}: {gap / 1e6:.2f}M CU gap vs usual pace over the next 90 days",
                   "Usual pace vs business-as-usual projection for the audience defined above (part of the gap is natural slowdown)", 380)


# ============================================================================= campaign
def net_profit_by_arm(econ: pd.DataFrame) -> go.Figure:
    d = econ[econ.role != "Not run"].copy()
    d["label"] = d["audience_label"] + " - " + d["arm"]
    d = d.iloc[::-1]
    colors = [BLUE if v >= 0 else RED for v in d["net_profit_cu"]]
    fig = go.Figure(go.Bar(x=d["net_profit_cu"] / 1e3, y=d["label"], orientation="h", marker_color=colors,
                           text=[f"{v / 1e3:+.1f}K" for v in d["net_profit_cu"]], textposition="outside", cliponaxis=False,
                           textfont=dict(size=11, color=INK2),
                           customdata=np.stack([d["incremental_revenue_cu"] / 1e3, d["total_cost_cu"] / 1e3, d["uplift_pp"]], axis=-1),
                           hovertemplate="%{y}<br>net %{x:+.1f}K CU<br>incremental revenue %{customdata[0]:.1f}K CU"
                                         "<br>cost %{customdata[1]:.1f}K CU<br>assumed lift +%{customdata[2]:.1f} pp<extra></extra>"))
    fig.add_vline(x=0, line_width=1, line_color=INK2)
    lo, hi = float(d["net_profit_cu"].min()) / 1e3, float(d["net_profit_cu"].max()) / 1e3
    span = hi - min(lo, 0)
    fig.update_layout(xaxis=dict(title="Expected 90-day net profit (thousand CU)", range=[min(lo, 0) - 0.18 * span, hi + 0.12 * span]),
                      yaxis=dict(title=None), margin=dict(l=10, r=60))
    neg = d[d.net_profit_cu < 0]
    title = ("Content-led actions pay back; the discount test cells are expected to cost money (the price of learning)"
             if len(neg) and (neg.discount_rate > 0).all() else "Expected net profit by campaign arm")
    return _finish(fig, title, "Net = incremental contribution (one order at the audience AOV, 40% margin) - discount cost - contact cost; "
                               "lifts are planning assumptions", 560)


def breakeven_vs_assumed(econ: pd.DataFrame) -> go.Figure:
    d = econ.copy()
    d["label"] = d["audience_label"] + " - " + d["arm"] + np.where(d["role"] == "Not run", " (not run)", "")
    d = d.iloc[::-1]
    be = d["breakeven_uplift_pp"].clip(upper=16)
    fig = go.Figure()
    for _, r in d.iterrows():
        fig.add_shape(type="line", x0=min(r.uplift_pp, min(r.breakeven_uplift_pp, 16)), x1=max(r.uplift_pp, min(r.breakeven_uplift_pp, 16)),
                      y0=r.label, y1=r.label, line=dict(color=AXIS, width=2))
    fig.add_scatter(x=d["uplift_pp"], y=d["label"], mode="markers", name="Assumed lift", marker=dict(size=11, color=BLUE, line=dict(color=SURFACE, width=2)),
                    hovertemplate="%{y}<br>assumed +%{x:.2f} pp<extra></extra>")
    fig.add_scatter(x=be, y=d["label"], mode="markers", name="Lift needed to break even", marker=dict(size=11, color=RED, symbol="diamond", line=dict(color=SURFACE, width=2)),
                    hovertemplate="%{y}<br>break-even +%{x:.2f} pp<extra></extra>")
    fig.update_layout(xaxis=dict(title="Lift in 90-day repurchase rate (percentage points)", rangemode="tozero"), yaxis=dict(title=None))
    return _finish(fig, "An offer pays back only where the assumed lift (blue) clears the break-even lift (red)",
                   "Break-even lift = what the arm must add to the 90-day repurchase rate to cover its discount and contact cost (one-order value)", 600)


def mde_by_holdout(power_tbl: pd.DataFrame, audience: str, assumed_pp: float, chosen_share: float) -> go.Figure:
    d = power_tbl[power_tbl.audience == audience].sort_values("holdout_share")
    segment = d["audience_label"].iloc[0]
    fig = go.Figure(go.Scatter(x=100 * d["holdout_share"], y=d["mde_rate_pp"], mode="lines+markers", line=dict(color=BLUE, width=2),
                               marker=dict(size=9, color=BLUE, line=dict(color=SURFACE, width=2)), name="Minimum detectable lift",
                               hovertemplate="holdout %{x:.0f}%<br>detects lifts of %{y:.2f} pp or more<extra></extra>"))
    fig.add_hline(y=assumed_pp, line_width=1, line_color=ORANGE)
    fig.add_annotation(x=100 * d["holdout_share"].max(), y=assumed_pp, text=f"assumed lift +{assumed_pp:.1f} pp", showarrow=False,
                       xanchor="right", yanchor="bottom", font=dict(size=11, color=INK2))
    fig.add_vline(x=100 * chosen_share, line_width=1, line_color=AXIS)
    fig.update_layout(xaxis=dict(title="Holdout share of the reachable audience", ticksuffix="%"),
                      yaxis=dict(title="Minimum detectable lift (pp)", rangemode="tozero"), showlegend=False)
    ok = d[d.mde_rate_pp <= assumed_pp]
    verdict = (f"a {100 * ok.holdout_share.min():.0f}% holdout is enough to detect +{assumed_pp:.1f} pp" if len(ok)
               else f"even a 30% holdout cannot detect +{assumed_pp:.1f} pp: read this segment only in the pooled holdout")
    return _finish(fig, f"{segment}: {verdict}", "Two-sided test, 5% significance, 80% power, on the 90-day repurchase rate", 360)


# ============================================================================= cohorts
def cohort_heatmap(coh: pd.DataFrame, max_months: int = 12) -> go.Figure:
    d = coh.groupby(["cohort_month", "month_number"], as_index=False).agg(active=("active_customers", "sum"))
    sizes = coh[coh.month_number == 0].groupby("cohort_month")["cohort_customers"].sum()
    d["retention"] = d["active"] / d["cohort_month"].map(sizes)
    piv = d[(d.month_number >= 1) & (d.month_number <= max_months)].pivot(index="cohort_month", columns="month_number", values="retention")
    labels = [pd.Timestamp(c).strftime("%Y-%m") for c in piv.index]
    fig = go.Figure(go.Heatmap(z=100 * piv.values, x=[f"M{m}" for m in piv.columns], y=labels, colorscale=SEQ_SCALE, xgap=2, ygap=2,
                               text=[[("" if np.isnan(v) else f"{v:.0f}") for v in row] for row in 100 * piv.values],
                               texttemplate="%{text}", textfont=dict(size=10),
                               colorbar=dict(title=dict(text="% active", side="right"), thickness=10),
                               hovertemplate="Cohort %{y}, %{x}<br>%{z:.1f}% bought in that month<extra></extra>"))
    fig.update_layout(xaxis=dict(title="Months after the first-order month", showline=False, side="top"),
                      yaxis=dict(title="First-order month (cohort)", autorange="reversed", type="category"), margin=dict(t=140))
    m1 = piv[1].dropna()
    return _finish(fig, f"Month-1 retention ranges {100 * m1.min():.0f}-{100 * m1.max():.0f}%; late-2018 cohorts look stronger because they include existing customers",
                   "% of each first-order cohort that bought again in each later month (M0 = 100% by definition, not shown)", 620)


def ltv_curves(coh: pd.DataFrame, first_cohort: str = "2019-01-01", last_cohort: str = "2019-08-01",
               months: int = 12) -> go.Figure:
    months_ = pd.to_datetime(coh["cohort_month"])
    d = coh[(months_ >= pd.Timestamp(first_cohort)) & (months_ <= pd.Timestamp(last_cohort))]
    sizes = d[d.month_number == 0].groupby("first_order_channel")["cohort_customers"].sum()
    fig = go.Figure()
    out = {}
    for ch, color in (("Online", BLUE), ("Store", ORANGE), ("Both", AQUA)):
        s = d[(d.first_order_channel == ch) & (d.month_number <= months)].groupby("month_number")["revenue_cu"].sum()
        cum = s.sort_index().cumsum() / sizes.get(ch, np.nan)
        out[ch] = cum
        fig.add_scatter(x=cum.index, y=cum.values, mode="lines+markers", name=f"First order {ch.lower() if ch != 'Both' else 'in both channels'}",
                        line=dict(color=color, width=2), marker=dict(size=6, color=color),
                        hovertemplate="Month %{x}<br>%{y:.0f} CU per customer so far<extra></extra>")
    fig.update_layout(xaxis=dict(title="Months after the first-order month", dtick=1),
                      yaxis=dict(title="Cumulative revenue per customer (CU)", rangemode="tozero"))
    end = {k: v.iloc[-1] for k, v in out.items() if len(v)}
    return _finish(fig, f"Observed {months}-month LTV: {end.get('Both', 0):.0f} CU when the first day used both channels, "
                        f"{end.get('Online', 0):.0f} online-first, {end.get('Store', 0):.0f} store-first",
                   f"Cohorts {first_cohort[:7]} to {last_cohort[:7]} ({months} full months of follow-up), by channel of the first order", 420)


def order_ladder(ladder: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for cohort, color in (("new: first order 2019-03-01 to 2019-09-22", BLUE), ("first order 2018-09-20 to 2019-09-22", GREY)):
        s = ladder[(ladder.cohort == cohort) & ladder.p_next_order.notna()]
        fig.add_scatter(x=s["orders"], y=100 * s["p_next_order"], mode="lines+markers",
                        name="Likely new customers (first order Mar-Sep 2019)" if cohort.startswith("new") else "Everyone first seen in year 1",
                        line=dict(color=color, width=2), marker=dict(size=8, color=color, line=dict(color=SURFACE, width=2)),
                        hovertemplate="After order %{x}<br>%{y:.1f}% place another within 12 months of the first<extra></extra>")
    fig.update_layout(xaxis=dict(title="Orders placed so far", dtick=1), yaxis=dict(title="Chance of one more order", ticksuffix="%", range=[50, 90]))
    s = ladder[ladder.cohort.str.startswith("new")].set_index("orders")["p_next_order"]
    return _finish(fig, f"The second order is the biggest hurdle: {100 * (1 - s.loc[1]):.0f}% of new customers never place one within a year",
                   "Share of customers with n orders who go on to place order n+1 within 12 months of their first order", 380)


# ============================================================================= value tier, flow, scenarios
def value_grid(grid: pd.DataFrame, value: str = "customers") -> go.Figure:
    tiers = ["VIP", "High", "Mid", "Low"]
    d = grid[grid.value_tier.isin(tiers) & (grid.segment != "Review List")]
    piv = d.pivot_table(index="segment", columns="value_tier", values=value, aggfunc="sum").reindex(columns=tiers).fillna(0)
    piv = piv.reindex([s for s in SEGMENT_ORDER if s in piv.index])
    total = grid[value].sum()
    txt = [[("" if v == 0 else f"{_k(v)}<br>{100 * v / total:.1f}%") for v in row] for row in piv.values]
    fig = go.Figure(go.Heatmap(z=piv.values, x=["VIP 1,000+ CU", "High 400-999", "Mid 200-399", "Low < 200"], y=piv.index,
                               colorscale=SEQ_SCALE, text=txt, texttemplate="%{text}", textfont=dict(size=11), xgap=2, ygap=2,
                               colorbar=dict(title=dict(text="customers" if value == "customers" else "CU", side="right"), thickness=10),
                               hovertemplate="%{y} x %{x}<br>%{z:,.0f}<extra></extra>"))
    fig.update_layout(xaxis=dict(title="Value tier (12-month spend)", showline=False, side="top"),
                      yaxis=dict(title=None, autorange="reversed"), margin=dict(t=150))
    vip = grid[grid.value_tier == "VIP"]
    share = vip.revenue_12m_cu.sum() / grid.revenue_12m_cu.sum()
    return _finish(fig, f"Value is a second axis: {_k(vip.customers.sum())} VIPs (1,000+ CU) bring in {100 * share:.0f}% of 12-month revenue, "
                        "and high spenders also sit outside Champions",
                   "Lifecycle segment x value tier, current snapshot; cells show " + ("customers" if value == "customers" else "12-month revenue") +
                   " and share of the total (Lost has no 12-month spend)", 520)


def segment_flow(flow: pd.DataFrame) -> go.Figure:
    order_from = [s for s in SEGMENT_ORDER if s != "Review List"] + ["Not yet a customer"]
    order_to = [s for s in SEGMENT_ORDER if s != "Review List"]
    d = flow[flow.from_segment.isin(order_from) & flow.to_segment.isin(order_to)]
    piv = d.pivot_table(index="from_segment", columns="to_segment", values="share_of_from_segment", aggfunc="sum")
    piv = piv.reindex(index=order_from, columns=order_to).fillna(0)
    fig = go.Figure(go.Heatmap(z=100 * piv.values, x=piv.columns, y=piv.index, colorscale=SEQ_SCALE, zmin=0, zmax=100,
                               text=[[f"{v:.0f}" if v >= 1 else "" for v in row] for row in 100 * piv.values], texttemplate="%{text}",
                               textfont=dict(size=10), xgap=2, ygap=2, colorbar=dict(title=dict(text="% of row", side="right"), thickness=10),
                               hovertemplate="From %{y} to %{x}: %{z:.1f}% of the row<extra></extra>"))
    fig.update_layout(xaxis=dict(title="Segment on 2020-09-22", side="top", showline=False, tickangle=-30),
                      yaxis=dict(title="Segment on 2020-06-24", autorange="reversed"), margin=dict(t=170))
    stay = d[(d.from_segment == "Champions") & (d.to_segment == "Champions")].share_of_from_segment.sum()
    slip = d[(d.from_segment == "Champions") & (d.to_segment == "Slipping Regulars")].share_of_from_segment.sum()
    return _finish(fig, f"Segments move fast: in one quarter only {100 * stay:.0f}% of Champions stayed Champions and {100 * slip:.0f}% slipped",
                   "Each row = customers in a segment on 2020-06-24; cells = % of them in each segment on 2020-09-22", 600)


def scenario_bars(scen: pd.DataFrame) -> go.Figure:
    order = ["Pessimistic", "Base", "Optimistic"]
    fig = go.Figure()
    for role, color in (("Rollout", BLUE), ("Test cell", ORANGE)):
        s = scen[scen.role == role].set_index("scenario").reindex(order)
        fig.add_bar(x=order, y=s["net_profit_cu"] / 1e3, name=f"{role} arms", marker_color=color,
                    text=[(f"{v / 1e3:+.1f}K" if abs(v) < 10_000 else f"{v / 1e3:+.0f}K") for v in s["net_profit_cu"]],
                    textposition="outside", cliponaxis=False, textfont=dict(size=11, color=INK2),
                    customdata=np.stack([s["total_cost_cu"] / 1e3, s["incremental_revenue_cu"] / 1e3], axis=-1),
                    hovertemplate="%{x}<br>net %{y:+.1f}K CU<br>cost %{customdata[0]:.1f}K<br>incremental revenue %{customdata[1]:.0f}K<extra></extra>")
    fig.add_hline(y=0, line_width=1, line_color=INK2)
    fig.update_layout(barmode="group", yaxis=dict(title="Expected 90-day net profit (thousand CU)"), xaxis=dict(title=None))
    r = scen[scen.role == "Rollout"].set_index("scenario")["net_profit_cu"]
    k = lambda v: f"{v / 1e3:+.1f}K" if abs(v) < 10_000 else f"{v / 1e3:+.0f}K"  # noqa: E731
    return _finish(fig, f"The content-led rollout stays at or above break-even in all three scenarios ({k(r['Pessimistic'])} to {k(r['Optimistic'])} CU)",
                   "Pessimistic: half the assumed lifts, 30% margin, paid social 0.60 CU; Optimistic: 1.5x lifts, 50% margin, average-buyer value", 400)


# ============================================================================= static export
_SERVER_STARTED = False


def start_static_export() -> None:
    """Start one persistent headless browser for PNG export (much faster and more stable than one per figure)."""
    global _SERVER_STARTED
    if not _SERVER_STARTED:
        import kaleido

        kaleido.start_sync_server(silence_warnings=True)
        _SERVER_STARTED = True


def stop_static_export() -> None:
    global _SERVER_STARTED
    if _SERVER_STARTED:
        import kaleido

        try:
            kaleido.stop_sync_server(silence_warnings=True)
        finally:
            _SERVER_STARTED = False
