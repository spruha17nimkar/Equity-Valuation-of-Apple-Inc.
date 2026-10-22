"""Cost of capital: regression beta, CAPM cost of equity, after-tax cost of debt and market-value WACC."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class BetaEstimate:
    raw: float
    adjusted: float          # Blume: 0.67 * raw + 0.33 * 1 (the Bloomberg "adjusted beta" convention)
    r_squared: float
    std_error: float
    n_obs: int
    start: str
    end: str
    frequency: str = "weekly"


def regression_beta(stock: pd.Series, market: pd.Series, end: pd.Timestamp, years: int = 2) -> BetaEstimate:
    """OLS beta of weekly (Friday-to-Friday) total returns over ``years`` ending on ``end``."""
    start = end - pd.DateOffset(years=years)
    px = pd.concat([stock, market], axis=1).loc[start:end].dropna()
    weekly = px.resample("W-FRI").last().pct_change().dropna()
    y, x = weekly.iloc[:, 0].to_numpy(), weekly.iloc[:, 1].to_numpy()
    cov = np.cov(y, x, ddof=1)
    raw = cov[0, 1] / cov[1, 1]
    alpha = y.mean() - raw * x.mean()
    resid = y - alpha - raw * x
    n = len(y)
    se = np.sqrt(resid.var(ddof=2) / ((x - x.mean()) ** 2).sum())
    r2 = 1 - resid.var() / y.var()
    return BetaEstimate(float(raw), float(0.67 * raw + 0.33), float(r2), float(se), n,
                        str(weekly.index[0].date()), str(weekly.index[-1].date()))


@dataclass
class WACC:
    risk_free: float
    beta: float
    equity_risk_premium: float
    cost_of_equity: float
    pre_tax_cost_of_debt: float
    tax_rate: float
    after_tax_cost_of_debt: float
    equity_value: float
    debt_value: float
    weight_equity: float
    weight_debt: float
    wacc: float

    def to_dict(self) -> dict:
        return asdict(self)


def compute_wacc(risk_free: float, beta: float, erp: float, pre_tax_kd: float, tax_rate: float,
                 equity_value: float, debt_value: float) -> WACC:
    ke = risk_free + beta * erp
    kd = pre_tax_kd * (1 - tax_rate)
    v = equity_value + debt_value
    we, wd = equity_value / v, debt_value / v
    return WACC(risk_free, beta, erp, ke, pre_tax_kd, tax_rate, kd, equity_value, debt_value, we, wd, we * ke + wd * kd)
