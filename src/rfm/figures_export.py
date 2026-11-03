"""Static PNG copies of the key charts (README, docs, one-page action plan).

Interactive versions of the same figures live in the dashboard and in reports/report.html.
"""

from __future__ import annotations

from typing import Callable

from . import charts as C
from . import data as D
from .config import get_paths

# file name -> figure builder; the README and docs reference these names
FIGURES: dict[str, Callable] = {
    "segment_share": lambda: C.segment_share(D.mart("segment_profile")),
    "value_grid": lambda: C.value_grid(D.mart("value_grid")),
    "segment_outcomes": lambda: C.segment_outcomes(D.mart("segment_outcomes_90d")),
    "run_rate_vs_expected": lambda: C.run_rate_vs_expected(D.mart("revenue_at_risk")),
    "net_profit_by_arm": lambda: C.net_profit_by_arm(D.mart("campaign_economics")),
    "breakeven_vs_assumed": lambda: C.breakeven_vs_assumed(D.mart("campaign_economics")),
    "scenario_bars": lambda: C.scenario_bars(D.mart("campaign_scenarios")),
    "weekly_channel": lambda: C.weekly_channel(D.mart("weekly_channel_trend")),
    "price_points": lambda: C.price_points(D.mart("price_points")),
    "return_curve": lambda: C.return_curve(D.mart("recency_return_curve")),
    "channel_value": lambda: C.channel_value(D.mart("channel_value")),
    "channel_forward": lambda: C.channel_forward(D.mart("channel_forward")),
    "segment_flow": lambda: C.segment_flow(D.mart("segment_flow")),
    "cohort_heatmap": lambda: C.cohort_heatmap(D.mart("cohort_retention")),
    "order_ladder": lambda: C.order_ladder(D.mart("order_ladder")),
    "kmeans_crosstab": lambda: C.kmeans_crosstab(D.mart("kmeans_crosstab"), D.mart("kmeans_profile")),
}


def export_all(log: Callable[[str], None] = print, width: int = 1100, scale: float = 1.5) -> list[str]:
    out = get_paths().figures
    out.mkdir(parents=True, exist_ok=True)
    C.start_static_export()
    written = []
    try:
        for name, build in FIGURES.items():
            fig = build()
            path = out / f"{name}.png"
            fig.write_image(path, width=width, height=fig.layout.height or 450, scale=scale)
            written.append(path.name)
    finally:
        C.stop_static_export()
    log(f"  wrote {len(written)} PNG files to reports/figures/")
    return written
