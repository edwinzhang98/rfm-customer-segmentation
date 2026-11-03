# One command for everything:   make all
# Python: uses .venv if it exists (created by `make setup`), otherwise python3 on PATH.
PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: setup all data analysis report docs notebooks test dashboard screenshots clean help

help:
	@echo "make setup        create .venv and install pinned requirements (+ this repo as a package)"
	@echo "make all          raw CSV -> marts -> analysis -> figures -> report -> notebooks -> docs"
	@echo "make data         staging + data quality + marts + reconciliation only"
	@echo "make test         SQL/Python parity + every dashboard page + interactive controls"
	@echo "make dashboard    streamlit run dashboard/app.py"
	@echo "make screenshots  PNG of every dashboard page into docs/images/ (needs Google Chrome)"

setup:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt; \
	else \
		python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -r requirements.txt; \
	fi

all:
	$(PY) run.py

data:
	$(PY) run.py --steps link,stage,dq,marts,reconcile

analysis:
	$(PY) run.py --steps analysis,figures

report:
	$(PY) run.py --steps report

docs:
	$(PY) run.py --steps docs

notebooks:
	$(PY) run.py --steps notebooks

test:
	$(PY) -m pytest -q tests

dashboard:
	$(PY) -m streamlit run dashboard/app.py

screenshots:
	$(PY) scripts/screenshots.py

clean:
	rm -rf data/staged data/marts data/raw
