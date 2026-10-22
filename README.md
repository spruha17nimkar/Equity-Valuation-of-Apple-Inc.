# Equity Valuation of Apple Inc. (AAPL)

**The question.** In 2025, higher interest rates were compressing mega-cap tech multiples. Does Apple's market
price reflect its long-term ability to generate cash as a mature platform?

**The answer (as of 16 May 2025, price $211.26).** The base-case DCF gives an intrinsic value of
**$170.21 per share**, so the stock traded about **24% above intrinsic value**. To justify the price, the market
needs roughly the bull case: faster growth, higher margins *and* a lower discount rate at the same time.

![Valuation summary](reports/figures/football_field.png)

The full output is in [`reports/valuation_report.md`](reports/valuation_report.md). An Excel workbook with every
table is at [`reports/aapl_valuation.xlsx`](reports/aapl_valuation.xlsx).

## What the model does

| Step | Method | Code |
|---|---|---|
| Historicals | FY2022–FY2024 income statement, cash flow and balance sheet, restricted to what was public on the valuation date | [`financials.py`](src/aaplval/financials.py) |
| Forecast | Bottom-up Free Cash Flow to the Firm for FY2025E–FY2029E (see the note below): revenue growth normalisation, EBIT margin and operating leverage, D&A, capex intensity and working capital | [`dcf.py`](src/aaplval/dcf.py) |
| Cost of capital | Regression beta (2y weekly vs S&P 500, Blume-adjusted), CAPM cost of equity, after-tax cost of debt, market-value weights | [`wacc.py`](src/aaplval/wacc.py) |
| Terminal value | Perpetuity growth (Gordon) **and** exit EV/EBITDA multiple, each cross-checked against the other's implied value | [`dcf.py`](src/aaplval/dcf.py) |
| Scenarios and sensitivity | Bear, base and bull cases; WACC × growth, WACC × exit multiple and revenue growth × margin heatmaps; one-at-a-time tornado | [`model.py`](src/aaplval/model.py) |
| Trading comps | Apple vs Microsoft, Meta, Alphabet and Amazon on EV/EBITDA, P/E and PEG at the valuation-date price | [`comps.py`](src/aaplval/comps.py) |
| Capital allocation | Where operating cash flow goes, the share count, EPS growth from buybacks, and whether buybacks at the market price add or destroy per-share value | [`capital_allocation.py`](src/aaplval/capital_allocation.py) |

Every assumption is in one file, [`assumptions.toml`](src/aaplval/assumptions.toml).

**No look-ahead.** The model uses only data public on 16 May 2025: the FY2024 10-K, and prices and yields on
that day. The firm is valued at the FY2024 year end, which is the last audited balance sheet. The per-share
value is then rolled forward to the valuation date at the cost of equity, less dividends paid in between.
Later results appear only in a separate hindsight check.

**Why the forecast starts at FY2025.** By May 2025, FY2024 (ended September 2024) was already reported, so it
is the base year and the five forecast years are FY2025–FY2029.

## Key results

### Cost of capital

| Input | Value | Source |
|---|---:|---|
| Risk-free rate | 4.44% | 10-year Treasury yield on 16 May 2025 |
| Beta | **1.05** | raw 1.07 from 104 weekly returns vs S&P 500 (May 2023–May 2025), Blume-adjusted |
| Equity risk premium | 4.50% | assumption (implied US ERP was roughly 4–5% in early 2025) |
| Cost of equity | 9.16% | CAPM |
| After-tax cost of debt | 3.98% | (rf + 0.60%) × (1 − 21%) |
| Weights | 96.8% equity / 3.2% debt | market cap $3.19tn, debt $107bn |
| **WACC** | **8.99%** | |

### DCF

| | Perpetuity growth | Exit multiple | Blended (50/50) |
|---|---:|---:|---:|
| Terminal assumption | g = 3.0% | 20.0x FY2029 EBITDA | |
| Cross-check | implies 13.2x EBITDA | implies g = 4.95% | |
| Terminal value share of EV | 75% | 82% | |
| **Value per share** | **$143.12** | **$197.29** | **$170.21** |

The two methods disagree by about $54, and the gap is itself a finding. A 20x exit multiple implies Apple's cash
flows grow at about 5% a year *forever*. A 3% perpetuity growth rate implies Apple ends up valued at 13x
EBITDA. The market price of $211 sits above even the exit-multiple value.

| Scenario | Avg revenue growth | FY2029 EBIT margin | WACC | g / exit | Value | Price vs value |
|---|---:|---:|---:|---:|---:|---:|
| Bear | 2.5% | 30.4% | 9.49% | 2.5% / 17x | $124.59 | +70% |
| **Base** | **5.0%** | **32.4%** | **8.99%** | **3.0% / 20x** | **$170.21** | **+24%** |
| Bull | 7.0% | 33.9% | 8.49% | 3.5% / 24x | $229.40 | −8% |

### Sensitivity

Ranges tested:
- WACC 7.5%–10.5%
- terminal growth 2.0%–4.0%
- exit multiple 16x–26x
- revenue growth and EBIT margin ±3 percentage points

| WACC × terminal growth | WACC × exit multiple |
|---|---|
| ![](reports/figures/heatmap_wacc_growth.png) | ![](reports/figures/heatmap_wacc_exit.png) |

![Tornado](reports/figures/tornado.png)

**WACC is the single biggest driver.** A ±1 point change moves the value by $32 (19%). Revenue growth (±2 points
a year, $30) and the exit multiple (±3x, $24) come next. The perpetuity method only reaches $211 with a WACC near
7.5% *and* 3.5% terminal growth.

### Trading comps (FY2024 financials, 16 May 2025 prices)

| | EV/EBITDA | P/E | Trailing EPS growth | PEG |
|---|---:|---:|---:|---:|
| **Apple** | **24.0x** | **31.3x** | 5.0% (2y CAGR, adj.) | **6.21** |
| Microsoft | 25.6x | 38.5x | 21.9% (1y) | 1.76 |
| Meta | 18.4x | 26.8x | 66.7% (2y) | 0.40 |
| Alphabet | 14.4x | 20.7x | 32.8% (2y) | 0.63 |
| Amazon | 17.8x | 37.2x | 90.7% (1y) | 0.41 |
| Peer median | 18.1x | 32.0x | | |

Apple traded at a P/E in line with its peers but on a much higher EV/EBITDA, with a fraction of their earnings
growth. At the peer-median EV/EBITDA, Apple is worth $158. At the peer-median P/E, it is worth $216.

Apple's FY2024 EPS excludes the one-off $10.2bn EU State Aid tax charge.

**PEG caveat:** PEG here uses trailing EPS growth, because the free data source keeps no historical consensus
estimates. Meta and Amazon's growth was a rebound from depressed 2022 earnings, which flatters their PEG.

### Capital allocation

![Capital allocation](reports/figures/capital_allocation.png)

| | FY2022 | FY2023 | FY2024 |
|---|---:|---:|---:|
| Free cash flow ($bn) | 111.4 | 99.6 | 108.8 |
| Buybacks + dividends ($bn) | 104.2 | 92.6 | 110.2 |
| Returned as % of FCF | 94% | 93% | 101% |
| Shares outstanding | −2.5% (FY23) | | −2.8% (FY24) |
| Diluted EPS growth | | +0.3% | −0.8% |
| … of which from fewer shares | | +3.2 pts | +2.6 pts |

Apple returns essentially all of its free cash flow, mostly through buybacks. Buybacks kept EPS flat in FY2023
and FY2024 even though net income fell about 3% a year.

Buybacks only create value per share when the stock is bought *below* intrinsic value. At the May 2025 price,
1.24× the base-case value, five more years of buybacks at the recent ~$87bn a year would **reduce** intrinsic
value per share by about **3.8%**. Bought at 0.8× intrinsic value, the same buybacks would add 5.4%.

### Hindsight check (not used in the valuation)

| | Forecast | Reported |
|---|---:|---:|
| FY2025 revenue | $408.6bn | $416.2bn (+1.8%) |
| FY2025 EBIT margin | 31.6% | 32.0% |
| AAPL price | $211.26 (16 May 2025) | $339.50 (20 Oct 2026), **+60.7%** |

The FY2025 operating forecast was slightly conservative. The stock then rose 61%, so the "overvalued" call would
have been wrong as a trading signal over the following 17 months. A DCF measures value, not timing, and the
re-rating since then implies the market adopted assumptions well beyond this model's bull case.

## How the results compare with the original project notes

| Item | Notes | This model | Why they differ |
|---|---:|---:|---|
| Market price | ~$210 | $211.26 | Close on 16 May 2025 |
| Beta | 1.26 (Bloomberg) | 1.05 | 2-year weekly regression vs the S&P 500, Blume-adjusted. Bloomberg data isn't available here, and its beta depends on the index, frequency and window chosen. |
| WACC | 8.5% | 8.99% | With a 4.44% risk-free rate, a beta of 1.26 and an 8.5% WACC only fit together if the equity risk premium is about 3.3%. Using beta 1.26 with this model's 4.5% ERP gives a WACC of 9.9%. |
| Intrinsic value | $192.80 | $170.21 | Holding the WACC at 8.5%, this model gives $178.47. The rest comes down to forecast and terminal assumptions. |
| Price vs value | ~8% above | ~24% above | Same conclusion (the price builds in optimistic assumptions), bigger gap. |
| Biggest drivers | WACC and capital allocation | WACC, then revenue growth and exit multiple | Buybacks drive *EPS* growth (2.6–3.2 points a year), but their effect on intrinsic value per share is small (−3.8% over five years at the 2025 price). |

## Run it

```bash
git clone https://github.com/spruha17nimkar/Equity-Valuation-of-Apple-Inc..git
cd Equity-Valuation-of-Apple-Inc.
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

aaplval run                                   # downloads data, writes reports/
aaplval run --assumptions my_assumptions.toml # your own forecast, WACC inputs or valuation date
pytest                                        # 15 tests, no network needed
```

Market and financial data come from Yahoo Finance (`yfinance`) and are cached in `data/`.

## Project layout

```
src/aaplval/
  assumptions.toml       every model input, in one place
  data.py                Yahoo Finance loader, cache and as-of-date filtering
  financials.py          standardised historical financials
  wacc.py                regression beta, CAPM, WACC
  dcf.py                 FCFF projection, two terminal values, equity bridge, sensitivity grids
  comps.py               EV/EBITDA, P/E, PEG and implied prices
  capital_allocation.py  cash deployment, buyback accretion
  model.py               orchestration, scenarios, tornado, hindsight check
  report.py              charts, Markdown report, Excel workbook
  cli.py                 `aaplval run`
reports/                 generated report, workbook, figures and summary.json
tests/                   unit tests (hand-checked DCF arithmetic, WACC, beta, comps, buybacks)
```

## Limitations
- Yahoo Finance provides only four fiscal years of statements, so the historical base is FY2022–FY2024. It has
  no historical consensus estimates, so the comps use trailing multiples and trailing growth.
- Bloomberg inputs (beta, ratings-based cost of debt) are replaced by a regression beta and an assumed credit spread.
- The equity bridge counts all marketable securities as cash. The comps use only cash and short-term
  investments for every company, to keep the comparison consistent.
- This is an educational model, not investment advice.

## License
MIT
