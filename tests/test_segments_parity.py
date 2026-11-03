"""The Python copy of the segment rules (used by the dashboard) must match the SQL exactly."""

import pandas as pd
import pytest

from rfm.config import get_paths
from rfm.segments import Thresholds, assign_segments, score

RFM = get_paths().marts / "customer_rfm.parquet"


@pytest.mark.skipif(not RFM.exists(), reason="run `python run.py` first")
@pytest.mark.parametrize("snapshot", ["current", "backtest_seasonal", "backtest_recent"])
def test_python_rules_match_sql(snapshot):
    df = pd.read_parquet(RFM, filters=[("snapshot_name", "==", snapshot)])
    th = Thresholds.from_config()
    scores = score(df, th)
    assert (scores["r_score"].to_numpy() == df["r_score"].to_numpy()).all()
    assert (scores["f_score"].to_numpy() == df["f_score"].to_numpy()).all()
    assert (scores["m_score"].to_numpy() == df["m_score"].to_numpy()).all()
    py_segments = assign_segments(df, th, scores).astype(str).to_numpy()
    mismatches = (py_segments != df["segment"].to_numpy()).sum()
    assert mismatches == 0, f"{mismatches} customers differ between SQL and Python rules"
