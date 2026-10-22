"""Market and financial-statement data from Yahoo Finance, cached on disk, with as-of-date filtering
so the valuation only uses information that was public on the valuation date."""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

CACHE_DIR = Path("data")


@dataclass
class Statements:
    ticker: str
    income: pd.DataFrame     # rows = fiscal years (index = period end), columns = line items
    cashflow: pd.DataFrame
    balance: pd.DataFrame

    def as_of(self, date: pd.Timestamp, lag_days: int) -> "Statements":
        """Keep only fiscal years whose results were public on ``date``."""
        cutoff = date - pd.Timedelta(days=lag_days)
        keep = lambda df: df[df.index <= cutoff]  # noqa: E731
        return Statements(self.ticker, keep(self.income), keep(self.cashflow), keep(self.balance))

    def last_year(self) -> pd.Timestamp:
        return self.income.index.max()


def _cached(name: str, fetch, refresh: bool):
    path = CACHE_DIR / f"{name}.pkl"
    if path.exists() and not refresh:
        return pickle.loads(path.read_bytes())
    obj = fetch()
    CACHE_DIR.mkdir(exist_ok=True)
    path.write_bytes(pickle.dumps(obj))
    return obj


def _tidy(df: pd.DataFrame) -> pd.DataFrame:
    out = df.T.sort_index()
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out.index.name = "fiscal_year_end"
    return out.apply(pd.to_numeric, errors="coerce")


def load_statements(ticker: str, refresh: bool = False) -> Statements:
    def fetch():
        import yfinance as yf

        t = yf.Ticker(ticker)
        return Statements(ticker, _tidy(t.income_stmt), _tidy(t.cashflow), _tidy(t.balance_sheet))

    return _cached(f"statements_{ticker}", fetch, refresh)


def load_prices(tickers: list[str], start: str, end: str, refresh: bool = False) -> pd.DataFrame:
    """Daily closes. Equity prices are split-adjusted but not dividend-adjusted, as quoted on the day."""

    def fetch():
        import yfinance as yf

        df = yf.download(tickers, start=start, end=end, auto_adjust=False, progress=False)
        close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]]
        close.index = pd.to_datetime(close.index).tz_localize(None)
        return close

    key = "_".join(sorted(t.replace("^", "") for t in tickers))
    return _cached(f"prices_{key}_{start}_{end}", fetch, refresh)


def load_total_return_prices(tickers: list[str], start: str, end: str, refresh: bool = False) -> pd.DataFrame:
    """Dividend-adjusted closes, for return regressions."""

    def fetch():
        import yfinance as yf

        df = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)["Close"]
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df

    key = "_".join(sorted(t.replace("^", "") for t in tickers))
    return _cached(f"tr_{key}_{start}_{end}", fetch, refresh)


def price_on(prices: pd.Series, date: pd.Timestamp) -> tuple[float, pd.Timestamp]:
    """Close on ``date`` or the last trading day before it."""
    s = prices.dropna()
    s = s[s.index <= date]
    return float(s.iloc[-1]), s.index[-1]


def dividends_between(ticker: str, start: pd.Timestamp, end: pd.Timestamp, refresh: bool = False) -> float:
    def fetch():
        import yfinance as yf

        d = yf.Ticker(ticker).dividends
        d.index = pd.to_datetime(d.index).tz_localize(None)
        return d

    divs = _cached(f"dividends_{ticker}", fetch, refresh)
    return float(divs[(divs.index > start) & (divs.index <= end)].sum())
