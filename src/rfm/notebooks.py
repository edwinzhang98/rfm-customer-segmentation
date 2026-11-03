"""Execute the analysis notebooks in place and export them to reports/*.html (`python run.py --steps notebooks`)."""

from __future__ import annotations

import time
from typing import Callable

import nbformat
from nbconvert import HTMLExporter
from nbconvert.preprocessors import ExecutePreprocessor

from .config import ROOT

NOTEBOOKS = [
    "01_cleaning.ipynb",
    "02_rfm.ipynb",
    "03_segments_and_actions.ipynb",
    "04_cohort.ipynb",
]


def execute_and_export(log: Callable[[str], None] = print, timings: dict | None = None, timeout: int = 1200) -> None:
    timings = {} if timings is None else timings
    nb_dir, out_dir = ROOT / "notebooks", ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    exporter = HTMLExporter(template_name="lab")
    for name in NOTEBOOKS:
        path = nb_dir / name
        t0 = time.perf_counter()
        nb = nbformat.read(path, as_version=4)
        ExecutePreprocessor(timeout=timeout, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(nb_dir)}})
        nbformat.write(nb, path)
        body, _ = exporter.from_notebook_node(nb)
        (out_dir / name.replace(".ipynb", ".html")).write_text(body)
        timings[f"notebook:{name}"] = round(time.perf_counter() - t0, 2)
        log(f"  {name:<32} executed + exported in {timings[f'notebook:{name}']:.1f} s")
