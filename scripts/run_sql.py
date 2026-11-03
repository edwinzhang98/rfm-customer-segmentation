"""Run one SQL file with the parameters from config.yaml and print its last result.

Usage (from the repo root):
    python scripts/run_sql.py sql/05_customer_rfm.sql
"""

import sys

from rfm.sqlrun import run_sql_file


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    frame, seconds = run_sql_file(sys.argv[1])
    if frame is not None:
        print(frame.to_string(index=False))
    print(f"\n{sys.argv[1]} finished in {seconds:.1f} s")


if __name__ == "__main__":
    main()
