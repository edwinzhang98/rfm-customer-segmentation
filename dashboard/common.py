"""Shared layout pieces and cached data access for every page of the demo app."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from rfm import data as D
from rfm.segments import SEGMENT_ORDER

PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}

CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px;}
h1, h2, h3 {letter-spacing: -0.01em;}
.page-question {font-size: 1.05rem; color: #52514e; border-left: 3px solid #2a78d6;
                padding: 0.35rem 0 0.35rem 0.8rem; margin: -0.4rem 0 1.2rem 0;}
.page-question b {color: #0b0b0b;}
.callout {background: #f3f2ee; border-radius: 6px; padding: 0.9rem 1.1rem; margin: 0.4rem 0 1rem 0; color: #0b0b0b;}
.small-note {color: #898781; font-size: 0.85rem;}
div[data-testid="stMetricValue"] {font-size: 1.7rem;}
div[data-testid="stMetricLabel"] p {color: #52514e;}
div[data-testid="stExpander"] details summary p {font-weight: 600;}
</style>
"""


def page_header(title: str, question: str) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="page-question"><b>Question this page answers:</b> {question}</div>',
                unsafe_allow_html=True)


def how_to_read(markdown_text: str) -> None:
    st.divider()
    with st.expander("How to read this", expanded=False, icon=":material/help:"):
        st.markdown(markdown_text)


def callout(text: str) -> None:
    st.markdown(f'<div class="callout">{text}</div>', unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<div class="small-note">{text}</div>', unsafe_allow_html=True)


def chart(fig, table: pd.DataFrame | None = None, key: str | None = None, table_label: str = "Data behind this chart") -> None:
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key=key)
    if table is not None:
        with st.expander(table_label, expanded=False):
            st.dataframe(table, hide_index=True, width="stretch")


# ----------------------------------------------------------------------------- cached data
@st.cache_data(show_spinner=False)
def mart(name: str) -> pd.DataFrame:
    return D.mart(name)


@st.cache_data(show_spinner=False)
def metrics() -> dict:
    return D.metrics()


@st.cache_data(show_spinner="Loading 1.36M customers ...")
def customers() -> pd.DataFrame:
    """Slim id-free customer table at 2020-09-22 (for interactive re-segmentation)."""
    return D.mart("app_customers")


@st.cache_data(show_spinner="Loading backtest outcomes ...")
def backtest() -> pd.DataFrame:
    return D.mart("app_backtest")


def segment_select(label: str = "Segment", default: str = "At Risk", key: str | None = None,
                   include_excluded: bool = False) -> str:
    options = [s for s in SEGMENT_ORDER if include_excluded or s != "Review List"]
    return st.selectbox(label, options, index=options.index(default), key=key)


fmt_cu, fmt_n, pct = D.fmt_cu, D.fmt_n, D.pct
