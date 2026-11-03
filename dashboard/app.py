"""RFM segmentation & autumn campaign - demo app.

    streamlit run dashboard/app.py

Pages follow the story of the analysis, in the order they are presented. Every page reads
pre-computed Parquet files written by `python run.py`; nothing is recomputed from raw data.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(page_title="RFM Segmentation | Autumn Campaign", page_icon=":material/groups:", layout="wide")

PAGES = [
    st.Page("views/p1_overview.py", title="Overview", icon=":material/dashboard:", url_path="overview", default=True),
    st.Page("views/p2_data_checks.py", title="Data & Sanity Checks", icon=":material/fact_check:", url_path="data-checks"),
    st.Page("views/p3_rfm_scoring.py", title="RFM Scoring", icon=":material/tune:", url_path="rfm-scoring"),
    st.Page("views/p4_segments.py", title="Segments Overview", icon=":material/donut_small:", url_path="segments"),
    st.Page("views/p5_drilldown.py", title="Segment Drill-down", icon=":material/search:", url_path="drill-down"),
    st.Page("views/p6_at_risk.py", title="At-risk Revenue", icon=":material/trending_down:", url_path="at-risk"),
    st.Page("views/p7_campaign.py", title="Campaign Plan & Measurement", icon=":material/campaign:", url_path="campaign"),
    st.Page("views/p8_cohorts.py", title="Appendix: Cohorts & LTV", icon=":material/stacked_line_chart:", url_path="cohorts"),
]

st.navigation(PAGES).run()
