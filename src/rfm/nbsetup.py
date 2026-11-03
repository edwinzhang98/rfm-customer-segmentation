"""One-line setup for the analysis notebooks.

    from rfm import nbsetup
    nbsetup.init()

Charts are shown as static PNG images (rendered from the same Plotly figures as the dashboard), so the
notebooks display on GitHub and in the exported HTML without any JavaScript.
"""

from __future__ import annotations

import itertools
import warnings

import pandas as pd
import plotly.io as pio

from . import charts


def _stable_styler_output() -> None:
    """Styled tables get numbered ids and a plain repr instead of a random id and a memory address,
    so re-running a notebook only changes the file when a result changes."""
    from pandas.io.formats.style import Styler

    if getattr(Styler, "_stable_output", False):
        return
    counter = itertools.count(1)
    original_init = Styler.__init__

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if not kwargs.get("uuid"):
            self.uuid = f"t{next(counter):03d}"

    Styler.__init__ = __init__
    Styler.__repr__ = lambda self: f"<styled table: {self.data.shape[0]} rows x {self.data.shape[1]} columns>"
    Styler._stable_output = True


def init(width: int = 1000) -> None:
    warnings.filterwarnings("ignore", message="The kopts argument is ignored")
    _stable_styler_output()
    pio.renderers.default = "png"
    pio.renderers["png"].width = width
    pio.renderers["png"].scale = 1.2
    charts.start_static_export()
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda v: f"{v:,.3f}")


def done() -> None:
    charts.stop_static_export()
