"""Every page of the Streamlit app renders without an exception, including after moving the interactive controls."""

import pytest
from streamlit.testing.v1 import AppTest

from rfm.config import ROOT, get_paths

APP = ROOT / "dashboard" / "app.py"

PAGES = [
    "views/p1_overview.py",
    "views/p2_data_checks.py",
    "views/p3_rfm_scoring.py",
    "views/p4_segments.py",
    "views/p5_drilldown.py",
    "views/p6_at_risk.py",
    "views/p7_campaign.py",
    "views/p8_cohorts.py",
]

pytestmark = pytest.mark.skipif(not (get_paths().marts / "app_customers.parquet").exists(), reason="run `python run.py` first")


def _app(page: str) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.run()
    if page != PAGES[0]:
        at.switch_page(page)
        at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    at = _app(page)
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.title) == 1
    assert any("Question this page answers" in md.value for md in at.markdown)
    assert any(e.label == "How to read this" for e in at.expander)


def test_rfm_thresholds_change_segments():
    at = _app("views/p3_rfm_scoring.py")
    at.slider(key="f4").set_value(4).run()
    at.slider(key="lost").set_value(300).run()
    assert not at.exception, [e.value for e in at.exception]


def test_at_risk_audience_recomputes():
    at = _app("views/p6_at_risk.py")
    before = [m.value for m in at.metric]
    at.slider(key="ar_rec").set_value((61, 120)).run()
    at.slider(key="ar_f").set_value(2).run()
    assert not at.exception, [e.value for e in at.exception]
    assert [m.value for m in at.metric] != before


def test_campaign_budget_and_mde_controls():
    at = _app("views/p7_campaign.py")
    at.slider(key="budget").set_value(5000.0).run()
    at.selectbox(key="mde_aud").set_value("new").run()
    at.slider(key="mde_share").set_value(0.2).run()
    at.radio(key="val_basis").set_value("Average 90-day buyer (optimistic)").run()
    assert not at.exception, [e.value for e in at.exception]
