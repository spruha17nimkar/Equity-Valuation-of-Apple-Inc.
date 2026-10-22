import numpy as np
import pandas as pd
import pytest

from aaplval.capital_allocation import accretion_at, buyback_accretion
from aaplval.comps import eps_growth
from aaplval.config import load_assumptions
from aaplval.data import Statements, price_on
from aaplval.financials import historicals
from aaplval.wacc import compute_wacc, regression_beta


def test_packaged_assumptions_are_valid():
    a = load_assumptions()
    assert len(a["forecast"]["revenue_growth"]) == len(a["valuation"]["forecast_years"])


def test_capm_and_wacc():
    w = compute_wacc(risk_free=0.04, beta=1.2, erp=0.05, pre_tax_kd=0.05, tax_rate=0.2, equity_value=900, debt_value=100)
    assert w.cost_of_equity == pytest.approx(0.10)
    assert w.after_tax_cost_of_debt == pytest.approx(0.04)
    assert w.wacc == pytest.approx(0.9 * 0.10 + 0.1 * 0.04)


def test_regression_beta_recovers_true_beta():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", "2024-12-31")
    mkt_r = rng.normal(0.0004, 0.01, len(idx))
    stock_r = 1.3 * mkt_r + rng.normal(0, 0.004, len(idx))
    mkt = pd.Series(100 * np.cumprod(1 + mkt_r), index=idx)
    stock = pd.Series(100 * np.cumprod(1 + stock_r), index=idx)
    b = regression_beta(stock, mkt, pd.Timestamp("2024-12-31"), years=2)
    assert b.raw == pytest.approx(1.3, abs=0.1)
    assert b.adjusted == pytest.approx(0.67 * b.raw + 0.33)
    assert 100 <= b.n_obs <= 106


def test_eps_growth_skips_negative_base():
    assert eps_growth(pd.Series([-0.27, 2.90, 5.53]))[1] == 1
    g, years = eps_growth(pd.Series([4.0, 5.0, 6.25]))
    assert years == 2 and g == pytest.approx(0.25)


def test_buybacks_accrete_only_below_intrinsic_value():
    assert accretion_at(100, 80, 10, 100) > 0
    assert accretion_at(100, 100, 10, 100) == pytest.approx(0)
    assert accretion_at(100, 125, 10, 100) < 0
    table = buyback_accretion(100, 124, 10, 100)
    assert table["is_market_price"].sum() == 1


def test_price_on_uses_last_trading_day():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2025-05-15", "2025-05-16"]))
    assert price_on(s, pd.Timestamp("2025-05-18")) == (2.0, pd.Timestamp("2025-05-16"))


def _statements():
    idx = pd.to_datetime(["2023-09-30", "2024-09-30", "2025-09-30"])
    income = pd.DataFrame({"Total Revenue": [100, 110, 121], "Gross Profit": [40, 45, 50], "EBIT": [30, 33, 36],
                           "Tax Provision": [5, 5, 6], "Pretax Income": [30, 33, 36], "Net Income": [25, 28, 30],
                           "Diluted EPS": [2.5, 2.9, 3.2], "Diluted Average Shares": [10, 9.7, 9.4]}, index=idx)
    cash = pd.DataFrame({"Operating Cash Flow": [32, 35, 38], "Capital Expenditure": [-3, -3, -4],
                         "Reconciled Depreciation": [2, 2, 2]}, index=idx)
    bal = pd.DataFrame({"Total Debt": [50, 50, 50], "Cash Cash Equivalents And Short Term Investments": [20, 25, 30],
                        "Ordinary Shares Number": [10, 9.7, 9.4]}, index=idx)
    return Statements("TEST", income, cash, bal)


def test_as_of_drops_unreported_years():
    st = _statements().as_of(pd.Timestamp("2025-10-15"), lag_days=45)
    assert list(historicals(st).index) == [2023, 2024]


def test_historicals_tolerate_missing_fields():
    h = historicals(_statements())
    assert h["da"].isna().all()          # no D&A field in any fallback -> NaN, not an error
    assert h.loc[2024, "free_cash_flow"] == 32
    assert h.loc[2024, "net_cash"] == -25
