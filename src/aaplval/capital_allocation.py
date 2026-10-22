"""How Apple turns operating cash flow into shareholder value: buybacks, dividends and excess cash."""

from __future__ import annotations

import pandas as pd


def history(h: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=h.index)
    out["operating_cash_flow"] = h["operating_cash_flow"]
    out["capex"] = h["capex"]
    out["free_cash_flow"] = h["free_cash_flow"]
    out["buybacks"] = h["buybacks"]
    out["dividends"] = h["dividends"]
    out["shareholder_returns"] = h["buybacks"] + h["dividends"]
    out["payout_pct_fcf"] = out["shareholder_returns"] / h["free_cash_flow"]
    out["sbc"] = h["sbc"]
    out["buybacks_net_of_sbc"] = h["buybacks"] - h["sbc"]
    out["net_cash"] = h["net_cash"]
    out["shares_outstanding"] = h["shares_outstanding"]
    out["share_count_change"] = h["shares_outstanding"].pct_change()
    retired = -h["shares_outstanding"].diff()
    out["implied_net_repurchase_price"] = h["buybacks"] / retired.where(retired > 0)
    out["eps_growth"] = h["diluted_eps"].pct_change()
    out["net_income_growth"] = h["net_income"].pct_change()
    out["eps_growth_from_share_count"] = (1 + out["eps_growth"]) / (1 + out["net_income_growth"]) - 1
    return out


def buyback_accretion(intrinsic: float, price: float, annual_buyback: float, shares: float, years: int = 5) -> pd.DataFrame:
    """Intrinsic value per share for continuing holders when ``annual_buyback`` dollars a year are spent
    buying stock at ``price`` relative to ``intrinsic``. Holding the operating business fixed, each dollar
    spent removes a dollar of value and price-adjusted shares; buying below intrinsic value is accretive."""
    ratios = sorted({0.8, 0.9, 1.0, 1.1, 1.2, round(price / intrinsic, 3)})
    rows = []
    for ratio in ratios:
        change = accretion_at(intrinsic, intrinsic * ratio, annual_buyback, shares, years)
        rows.append({"price_to_intrinsic": ratio, "value_per_share_after": intrinsic * (1 + change),
                     "change_vs_no_buyback": change, "is_market_price": ratio == round(price / intrinsic, 3)})
    return pd.DataFrame(rows).set_index("price_to_intrinsic")


def accretion_at(intrinsic: float, price: float, annual_buyback: float, shares: float, years: int = 5) -> float:
    """Fractional change in intrinsic value per share after ``years`` of buying back at ``price``."""
    n, v = shares, intrinsic * shares
    for _ in range(years):
        v -= annual_buyback
        n -= annual_buyback / price
    return v / n / intrinsic - 1
