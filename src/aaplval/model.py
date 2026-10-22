"""Orchestrates the valuation: data -> WACC -> DCF -> scenarios and sensitivities -> comps -> capital allocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from . import capital_allocation as capalloc
from .comps import comps_table, implied_prices
from .data import Statements, dividends_between, load_prices, load_statements, load_total_return_prices, price_on
from .dcf import DCFInputs, DCFResult, grid, value
from .financials import historicals
from .wacc import WACC, BetaEstimate, compute_wacc, regression_beta


@dataclass
class Valuation:
    assumptions: dict
    valuation_date: pd.Timestamp
    price: float
    price_date: pd.Timestamp
    historicals: pd.DataFrame
    beta: BetaEstimate | None
    wacc: WACC
    inputs: DCFInputs
    base: DCFResult
    scenarios: dict[str, DCFResult]
    sensitivity: dict[str, pd.DataFrame]
    tornado: pd.DataFrame
    comps: pd.DataFrame
    comps_implied: pd.DataFrame
    capital_allocation: pd.DataFrame
    buyback_accretion: pd.DataFrame
    hindsight: dict = field(default_factory=dict)

    @property
    def intrinsic_value(self) -> float:
        return self.base.per_share_blended

    @property
    def premium_to_intrinsic(self) -> float:
        return self.price / self.intrinsic_value - 1


def build_inputs(a: dict, base: pd.Series, w: WACC, roll_years: float, dps_since: float) -> DCFInputs:
    f, t, v = a["forecast"], a["terminal"], a["valuation"]
    n = len(v["forecast_years"])
    capex = f["capex_pct_revenue"] if isinstance(f["capex_pct_revenue"], list) else [f["capex_pct_revenue"]] * n
    return DCFInputs(
        base_revenue=float(base["revenue"]),
        years=tuple(v["forecast_years"]),
        revenue_growth=tuple(f["revenue_growth"]),
        ebit_margin=tuple(f["ebit_margin"]),
        cash_tax_rate=f["cash_tax_rate"],
        da_pct_revenue=f["da_pct_revenue"],
        capex_pct_revenue=tuple(capex),
        nwc_pct_incremental_revenue=f["nwc_pct_incremental_revenue"],
        wacc=w.wacc,
        perpetuity_growth=t["perpetuity_growth"],
        exit_ev_ebitda=t["exit_ev_ebitda"],
        perpetuity_weight=t["perpetuity_weight"],
        net_cash=float(base["net_cash"]),
        shares=float(base["shares_outstanding"]),
        cost_of_equity=w.cost_of_equity,
        roll_forward_years=roll_years,
        dividends_per_share_since_base=dps_since,
    )


def scenario_inputs(inp: DCFInputs, s: dict) -> DCFInputs:
    return inp.shifted(revenue_growth=s.get("revenue_growth_shift", 0.0), ebit_margin=s.get("ebit_margin_shift", 0.0),
                       wacc=s.get("wacc_shift", 0.0), perpetuity_growth=s.get("perpetuity_growth", inp.perpetuity_growth),
                       exit_ev_ebitda=s.get("exit_ev_ebitda", inp.exit_ev_ebitda))


def tornado(inp: DCFInputs) -> pd.DataFrame:
    """Swing in blended value per share when one driver moves to a low and a high case."""
    drivers = {
        "WACC (+/-1.0pp)": (inp.shifted(wacc=0.01), inp.shifted(wacc=-0.01)),
        "Terminal growth (+/-0.5pp)": (inp.shifted(perpetuity_growth=inp.perpetuity_growth - 0.005),
                                       inp.shifted(perpetuity_growth=inp.perpetuity_growth + 0.005)),
        "Exit EV/EBITDA (+/-3x)": (inp.shifted(exit_ev_ebitda=inp.exit_ev_ebitda - 3),
                                   inp.shifted(exit_ev_ebitda=inp.exit_ev_ebitda + 3)),
        "Revenue growth (+/-2pp a year)": (inp.shifted(revenue_growth=-0.02), inp.shifted(revenue_growth=0.02)),
        "EBIT margin (+/-2pp)": (inp.shifted(ebit_margin=-0.02), inp.shifted(ebit_margin=0.02)),
        "Capex intensity (+/-0.5pp of revenue)": (inp.shifted(capex=0.005), inp.shifted(capex=-0.005)),
        "Cash tax rate (+/-2pp)": (inp.shifted(tax=0.02), inp.shifted(tax=-0.02)),
    }
    base = value(inp).per_share_blended
    rows = []
    for name, (lo, hi) in drivers.items():
        lo_v, hi_v = value(lo).per_share_blended, value(hi).per_share_blended
        rows.append({"driver": name, "low": lo_v, "high": hi_v, "swing": abs(hi_v - lo_v),
                     "swing_pct_of_base": abs(hi_v - lo_v) / base})
    return pd.DataFrame(rows).sort_values("swing", ascending=False).set_index("driver")


def sensitivities(inp: DCFInputs, s: dict) -> dict[str, pd.DataFrame]:
    waccs = [round(inp.wacc + d, 4) for d in s["wacc_steps"]]
    return {
        "wacc_x_growth": grid(inp, {"wacc": waccs}, {"perpetuity_growth": s["perpetuity_growth"]}, "per_share_perpetuity",
                              lambda i, w, g: i.shifted(wacc=w - i.wacc, perpetuity_growth=g)),
        "wacc_x_exit": grid(inp, {"wacc": waccs}, {"exit_ev_ebitda": s["exit_ev_ebitda"]}, "per_share_exit",
                            lambda i, w, m: i.shifted(wacc=w - i.wacc, exit_ev_ebitda=m)),
        "growth_x_margin": grid(inp, {"revenue_growth_shift": s["revenue_growth_shift"]},
                                {"ebit_margin_shift": s["ebit_margin_shift"]}, "per_share_blended",
                                lambda i, g, m: i.shifted(revenue_growth=g, ebit_margin=m)),
    }


def run(a: dict, refresh: bool = False) -> Valuation:
    v, m = a["valuation"], a["market"]
    ticker = v["ticker"]
    vdate = pd.Timestamp(v["valuation_date"])
    lag = v["reporting_lag_days"]
    peers = a["comps"]["peers"]
    today = date.today().isoformat()

    stmts: dict[str, Statements] = {t: load_statements(t, refresh) for t in [ticker, *peers]}
    full = historicals(stmts[ticker])
    asof_st = stmts[ticker].as_of(vdate, lag)
    hist = historicals(asof_st)
    if hist.index[-1] != v["base_fiscal_year"]:
        raise ValueError(f"last fiscal year public on {vdate.date()} is {hist.index[-1]}, config says {v['base_fiscal_year']}")
    base = hist.iloc[-1]
    base_fye = asof_st.last_year()

    start = (vdate - pd.DateOffset(years=m["beta_lookback_years"] + 1)).date().isoformat()
    prices = load_prices([ticker, *peers, "^TNX", m["market_index"]], start, today, refresh)
    price, price_date = price_on(prices[ticker], vdate)

    rf = price_on(prices["^TNX"], vdate)[0] / 100 if m["risk_free"] == "auto" else float(m["risk_free"])
    beta_est = None
    if m["beta"] == "auto":
        tr = load_total_return_prices([ticker, m["market_index"]], start, today, refresh)
        beta_est = regression_beta(tr[ticker], tr[m["market_index"]], vdate, m["beta_lookback_years"])
        beta = beta_est.adjusted
    else:
        beta = float(m["beta"])

    w = compute_wacc(rf, beta, m["equity_risk_premium"], rf + m["pre_tax_cost_of_debt_spread"], m["marginal_tax_rate"],
                     equity_value=price * base["shares_outstanding"], debt_value=base["total_debt"])

    roll_years = (vdate - base_fye).days / 365.25
    dps = dividends_between(ticker, base_fye, vdate, refresh)
    inp = build_inputs(a, base, w, roll_years, dps)
    result = value(inp)
    scenarios = {"bear": value(scenario_inputs(inp, a["scenarios"]["bear"])), "base": result,
                 "bull": value(scenario_inputs(inp, a["scenarios"]["bull"]))}

    adj = {ticker: a["adjustments"]["aapl_fy2024_one_off_tax_charge"] / base["diluted_shares"]} if v["base_fiscal_year"] == 2024 else {}
    comps = comps_table(stmts, prices, vdate, lag, adj)
    implied = implied_prices(comps, ticker, net_debt=base["total_debt"] - base["cash_and_st_investments"],
                             shares=base["shares_outstanding"])

    cap = capalloc.history(hist)
    annual_buyback = float(hist["buybacks"].tail(3).mean())
    accretion = capalloc.buyback_accretion(result.per_share_blended, price, annual_buyback, base["shares_outstanding"])

    hindsight = hindsight_check(full, result, prices[ticker], v["forecast_years"][0], price)
    return Valuation(a, vdate, price, price_date, hist, beta_est, w, inp, result, scenarios, sensitivities(inp, a["sensitivity"]),
                     tornado(inp), comps, implied, cap, accretion, hindsight)


def hindsight_check(full: pd.DataFrame, result: DCFResult, prices: pd.Series, first_year: int, price: float) -> dict:
    """Compare the first forecast year with what Apple later reported (not used in the valuation)."""
    out: dict = {}
    if first_year in full.index:
        act = full.loc[first_year]
        fc = result.forecast.loc[first_year]
        actual_fcff_proxy = act["free_cash_flow"]
        out["first_year"] = {
            "fiscal_year": first_year,
            "revenue_forecast": fc["revenue"], "revenue_actual": act["revenue"],
            "ebit_margin_forecast": fc["ebit_margin"], "ebit_margin_actual": act["ebit_margin"],
            "fcff_forecast": fc["fcff"], "reported_fcf_actual": actual_fcff_proxy,
        }
    last = prices.dropna()
    out["latest_price"] = float(last.iloc[-1])
    out["latest_price_date"] = str(last.index[-1].date())
    out["return_since_valuation"] = float(last.iloc[-1] / price - 1)
    return out
