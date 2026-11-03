"""Configuration and paths.

Everything that can change between runs lives in ``config.yaml`` at the repo root.
The raw-data folder can also be overridden with ``HM_RAW_DIR`` in a ``.env`` file.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    root: Path
    raw_link: Path      # data/raw -> symlink to the configured raw folder
    staged: Path        # data/staged
    marts: Path         # data/marts
    reports: Path       # reports/
    figures: Path       # reports/figures
    docs: Path          # docs/
    sql: Path           # sql/


@lru_cache(maxsize=1)
def load_config() -> dict:
    """Read config.yaml and apply the optional HM_RAW_DIR override from .env."""
    load_dotenv(ROOT / ".env", override=False)
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    raw_dir = os.environ.get("HM_RAW_DIR") or cfg["data"]["raw_dir"]
    cfg["data"]["raw_dir"] = str(Path(raw_dir).expanduser())
    return cfg


def get_paths(cfg: dict | None = None) -> Paths:
    cfg = cfg or load_config()
    work = ROOT / cfg["data"]["work_dir"]
    return Paths(
        root=ROOT,
        raw_link=work / "raw",
        staged=work / "staged",
        marts=work / "marts",
        reports=ROOT / "reports",
        figures=ROOT / "reports" / "figures",
        docs=ROOT / "docs",
        sql=ROOT / "sql",
    )


def snapshot_dates(cfg: dict | None = None) -> dict[str, dt.date]:
    s = (cfg or load_config())["snapshot"]
    return {
        "current": s["current"],
        "backtest_seasonal": s["backtest_seasonal"],
        "backtest_recent": s["backtest_recent"],
    }


def sql_params(cfg: dict | None = None) -> dict[str, object]:
    """Map config.yaml onto the variable names the SQL files read with getvariable()."""
    cfg = cfg or load_config()
    s, t, e = cfg["snapshot"], cfg["rfm_thresholds"], cfg["exclusion"]
    return {
        "price_scale": cfg["money"]["price_scale"],
        "snapshot_current": s["current"],
        "snapshot_seasonal": s["backtest_seasonal"],
        "snapshot_recent": s["backtest_recent"],
        "lookback_days": s["lookback_days"],
        "outcome_days": s["outcome_days"],
        "r5_max_days": t["r5_max_days"],
        "r4_max_days": t["r4_max_days"],
        "r3_max_days": t["r3_max_days"],
        "r2_max_days": t["r2_max_days"],
        "f5_min_orders": t["f5_min_orders"],
        "f4_min_orders": t["f4_min_orders"],
        "f3_min_orders": t["f3_min_orders"],
        "f2_min_orders": t["f2_min_orders"],
        "m5_min_cu": t["m5_min_cu"],
        "m4_min_cu": t["m4_min_cu"],
        "m3_min_cu": t["m3_min_cu"],
        "m2_min_cu": t["m2_min_cu"],
        "new_customer_days": t["new_customer_days"],
        "vip_min_cu": t["vip_min_cu"],
        "excl_units_same_article": e["units_same_article_per_order"],
        "excl_units_per_order": e["units_per_order"],
        "excl_purchase_days": e["purchase_days_2y"],
    }
