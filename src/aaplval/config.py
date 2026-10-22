"""Load and validate the assumptions file."""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path
from typing import Any


def load_assumptions(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        raw = tomllib.loads(resources.files("aaplval").joinpath("assumptions.toml").read_text())
    else:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    validate(raw)
    return raw


def validate(a: dict[str, Any]) -> None:
    n = len(a["valuation"]["forecast_years"])
    f = a["forecast"]
    for key in ("revenue_growth", "ebit_margin"):
        if len(f[key]) != n:
            raise ValueError(f"forecast.{key} needs {n} values, one per forecast year")
    if isinstance(f["capex_pct_revenue"], list) and len(f["capex_pct_revenue"]) != n:
        raise ValueError(f"forecast.capex_pct_revenue needs {n} values")
    if not 0 <= a["terminal"]["perpetuity_weight"] <= 1:
        raise ValueError("terminal.perpetuity_weight must be between 0 and 1")
    if a["terminal"]["perpetuity_growth"] >= 0.06:
        raise ValueError("terminal.perpetuity_growth above 6% exceeds long-run nominal GDP growth")
