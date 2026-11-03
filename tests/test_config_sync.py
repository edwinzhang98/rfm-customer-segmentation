"""Every SQL file carries its parameters as defaults so it can run on its own.
Those defaults must equal config.yaml, otherwise a hand-run file would silently use other thresholds."""

import datetime as dt
import re

import pytest

from rfm.config import ROOT, sql_params

PATTERN = re.compile(r"SET VARIABLE (\w+)\s*=\s*COALESCE\(getvariable\('(\w+)'\),\s*(.+?)\);")


def _parse(default: str):
    default = default.strip()
    if default.startswith("DATE"):
        return dt.date.fromisoformat(default.split("'")[1])
    if default.startswith("'"):
        return default.strip("'")
    return float(default) if "." in default else int(default)


def _defaults():
    for path in sorted((ROOT / "sql").glob("*.sql")):
        for name, inner, default in PATTERN.findall(path.read_text()):
            assert name == inner, f"{path.name}: SET VARIABLE {name} reads getvariable('{inner}')"
            yield path.name, name, _parse(default)


@pytest.mark.parametrize("file,name,default", list(_defaults()))
def test_sql_default_matches_config(file, name, default):
    params = sql_params()
    assert name in params, f"{file}: variable {name} is not set by config.yaml / sql_params()"
    assert params[name] == default, f"{file}: default {name}={default!r} but config.yaml says {params[name]!r}"
