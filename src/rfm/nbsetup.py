"""One-line setup for the analysis notebooks.

    from rfm import nbsetup
    nbsetup.init()

Charts are shown as static PNG images (rendered from the same Plotly figures as the dashboard), so the
notebooks display on GitHub and in the exported HTML without any JavaScript.
"""

from __future__ import annotations

import warnings

import pandas as pd
import plotly.io as pio

from . import charts


def init(width: int = 1000) -> None:
    warnings.filterwarnings("ignore", message="The kopts argument is ignored")
    pio.renderers.default = "png"
    pio.renderers["png"].width = width
    pio.renderers["png"].scale = 1.2
    charts.start_static_export()
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda v: f"{v:,.3f}")


def done() -> None:
    charts.stop_static_export()
