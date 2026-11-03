"""Read the pipeline outputs (Parquet marts + metrics.json). No computation here.

The dashboard wraps these readers in st.cache_data; the report and notebooks call them directly.
"""

from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from .config import get_paths
from .segments import SEGMENT_ORDER


def mart(name: str, columns: list[str] | None = None, filters=None) -> pd.DataFrame:
    path = get_paths().marts / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `python run.py` first")
    return pd.read_parquet(path, columns=columns, filters=filters)


def ordered(df: pd.DataFrame, col: str = "segment") -> pd.DataFrame:
    """Sort rows by the fixed segment order (Champions first, Review List last)."""
    out = df.copy()
    out[col] = pd.Categorical(out[col].astype(str), SEGMENT_ORDER, ordered=True)
    return out.sort_values(col).reset_index(drop=True)


@lru_cache(maxsize=1)
def metrics() -> dict:
    return json.loads((get_paths().reports / "metrics.json").read_text())


def fmt_cu(value: float, digits: int = 1) -> str:
    """Compact money in CU: 2,059,624 -> '2.1M CU'."""
    v = float(value)
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"{v / div:.{digits}f}{suffix} CU"
    return f"{v:,.0f} CU"


def fmt_n(value: float, digits: int = 1) -> str:
    """Compact count: 190,320 -> '190.3K'."""
    v = float(value)
    for div, suffix in ((1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"{v / div:.{digits}f}{suffix}"
    return f"{v:,.0f}"


def pct(value: float, digits: int = 1) -> str:
    return f"{100 * float(value):.{digits}f}%"
