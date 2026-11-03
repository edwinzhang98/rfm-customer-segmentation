"""Run the numbered SQL files with DuckDB.

Every SQL file in ``sql/`` is self-contained: it reads Parquet inputs, writes one
Parquet output and declares its parameters with
``SET VARIABLE x = COALESCE(getvariable('x'), <default>)``.
This runner sets those variables from config.yaml first, so the file defaults only
matter when a file is run by hand.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import time
from pathlib import Path

import duckdb
import pandas as pd

from .config import ROOT, sql_params


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, dt.date):
        return f"DATE '{value.isoformat()}'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise TypeError(f"Unsupported SQL parameter type: {type(value)!r}")


@contextlib.contextmanager
def at_repo_root():
    """SQL files use paths relative to the repo root (data/...)."""
    previous = Path.cwd()
    os.chdir(ROOT)
    try:
        yield
    finally:
        os.chdir(previous)


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def run_sql_file(
    path: str | Path,
    con: duckdb.DuckDBPyConnection | None = None,
    params: dict[str, object] | None = None,
) -> tuple[pd.DataFrame | None, float]:
    """Execute one SQL file; return (result of its last statement, seconds taken)."""
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    con = con or connect()
    params = sql_params() if params is None else params
    with at_repo_root():
        for name, value in params.items():
            con.execute(f"SET VARIABLE {name} = {_literal(value)}")
        started = time.perf_counter()
        result = con.execute(path.read_text())
        seconds = time.perf_counter() - started
        try:
            frame = result.df()
        except (duckdb.InvalidInputException, AttributeError):
            frame = None
    return frame, seconds


def query(sql: str, con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    """Run an ad-hoc query (paths relative to the repo root)."""
    con = con or connect()
    with at_repo_root():
        return con.execute(sql).df()
