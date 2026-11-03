"""Mechanical acceptance checks before a release.

    python scripts/acceptance_checks.py                 # all checks
    python scripts/acceptance_checks.py --compare other/reports/metrics.json

1. every SQL file runs on its own, in its own fresh process, in pipeline order
2. (optional) key numbers are identical to another run's metrics.json (timings excluded)
3. no personal absolute paths, secrets or debug leftovers in tracked files
4. every document the brief asks for exists and has no placeholder left
5. segment counts and revenue shares add up to the totals
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_ORDER = ["00_stage_raw.sql", "01_data_quality_checks.sql", "02_fct_sales_lines.sql", "03_fct_orders.sql", "04_dim_customers.sql",
             "05_customer_rfm.sql", "06_customer_outcomes_90d.sql", "07_segment_outcomes_90d.sql", "08_recency_return_curve.sql",
             "09_segment_profile.sql", "10_segment_mix.sql", "11_cohort_retention.sql", "12_weekly_channel_trend.sql",
             "13_reconciliation_checks.sql", "14_segment_flow.sql", "rfm_single_query.sql"]
REQUIRED_DOCS = ["docs/00_plan.md", "docs/01_request_and_scope.md", "docs/02_metric_definitions.md", "docs/03_data_quality_checks.md",
                 "docs/assumptions.md", "docs/readout.md", "docs/segmentation_spec.md", "docs/campaign_plan.md",
                 "docs/measurement_plan.md", "README.md",
                 "reports/report.html", "reports/action_plan.html", "reports/01_cleaning.html", "reports/02_rfm.html",
                 "reports/03_segments_and_actions.html", "reports/04_cohort.html", "dashboard/app.py"]


def check_sql() -> list[str]:
    out = []
    for name in SQL_ORDER:
        t0 = time.perf_counter()
        r = subprocess.run([sys.executable, "scripts/run_sql.py", f"sql/{name}"], cwd=ROOT, capture_output=True, text=True)
        status = "ok" if r.returncode == 0 else "FAILED"
        out.append(f"{status:<6} sql/{name:<34} {time.perf_counter() - t0:6.1f} s")
        if r.returncode:
            out.append(r.stderr[-800:])
    return out


def _strip(d):
    if isinstance(d, dict):
        return {k: _strip(v) for k, v in d.items() if k not in ("timings_s",)}
    return d


def check_compare(other: Path) -> list[str]:
    a = _strip(json.loads((ROOT / "reports" / "metrics.json").read_text()))
    b = _strip(json.loads(other.read_text()))
    if a == b:
        return [f"ok     metrics.json identical to {other} (excluding timings)"]
    diffs = []

    def walk(x, y, path=""):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                walk(x.get(k), y.get(k), f"{path}.{k}")
        elif x != y:
            diffs.append(f"{path}: {x!r} vs {y!r}")

    walk(a, b)
    return [f"FAILED {len(diffs)} differences"] + diffs[:20]


def check_repo_hygiene() -> list[str]:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    paths_secrets = re.compile(r"/Users/[a-z]+/|/home/[a-z]+/|/private/tmp/|api[_-]?key\s*=|secret\s*=|password\s*=", re.I)
    # debug markers only in our own source and docs (generated HTML embeds third-party plotly.js, which has its own TODOs)
    debug = re.compile(r"\bTODO\b|\bFIXME\b|breakpoint\(\)|pdb\.set_trace")
    hits = []
    for f in files:
        p = ROOT / f
        if p.suffix in {".png", ".parquet"} or not p.is_file() or p.stat().st_size > 8_000_000 or "acceptance_checks.py" in f:
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        check_debug = p.suffix in {".py", ".sql", ".md", ".yaml", ".toml", ".ipynb"}
        for i, line in enumerate(text.splitlines(), 1):
            if paths_secrets.search(line) or (check_debug and debug.search(line)):
                hits.append(f"{f}:{i}: {line.strip()[:120]}")
    data = [f for f in files if f.startswith("data/") or f.endswith((".csv", ".parquet", ".duckdb"))]
    out = ["ok     no personal paths, secrets or debug markers in tracked files" if not hits else f"FAILED {len(hits)} hits"] + hits[:20]
    out.append("ok     no data files tracked" if not data else f"FAILED data files tracked: {data[:5]}")
    return out


def check_docs() -> list[str]:
    out = []
    for f in REQUIRED_DOCS:
        p = ROOT / f
        if not p.exists():
            out.append(f"FAILED missing {f}")
            continue
        text = p.read_text(errors="ignore") if p.suffix in {".md", ".py"} else ""
        left = [m for m in ("(generated)", "TBD", "lorem") if m in text]
        out.append(f"{'ok' if not left else 'FAILED':<6} {f}" + (f" contains {left}" if left else ""))
    return out


def check_totals() -> list[str]:
    import pandas as pd

    prof = pd.read_parquet(ROOT / "data" / "marts" / "segment_profile.parquet")
    m = json.loads((ROOT / "reports" / "metrics.json").read_text())["data"]
    ok_c = int(prof.customers.sum()) == m["customers_with_orders"]
    ok_s = abs(prof.pct_customers.sum() - 1) < 1e-9 and abs(prof.pct_revenue_12m.sum() - 1) < 1e-9
    ok_r = abs(prof.revenue_12m_cu.sum() - m["revenue_12m_cu"]) < 1
    return [f"{'ok' if ok_c else 'FAILED':<6} segment customers sum to {prof.customers.sum():,} (= customers with an order)",
            f"{'ok' if ok_s else 'FAILED':<6} customer and revenue shares each sum to 100%",
            f"{'ok' if ok_r else 'FAILED':<6} segment 12-month revenue sums to the 12-month total"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", type=Path, help="metrics.json of another run")
    ap.add_argument("--skip-sql", action="store_true")
    args = ap.parse_args()
    sections = []
    if not args.skip_sql:
        sections.append(("SQL files run on their own", check_sql()))
    if args.compare:
        sections.append(("Two runs give the same numbers", check_compare(args.compare)))
    sections += [("Repo hygiene", check_repo_hygiene()), ("Required documents", check_docs()), ("Totals add up", check_totals())]
    failed = False
    for title, lines in sections:
        print(f"\n## {title}")
        for line in lines:
            print("  " + line)
            failed |= line.startswith("FAILED")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
