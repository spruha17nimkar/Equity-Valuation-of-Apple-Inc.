"""Trading comparables on the valuation date: EV/EBITDA, P/E and PEG, using each company's last fiscal
year that was public on that date."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data import Statements, price_on
from .financials import historicals


def eps_growth(eps: pd.Series, max_years: int = 2) -> tuple[float, int]:
    """CAGR of diluted EPS over up to ``max_years`` ending at the last year, from a positive base."""
    eps = eps.dropna()
    for years in range(min(max_years, len(eps) - 1), 0, -1):
        start, end = eps.iloc[-1 - years], eps.iloc[-1]
        if start > 0 and end > 0:
            return (end / start) ** (1 / years) - 1, years
    return np.nan, 0


def comps_row(st: Statements, price: float, eps_adjustment: float = 0.0) -> dict:
    h = historicals(st)
    last = h.iloc[-1]
    eps = h["diluted_eps"].copy()
    eps.iloc[-1] += eps_adjustment
    growth, years = eps_growth(eps)
    shares = last["shares_outstanding"]
    mcap = price * shares
    ev = mcap + last["total_debt"] - last["cash_and_st_investments"]
    pe = price / eps.iloc[-1]
    return {
        "ticker": st.ticker,
        "fiscal_year": int(h.index[-1]),
        "price": price,
        "market_cap": mcap,
        "enterprise_value": ev,
        "ebitda": last["ebitda"],
        "eps": eps.iloc[-1],
        "eps_growth": growth,
        "eps_growth_years": years,
        "ev_ebitda": ev / last["ebitda"],
        "pe": pe,
        "peg": pe / (growth * 100) if growth and growth > 0 else np.nan,
        "ebitda_margin": last["ebitda"] / last["revenue"],
        "revenue_growth": last["revenue_growth"],
    }


def comps_table(statements: dict[str, Statements], prices: pd.DataFrame, date: pd.Timestamp, lag_days: int,
                eps_adjustments: dict[str, float]) -> pd.DataFrame:
    rows = []
    for tk, st in statements.items():
        px, _ = price_on(prices[tk], date)
        rows.append(comps_row(st.as_of(date, lag_days), px, eps_adjustments.get(tk, 0.0)))
    return pd.DataFrame(rows).set_index("ticker")


def implied_prices(table: pd.DataFrame, target: str, net_debt: float, shares: float) -> pd.DataFrame:
    """Apple's price implied by the peer median and the peer range of each multiple."""
    peers = table.drop(index=target)
    t = table.loc[target]
    out = {}
    for m, apply in {
        "ev_ebitda": lambda x: (x * t["ebitda"] - net_debt) / shares,
        "pe": lambda x: x * t["eps"],
    }.items():
        vals = peers[m].dropna()
        out[m] = {"low": apply(vals.min()), "median": apply(vals.median()), "high": apply(vals.max()),
                  "peer_median_multiple": vals.median(), "apple_multiple": t[m]}
    return pd.DataFrame(out).T
