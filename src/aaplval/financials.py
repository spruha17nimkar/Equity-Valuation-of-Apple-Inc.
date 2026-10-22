"""Standardised historical financials from the raw statements."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data import Statements


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    return df[name] if name in df.columns else pd.Series(np.nan, index=df.index)


def historicals(st: Statements) -> pd.DataFrame:
    """One row per fiscal year, in dollars; ratios as fractions."""
    i, c, b = st.income, st.cashflow, st.balance
    h = pd.DataFrame(index=i.index)
    h["revenue"] = _col(i, "Total Revenue")
    h["revenue_growth"] = h["revenue"].pct_change()
    h["gross_margin"] = _col(i, "Gross Profit") / h["revenue"]
    h["ebit"] = _col(i, "EBIT")
    h["ebit_margin"] = h["ebit"] / h["revenue"]
    h["da"] = (_col(c, "Depreciation And Amortization")
               .fillna(_col(c, "Depreciation Amortization Depletion"))
               .fillna(_col(i, "Reconciled Depreciation")))
    h["ebitda"] = h["ebit"] + h["da"]
    h["effective_tax_rate"] = _col(i, "Tax Provision") / _col(i, "Pretax Income")
    h["net_income"] = _col(i, "Net Income")
    h["diluted_eps"] = _col(i, "Diluted EPS")
    h["diluted_shares"] = _col(i, "Diluted Average Shares")
    h["sbc"] = _col(c, "Stock Based Compensation")
    h["operating_cash_flow"] = _col(c, "Operating Cash Flow")
    h["capex"] = -_col(c, "Capital Expenditure")
    h["free_cash_flow"] = h["operating_cash_flow"] - h["capex"]
    h["buybacks"] = -_col(c, "Repurchase Of Capital Stock")
    h["dividends"] = -_col(c, "Cash Dividends Paid")
    h["da_pct_revenue"] = h["da"] / h["revenue"]
    h["capex_pct_revenue"] = h["capex"] / h["revenue"]
    h["fcf_margin"] = h["free_cash_flow"] / h["revenue"]
    b = b.reindex(h.index)
    h["operating_nwc"] = (_col(b, "Accounts Receivable") + _col(b, "Inventory")
                          - _col(b, "Accounts Payable") - _col(b, "Current Deferred Revenue"))
    h["cash_and_st_investments"] = _col(b, "Cash Cash Equivalents And Short Term Investments")
    h["lt_marketable_securities"] = _col(b, "Investmentin Financial Assets").fillna(0)
    h["total_debt"] = _col(b, "Total Debt")
    h["net_cash"] = h["cash_and_st_investments"] + h["lt_marketable_securities"] - h["total_debt"]
    h["shares_outstanding"] = _col(b, "Ordinary Shares Number")
    h.index = h.index.year
    h.index.name = "fiscal_year"
    return h
