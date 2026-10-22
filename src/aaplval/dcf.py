"""Free Cash Flow to the Firm DCF with two terminal-value methods.

The firm is valued at the end of the base fiscal year (the date of the last audited balance sheet) and
the per-share value is then rolled forward to the valuation date at the cost of equity, net of dividends
paid in between. Cash flows use the mid-year convention; terminal values are discounted from year end.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DCFInputs:
    base_revenue: float
    years: tuple[int, ...]
    revenue_growth: tuple[float, ...]
    ebit_margin: tuple[float, ...]
    cash_tax_rate: float
    da_pct_revenue: float
    capex_pct_revenue: tuple[float, ...]
    nwc_pct_incremental_revenue: float
    wacc: float
    perpetuity_growth: float
    exit_ev_ebitda: float
    perpetuity_weight: float
    net_cash: float             # cash + all marketable securities - total debt, at base year end
    shares: float               # shares outstanding at base year end
    cost_of_equity: float
    roll_forward_years: float   # base year end -> valuation date
    dividends_per_share_since_base: float = 0.0

    def shifted(self, revenue_growth: float = 0.0, ebit_margin: float = 0.0, wacc: float = 0.0,
                capex: float = 0.0, tax: float = 0.0, **overrides) -> "DCFInputs":
        return replace(
            self,
            revenue_growth=tuple(g + revenue_growth for g in self.revenue_growth),
            ebit_margin=tuple(m + ebit_margin for m in self.ebit_margin),
            capex_pct_revenue=tuple(c + capex for c in self.capex_pct_revenue),
            cash_tax_rate=self.cash_tax_rate + tax,
            wacc=self.wacc + wacc,
            **overrides,
        )


@dataclass
class DCFResult:
    forecast: pd.DataFrame
    pv_fcff: float
    tv_perpetuity: float
    tv_exit: float
    pv_tv_perpetuity: float
    pv_tv_exit: float
    ev_perpetuity: float
    ev_exit: float
    per_share_perpetuity: float          # at the valuation date
    per_share_exit: float
    per_share_blended: float
    implied_exit_multiple: float         # EV/EBITDA implied by the perpetuity-growth TV
    implied_perpetuity_growth: float     # growth implied by the exit-multiple TV
    tv_share_of_ev: dict = field(default_factory=dict)


def project(inp: DCFInputs) -> pd.DataFrame:
    rows = []
    prev = inp.base_revenue
    for i, year in enumerate(inp.years):
        rev = prev * (1 + inp.revenue_growth[i])
        ebit = rev * inp.ebit_margin[i]
        da = rev * inp.da_pct_revenue
        capex = rev * inp.capex_pct_revenue[i]
        dnwc = inp.nwc_pct_incremental_revenue * (rev - prev)
        nopat = ebit * (1 - inp.cash_tax_rate)
        fcff = nopat + da - capex - dnwc
        t = i + 0.5
        rows.append({
            "fiscal_year": year, "revenue": rev, "revenue_growth": inp.revenue_growth[i], "ebit": ebit,
            "ebit_margin": inp.ebit_margin[i], "ebitda": ebit + da, "taxes": ebit * inp.cash_tax_rate, "nopat": nopat,
            "da": da, "capex": capex, "delta_nwc": dnwc, "fcff": fcff, "discount_period": t,
            "discount_factor": (1 + inp.wacc) ** -t,
        })
        prev = rev
    df = pd.DataFrame(rows).set_index("fiscal_year")
    df["pv_fcff"] = df["fcff"] * df["discount_factor"]
    return df


def value(inp: DCFInputs) -> DCFResult:
    if inp.wacc <= inp.perpetuity_growth:
        raise ValueError(f"WACC {inp.wacc:.2%} must exceed perpetuity growth {inp.perpetuity_growth:.2%}")
    f = project(inp)
    n = len(f)
    last = f.iloc[-1]
    df_n = (1 + inp.wacc) ** -n

    tv_g = last["fcff"] * (1 + inp.perpetuity_growth) / (inp.wacc - inp.perpetuity_growth)
    tv_x = last["ebitda"] * inp.exit_ev_ebitda
    pv_fcff = float(f["pv_fcff"].sum())
    ev_g = pv_fcff + tv_g * df_n
    ev_x = pv_fcff + tv_x * df_n

    roll = (1 + inp.cost_of_equity) ** inp.roll_forward_years

    def per_share(ev: float) -> float:
        return (ev + inp.net_cash) / inp.shares * roll - inp.dividends_per_share_since_base

    ps_g, ps_x = per_share(ev_g), per_share(ev_x)
    w = inp.perpetuity_weight
    return DCFResult(
        forecast=f,
        pv_fcff=pv_fcff,
        tv_perpetuity=tv_g,
        tv_exit=tv_x,
        pv_tv_perpetuity=tv_g * df_n,
        pv_tv_exit=tv_x * df_n,
        ev_perpetuity=ev_g,
        ev_exit=ev_x,
        per_share_perpetuity=ps_g,
        per_share_exit=ps_x,
        per_share_blended=w * ps_g + (1 - w) * ps_x,
        implied_exit_multiple=tv_g / last["ebitda"],
        implied_perpetuity_growth=(tv_x * inp.wacc - last["fcff"]) / (tv_x + last["fcff"]),
        tv_share_of_ev={"perpetuity": tv_g * df_n / ev_g, "exit": tv_x * df_n / ev_x},
    )


def grid(inp: DCFInputs, rows: dict[str, list], cols: dict[str, list], metric: str, build) -> pd.DataFrame:
    """Evaluate ``metric`` of ``value(build(inp, r, c))`` over a 2-D grid."""
    (rname, rvals), (cname, cvals) = next(iter(rows.items())), next(iter(cols.items()))
    out = np.full((len(rvals), len(cvals)), np.nan)
    for i, r in enumerate(rvals):
        for j, c in enumerate(cvals):
            try:
                out[i, j] = getattr(value(build(inp, r, c)), metric)
            except ValueError:
                pass
    return pd.DataFrame(out, index=pd.Index(rvals, name=rname), columns=pd.Index(cvals, name=cname))
