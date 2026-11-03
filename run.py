"""One command for the whole pipeline: raw CSV -> clean marts -> analysis -> report.

    python run.py                    # everything (same as `make all`)
    python run.py --steps marts,analysis
    python run.py --list             # show the steps

Each step is idempotent and only reads the outputs of earlier steps, so any step can
be rerun on its own. Timings are written to reports/run_log.json.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

from rfm.config import ROOT, get_paths, load_config
from rfm.sqlrun import connect, run_sql_file

RAW_FILES = ("transactions_train.csv", "customers.csv", "articles.csv")
MART_SQL = (
    "02_fct_sales_lines.sql",
    "03_fct_orders.sql",
    "04_dim_customers.sql",
    "05_customer_rfm.sql",
    "06_customer_outcomes_90d.sql",
    "07_segment_outcomes_90d.sql",
    "08_recency_return_curve.sql",
    "09_segment_profile.sql",
    "10_segment_mix.sql",
    "11_cohort_retention.sql",
    "12_weekly_channel_trend.sql",
    "14_segment_flow.sql",
)


FULL_RUN = False   # set in main(): True when every step runs, in order


def log(message: str) -> None:
    print(message, flush=True)


# --------------------------------------------------------------------------- steps
def step_link(timings: dict) -> None:
    """Point data/raw at the configured raw folder (raw data is never copied)."""
    cfg, paths = load_config(), get_paths()
    raw_dir = Path(cfg["data"]["raw_dir"])
    missing = [f for f in RAW_FILES if not (raw_dir / f).exists()]
    if missing:
        sys.exit(
            f"Raw files not found in {raw_dir}: {missing}\n"
            "Set data.raw_dir in config.yaml or HM_RAW_DIR in .env (see README)."
        )
    paths.raw_link.parent.mkdir(parents=True, exist_ok=True)
    if paths.raw_link.is_symlink() or paths.raw_link.exists():
        paths.raw_link.unlink()
    paths.raw_link.symlink_to(raw_dir, target_is_directory=True)
    for folder in (paths.staged, paths.marts, paths.figures):
        folder.mkdir(parents=True, exist_ok=True)
    log(f"  data/raw -> {raw_dir}")


def _run_sql(name: str, timings: dict, con=None) -> None:
    frame, seconds = run_sql_file(get_paths().sql / name, con=con)
    timings[f"sql/{name}"] = round(seconds, 2)
    log(f"  sql/{name:<34} {seconds:6.1f} s")
    if frame is not None and len(frame) <= 12:
        for line in frame.to_string(index=False).splitlines():
            log(f"      {line}")


def step_stage(timings: dict) -> None:
    """Raw CSV -> typed Parquet (sql/00)."""
    _run_sql("00_stage_raw.sql", timings)


def step_dq(timings: dict) -> None:
    """Data quality checks on the staged data (stops the pipeline on any FAIL)."""
    import pandas as pd

    _run_sql("01_data_quality_checks.sql", timings)
    checks = pd.read_parquet(get_paths().marts / "dq_checks.parquet")
    counts = checks["status"].value_counts().to_dict()
    log(f"  {counts.get('PASS', 0)} PASS, {counts.get('FLAG', 0)} FLAG (known issue, handled), {counts.get('FAIL', 0)} FAIL")
    if counts.get("FAIL", 0):
        sys.exit("Data quality check failed (status FAIL above).")


def step_marts(timings: dict) -> None:
    """Clean facts, customer dim, RFM, backtests, profiles, cohorts (sql/02-12)."""
    con = connect()
    for name in MART_SQL:
        _run_sql(name, timings, con=con)


def step_reconcile(timings: dict) -> None:
    """Totals must match across every table (sql/13); stops the pipeline otherwise."""
    import pandas as pd

    _run_sql("13_reconciliation_checks.sql", timings)
    checks = pd.read_parquet(get_paths().marts / "reconciliation_checks.parquet")
    failed = checks[~checks["passed"]]
    if len(failed):
        log(failed.to_string(index=False))
        sys.exit("Reconciliation failed: totals do not add up across tables (see above).")
    log(f"  all {len(checks)} reconciliation checks passed")


def step_analysis(timings: dict) -> None:
    """K-Means comparison, revenue at risk, campaign economics, holdout power, metrics.json."""
    from rfm import analysis

    analysis.run_all(log=log, timings=timings)


def step_figures(timings: dict) -> None:
    """Static PNG copies of the key charts for README / docs."""
    from rfm import figures_export

    figures_export.export_all(log=log)


def step_report(timings: dict) -> None:
    """reports/report.html (standalone) and reports/action_plan.html."""
    from rfm import report

    report.build_all(log=log)


def step_docs(timings: dict) -> None:
    """Refresh the generated tables inside docs/*.md and README.md."""
    from rfm import docgen

    # in a full run the timings table shows this run; otherwise the last full run in reports/run_log.json
    docgen.update_all(log=log, run_timings=timings if FULL_RUN else None)


def step_notebooks(timings: dict) -> None:
    """Execute notebooks 01-04 in place and export them to reports/*.html."""
    from rfm import notebooks

    notebooks.execute_and_export(log=log, timings=timings)


STEPS = {
    "link": step_link,
    "stage": step_stage,
    "dq": step_dq,
    "marts": step_marts,
    "reconcile": step_reconcile,
    "analysis": step_analysis,
    "figures": step_figures,
    "report": step_report,
    "notebooks": step_notebooks,
    "docs": step_docs,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--steps", default="all", help="comma-separated subset of steps (default: all)")
    parser.add_argument("--list", action="store_true", help="list the steps and exit")
    args = parser.parse_args()

    if args.list:
        for name, func in STEPS.items():
            log(f"{name:<10} {(func.__doc__ or '').strip()}")
        return

    selected = list(STEPS) if args.steps == "all" else [s.strip() for s in args.steps.split(",")]
    unknown = [s for s in selected if s not in STEPS]
    if unknown:
        sys.exit(f"Unknown step(s): {unknown}. Use --list.")

    global FULL_RUN
    FULL_RUN = selected == list(STEPS)
    timings: dict[str, float] = {}
    started = time.perf_counter()
    for name in selected:
        log(f"[{name}]")
        t0 = time.perf_counter()
        STEPS[name](timings)
        timings[f"step:{name}"] = round(time.perf_counter() - t0, 2)
        log(f"  done in {timings[f'step:{name}']:.1f} s")
    total = round(time.perf_counter() - started, 2)
    log(f"Pipeline finished in {total:.1f} s")

    log_path = ROOT / "reports" / "run_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(log_path.read_text()) if log_path.exists() else {}
    previous.setdefault("timings_s", {}).update(timings)
    if FULL_RUN:
        previous["last_full_run"] = {"timings_s": {k: v for k, v in timings.items() if k.startswith("step:")}, "total_s": total}
    previous["last_run"] = {
        "steps": selected,
        "total_s": total,
        "python": platform.python_version(),
        "machine": platform.platform(),
    }
    log_path.write_text(json.dumps(previous, indent=2) + "\n")


if __name__ == "__main__":
    main()
