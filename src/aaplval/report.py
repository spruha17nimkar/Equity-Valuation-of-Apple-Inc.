"""Charts, Markdown report, Excel workbook and JSON summary for a valuation run."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .model import Valuation  # noqa: E402

BLUE, RED, GREY, GREEN = "#1f4e79", "#c0392b", "#7f8c8d", "#2e7d32"
B = 1e9


def _save(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def heatmap(df: pd.DataFrame, price: float, title: str, xfmt, yfmt, path: Path, base=None) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    z = df.to_numpy()
    lim = np.nanmax(np.abs(z / price - 1))
    im = ax.imshow(z / price - 1, cmap="RdYlGn", vmin=-lim, vmax=lim, aspect="auto")
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            if np.isfinite(z[i, j]):
                bold = base is not None and (df.index[i], df.columns[j]) == base
                ax.text(j, i, f"${z[i, j]:.0f}", ha="center", va="center", fontsize=9,
                        fontweight="bold" if bold else "normal")
    ax.set_xticks(range(z.shape[1]), [xfmt(c) for c in df.columns])
    ax.set_yticks(range(z.shape[0]), [yfmt(r) for r in df.index])
    ax.set_xlabel(df.columns.name.replace("_", " "))
    ax.set_ylabel(df.index.name.replace("_", " "))
    ax.set_title(title, fontsize=11)
    cb = fig.colorbar(im, ax=ax, format=lambda x, _: f"{x:+.0%}")
    cb.set_label(f"vs market price ${price:.2f}")
    _save(fig, path)


def charts(v: Valuation, out: Path) -> dict[str, str]:
    out.mkdir(parents=True, exist_ok=True)
    pct = lambda x: f"{x:.1%}"  # noqa: E731
    files = {}
    s = v.sensitivity
    base_w = round(v.wacc.wacc, 4)
    t = v.inputs

    heatmap(s["wacc_x_growth"], v.price, "Perpetuity-growth method: value per share", pct, pct,
            out / "heatmap_wacc_growth.png", (base_w, t.perpetuity_growth))
    heatmap(s["wacc_x_exit"], v.price, "Exit-multiple method: value per share", lambda x: f"{x:.0f}x", pct,
            out / "heatmap_wacc_exit.png", (base_w, t.exit_ev_ebitda))
    heatmap(s["growth_x_margin"], v.price, "Blended value: revenue growth vs EBIT margin shifts",
            lambda x: f"{x:+.0%}", lambda x: f"{x:+.0%}", out / "heatmap_growth_margin.png", (0.0, 0.0))
    files.update(heatmaps=["heatmap_wacc_growth.png", "heatmap_wacc_exit.png", "heatmap_growth_margin.png"])

    # Tornado
    tor = v.tornado.iloc[::-1]
    base = v.intrinsic_value
    fig, ax = plt.subplots(figsize=(8, 4.2))
    y = np.arange(len(tor))
    ax.barh(y, tor["low"] - base, left=base, color=RED, alpha=0.8, label="downside case")
    ax.barh(y, tor["high"] - base, left=base, color=GREEN, alpha=0.8, label="upside case")
    ax.axvline(base, color="black", lw=1)
    ax.axvline(v.price, color=BLUE, ls="--", lw=1.2, label=f"market price ${v.price:.0f}")
    ax.set_yticks(y, tor.index)
    ax.set_xlabel("blended value per share ($)")
    ax.set_title(f"What moves the value most (base ${base:.0f})", fontsize=11)
    ax.legend(loc="lower right", fontsize=8)
    _save(fig, out / "tornado.png")
    files["tornado"] = "tornado.png"

    # Football field
    rows = [
        ("DCF: perpetuity growth (bear-bull)", v.scenarios["bear"].per_share_perpetuity, v.scenarios["bull"].per_share_perpetuity, v.base.per_share_perpetuity),
        ("DCF: exit multiple (bear-bull)", v.scenarios["bear"].per_share_exit, v.scenarios["bull"].per_share_exit, v.base.per_share_exit),
        ("DCF: blended (bear-bull)", v.scenarios["bear"].per_share_blended, v.scenarios["bull"].per_share_blended, v.base.per_share_blended),
        ("Comps: EV/EBITDA (peer range)", v.comps_implied.loc["ev_ebitda", "low"], v.comps_implied.loc["ev_ebitda", "high"], v.comps_implied.loc["ev_ebitda", "median"]),
        ("Comps: P/E (peer range)", v.comps_implied.loc["pe", "low"], v.comps_implied.loc["pe", "high"], v.comps_implied.loc["pe", "median"]),
    ]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    for i, (name, lo, hi, mid) in enumerate(rows[::-1]):
        ax.barh(i, hi - lo, left=lo, color=BLUE, alpha=0.55)
        ax.plot([mid, mid], [i - 0.4, i + 0.4], color="black", lw=2)
    ax.axvline(v.price, color=RED, ls="--", label=f"market price ${v.price:.2f} ({v.valuation_date.date()})")
    lo_all = min(min(r[1], r[2]) for r in rows + [("", v.price, v.price, 0)])
    hi_all = max(max(r[1], r[2]) for r in rows + [("", v.price, v.price, 0)])
    ax.set_xlim(lo_all - 0.06 * (hi_all - lo_all), hi_all + 0.06 * (hi_all - lo_all))
    ax.set_yticks(range(len(rows)), [r[0] for r in rows[::-1]])
    ax.set_xlabel("value per share ($); black tick = base case / peer median")
    ax.set_title("Valuation summary", fontsize=11)
    ax.legend(fontsize=8, loc="lower right")
    _save(fig, out / "football_field.png")
    files["football_field"] = "football_field.png"

    # FCFF history and forecast
    h, f = v.historicals, v.base.forecast
    fig, ax = plt.subplots(figsize=(8, 3.8))
    hist_fcff = (h["ebit"] * (1 - t.cash_tax_rate) + h["da"] - h["capex"]) / B
    ax.bar([str(x) for x in h.index], hist_fcff, color=GREY, label="historical (normalised tax, before NWC)")
    ax.bar([f"{x}E" for x in f.index], f["fcff"] / B, color=BLUE, label="forecast FCFF")
    ax2 = ax.twinx()
    ax2.plot([str(x) for x in h.index] + [f"{x}E" for x in f.index], list(h["ebit_margin"]) + list(f["ebit_margin"]),
             color=RED, marker="o", label="EBIT margin")
    ax2.yaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
    ax.set_ylabel("$bn")
    ax.set_title("Free cash flow to the firm", fontsize=11)
    ax.legend(loc="upper left", fontsize=8)
    ax2.legend(loc="lower right", fontsize=8)
    _save(fig, out / "fcff.png")
    files["fcff"] = "fcff.png"

    # Capital allocation
    c = v.capital_allocation
    yrs = [str(x) for x in c.index]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.bar(yrs, c["capex"] / B, color=GREY, label="capex")
    ax.bar(yrs, c["dividends"] / B, bottom=c["capex"] / B, color=GREEN, label="dividends")
    ax.bar(yrs, c["buybacks"] / B, bottom=(c["capex"] + c["dividends"]) / B, color=BLUE, label="buybacks")
    ax.plot(yrs, c["operating_cash_flow"] / B, color="black", marker="o", label="operating cash flow")
    ax2 = ax.twinx()
    ax2.plot(yrs, c["shares_outstanding"] / B, color=RED, marker="s", ls="--", label="shares outstanding (rhs)")
    ax.set_ylabel("$bn")
    ax2.set_ylabel("shares outstanding (bn)")
    ax.set_ylim(0, max(c["operating_cash_flow"].max(), (c["capex"] + c["dividends"] + c["buybacks"]).max()) / B * 1.1)
    ax.set_title("Where operating cash flow goes", fontsize=11)
    handles = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    labels = ax.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    fig.legend(handles, labels, loc="lower center", ncol=5, fontsize=8, bbox_to_anchor=(0.5, -0.02))
    fig.subplots_adjust(bottom=0.2)
    _save(fig, out / "capital_allocation.png")
    files["capital_allocation"] = "capital_allocation.png"

    # Comps
    comp = v.comps
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4))
    for ax, (col, label) in zip(axes, [("ev_ebitda", "EV / EBITDA"), ("pe", "P / E"), ("peg", "PEG (trailing growth)")]):
        colors = [RED if tk == v.assumptions["valuation"]["ticker"] else BLUE for tk in comp.index]
        ax.bar(comp.index, comp[col], color=colors)
        med = comp.drop(index=v.assumptions["valuation"]["ticker"])[col].median()
        ax.axhline(med, color="black", ls=":", lw=1, label=f"peer median {med:.1f}")
        ax.set_title(label, fontsize=10)
        ax.legend(fontsize=7)
    _save(fig, out / "comps.png")
    files["comps"] = "comps.png"
    return files


def _m(x: float) -> str:
    return f"${x / B:,.1f}bn"


def markdown(v: Valuation, fig_dir: str) -> str:
    a, w, b, inp = v.assumptions, v.wacc, v.base, v.inputs
    f = b.forecast
    tk = a["valuation"]["ticker"]
    prem = v.premium_to_intrinsic
    L = [
        f"# {tk} valuation report",
        "",
        f"**Valuation date:** {v.valuation_date.date()} | **Price:** ${v.price:.2f} (close {v.price_date.date()}) | "
        f"**Base year:** FY{a['valuation']['base_fiscal_year']} (latest 10-K public on the valuation date)",
        "",
        "## Answer",
        f"- **Intrinsic value: ${v.intrinsic_value:.2f} per share** (50/50 blend of perpetuity growth ${b.per_share_perpetuity:.2f} "
        f"and exit multiple ${b.per_share_exit:.2f}).",
        f"- The market price is **{prem:+.1%}** relative to intrinsic value. "
        + ("The market is pricing in more growth, margin or a lower discount rate than the base case."
           if prem > 0 else "The market price is below the base-case value."),
        f"- Scenario range: bear ${v.scenarios['bear'].per_share_blended:.2f}, base ${v.intrinsic_value:.2f}, bull ${v.scenarios['bull'].per_share_blended:.2f}.",
        "",
        f"![Valuation summary]({fig_dir}/football_field.png)",
        "",
        "## Cost of capital",
        "| Input | Value | Source |",
        "|---|---:|---|",
        f"| Risk-free rate | {w.risk_free:.2%} | 10-year US Treasury yield on {v.valuation_date.date()} |",
    ]
    if v.beta:
        L.append(f"| Beta (adjusted) | {w.beta:.2f} | raw {v.beta.raw:.2f} from {v.beta.n_obs} weekly returns vs S&P 500, "
                 f"{v.beta.start} to {v.beta.end} (R² {v.beta.r_squared:.2f}, s.e. {v.beta.std_error:.2f}); Blume-adjusted 0.67·raw + 0.33 |")
    else:
        L.append(f"| Beta | {w.beta:.2f} | assumption |")
    L += [
        f"| Equity risk premium | {w.equity_risk_premium:.2%} | assumption |",
        f"| Cost of equity (CAPM) | {w.cost_of_equity:.2%} | rf + β × ERP |",
        f"| Pre-tax cost of debt | {w.pre_tax_cost_of_debt:.2%} | rf + {a['market']['pre_tax_cost_of_debt_spread']:.2%} spread |",
        f"| After-tax cost of debt | {w.after_tax_cost_of_debt:.2%} | at {w.tax_rate:.0%} marginal tax |",
        f"| Weights E / D | {w.weight_equity:.1%} / {w.weight_debt:.1%} | market cap {_m(w.equity_value)}, debt {_m(w.debt_value)} |",
        f"| **WACC** | **{w.wacc:.2%}** | |",
        "",
        "## Free cash flow forecast ($bn)",
        "| | " + " | ".join(f"FY{y}E" for y in f.index) + " |",
        "|---|" + "---:|" * len(f),
    ]
    for col, label, fmt in [("revenue", "Revenue", "bn"), ("revenue_growth", "Growth", "pct"), ("ebit", "EBIT", "bn"),
                            ("ebit_margin", "EBIT margin", "pct"), ("taxes", "Cash taxes", "bn"), ("nopat", "NOPAT", "bn"),
                            ("da", "+ D&A", "bn"), ("capex", "- Capex", "bn"), ("delta_nwc", "- Change in NWC", "bn"),
                            ("fcff", "**FCFF**", "bn"), ("discount_factor", "Discount factor (mid-year)", "x"), ("pv_fcff", "PV of FCFF", "bn")]:
        vals = f[col]
        cells = [f"{x / B:,.1f}" if fmt == "bn" else f"{x:.1%}" if fmt == "pct" else f"{x:.3f}" for x in vals]
        L.append(f"| {label} | " + " | ".join(cells) + " |")
    L += [
        "",
        f"![FCFF]({fig_dir}/fcff.png)",
        "",
        "## Terminal value",
        "| | Perpetuity growth | Exit multiple |",
        "|---|---:|---:|",
        f"| Assumption | g = {inp.perpetuity_growth:.1%} | {inp.exit_ev_ebitda:.1f}x FY{f.index[-1]} EBITDA |",
        f"| Terminal value | {_m(b.tv_perpetuity)} | {_m(b.tv_exit)} |",
        f"| PV of terminal value | {_m(b.pv_tv_perpetuity)} | {_m(b.pv_tv_exit)} |",
        f"| PV of FCFF FY{f.index[0]}-FY{f.index[-1]} | {_m(b.pv_fcff)} | {_m(b.pv_fcff)} |",
        f"| Enterprise value (at FY{a['valuation']['base_fiscal_year']} year end) | {_m(b.ev_perpetuity)} | {_m(b.ev_exit)} |",
        f"| Terminal value share of EV | {b.tv_share_of_ev['perpetuity']:.0%} | {b.tv_share_of_ev['exit']:.0%} |",
        f"| Cross-check | implies {b.implied_exit_multiple:.1f}x EBITDA | implies g = {b.implied_perpetuity_growth:.2%} |",
        f"| **Value per share at valuation date** | **${b.per_share_perpetuity:.2f}** | **${b.per_share_exit:.2f}** |",
        "",
        f"Equity bridge: EV + net cash {_m(inp.net_cash)} (cash, short- and long-term marketable securities less total debt), "
        f"÷ {inp.shares / B:.2f}bn shares, rolled forward {inp.roll_forward_years:.2f} years at the cost of equity, "
        f"less ${inp.dividends_per_share_since_base:.2f} of dividends paid in between.",
        "",
        "## Scenarios",
        "| Scenario | Revenue growth | EBIT margin | WACC | g | Exit | Perpetuity | Exit multiple | Blended | Price vs value |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("bear", "base", "bull"):
        r = v.scenarios[name]
        s = a["scenarios"].get(name, {})
        L.append(f"| {name} | {np.mean(r.forecast['revenue_growth']):.1%} avg | {r.forecast['ebit_margin'].iloc[-1]:.1%} FY{f.index[-1]} | "
                 f"{w.wacc + s.get('wacc_shift', 0):.2%} | {s.get('perpetuity_growth', inp.perpetuity_growth):.1%} | "
                 f"{s.get('exit_ev_ebitda', inp.exit_ev_ebitda):.0f}x | ${r.per_share_perpetuity:.2f} | ${r.per_share_exit:.2f} | "
                 f"**${r.per_share_blended:.2f}** | {v.price / r.per_share_blended - 1:+.0%} |")
    sens = v.sensitivity
    L += [
        "",
        "## Sensitivity",
        f"Ranges tested: WACC {min(sens['wacc_x_growth'].index):.2%}-{max(sens['wacc_x_growth'].index):.2%}, "
        f"terminal growth {min(sens['wacc_x_growth'].columns):.1%}-{max(sens['wacc_x_growth'].columns):.1%}, "
        f"exit multiple {min(sens['wacc_x_exit'].columns):.0f}x-{max(sens['wacc_x_exit'].columns):.0f}x, "
        f"revenue growth and EBIT margin ±{max(sens['growth_x_margin'].index):.0%} points.",
        "",
        f"![WACC x growth]({fig_dir}/heatmap_wacc_growth.png)",
        f"![WACC x exit]({fig_dir}/heatmap_wacc_exit.png)",
        f"![Growth x margin]({fig_dir}/heatmap_growth_margin.png)",
        "",
        "| Driver (one at a time) | Low | High | Swing | % of base |",
        "|---|---:|---:|---:|---:|",
        *[f"| {d} | ${r.low:.2f} | ${r.high:.2f} | ${r.swing:.2f} | {r.swing_pct_of_base:.0%} |" for d, r in v.tornado.iterrows()],
        "",
        f"![Tornado]({fig_dir}/tornado.png)",
        "",
        "## Trading comparables (last fiscal year public on the valuation date)",
        "| Company | FY | Price | EV/EBITDA | P/E | EPS growth (CAGR, yrs) | PEG |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for t_, r in v.comps.iterrows():
        L.append(f"| {t_} | {int(r.fiscal_year)} | ${r.price:.2f} | {r.ev_ebitda:.1f}x | {r.pe:.1f}x | "
                 f"{r.eps_growth:.1%} ({int(r.eps_growth_years)}y) | {r.peg:.2f} |")
    ci = v.comps_implied
    L += [
        "",
        f"Apple at peer-median EV/EBITDA ({ci.loc['ev_ebitda', 'peer_median_multiple']:.1f}x) is worth ${ci.loc['ev_ebitda', 'median']:.2f}; "
        f"at peer-median P/E ({ci.loc['pe', 'peer_median_multiple']:.1f}x) ${ci.loc['pe', 'median']:.2f}. "
        f"Apple's EPS is adjusted for the one-off ${a['adjustments']['aapl_fy2024_one_off_tax_charge'] / B:.1f}bn FY24 tax charge.",
        "",
        f"![Comps]({fig_dir}/comps.png)",
        "",
        "## Capital allocation",
        "| | " + " | ".join(f"FY{y}" for y in v.capital_allocation.index) + " |",
        "|---|" + "---:|" * len(v.capital_allocation),
    ]
    c = v.capital_allocation
    for col, label, fmt in [("operating_cash_flow", "Operating cash flow", "bn"), ("capex", "Capex", "bn"),
                            ("free_cash_flow", "Free cash flow", "bn"), ("buybacks", "Buybacks", "bn"),
                            ("dividends", "Dividends", "bn"), ("payout_pct_fcf", "Returned as % of FCF", "share"),
                            ("sbc", "Stock-based compensation", "bn"), ("net_cash", "Net cash", "bn"),
                            ("share_count_change", "Change in shares outstanding", "pct"),
                            ("implied_net_repurchase_price", "Buyback $ per net share retired", "usd"),
                            ("net_income_growth", "Net income growth", "pct"), ("eps_growth", "Diluted EPS growth", "pct"),
                            ("eps_growth_from_share_count", "EPS growth from lower share count", "pct")]:
        cells = []
        for x in c[col]:
            if pd.isna(x):
                cells.append("–")
            else:
                cells.append(f"{x / B:,.1f}" if fmt == "bn" else f"{x:+.1%}" if fmt == "pct"
                             else f"{x:.0%}" if fmt == "share" else f"${x:,.0f}")
        L.append(f"| {label} | " + " | ".join(cells) + " |")
    acc = v.buyback_accretion
    mkt = acc[acc["is_market_price"]].iloc[0]
    L += [
        "",
        f"![Capital allocation]({fig_dir}/capital_allocation.png)",
        "",
        f"**Buybacks and per-share value.** Holding the business constant, five years of buybacks at the recent "
        f"${v.historicals['buybacks'].tail(3).mean() / B:.0f}bn a year change intrinsic value per share by:",
        "",
        "| Buyback price ÷ intrinsic value | Value per share after 5 years | Change |",
        "|---:|---:|---:|",
        *[f"| {i:.2f}{' (market price)' if r.is_market_price else ''} | ${r.value_per_share_after:.2f} | {round(r.change_vs_no_buyback, 6) + 0:+.1%} |"
          for i, r in acc.iterrows()],
        "",
        f"At the valuation-date price, continued buybacks would *dilute* intrinsic value per share by {abs(mkt.change_vs_no_buyback):.1%} over five years.",
    ]
    hs = v.hindsight
    if "first_year" in hs:
        fy = hs["first_year"]
        L += [
            "",
            "## Hindsight check (not used in the valuation)",
            f"- FY{fy['fiscal_year']} revenue: forecast {_m(fy['revenue_forecast'])}, reported {_m(fy['revenue_actual'])} "
            f"({fy['revenue_actual'] / fy['revenue_forecast'] - 1:+.1%}).",
            f"- FY{fy['fiscal_year']} EBIT margin: forecast {fy['ebit_margin_forecast']:.1%}, reported {fy['ebit_margin_actual']:.1%}.",
            f"- FY{fy['fiscal_year']} FCFF forecast {_m(fy['fcff_forecast'])} vs reported free cash flow {_m(fy['reported_fcf_actual'])} "
            "(not like-for-like: reported FCF is after interest, actual taxes and a large working-capital outflow).",
            f"- AAPL closed at ${hs['latest_price']:.2f} on {hs['latest_price_date']}, {hs['return_since_valuation']:+.1%} since the valuation date.",
        ]
    return "\n".join(L) + "\n"


def summary(v: Valuation) -> dict:
    return {
        "valuation_date": str(v.valuation_date.date()),
        "price": v.price,
        "intrinsic_value_blended": v.intrinsic_value,
        "intrinsic_value_perpetuity": v.base.per_share_perpetuity,
        "intrinsic_value_exit": v.base.per_share_exit,
        "price_vs_intrinsic": v.premium_to_intrinsic,
        "scenarios": {k: r.per_share_blended for k, r in v.scenarios.items()},
        "wacc": v.wacc.to_dict(),
        "beta": None if v.beta is None else v.beta.__dict__,
        "terminal": {"perpetuity_growth": v.inputs.perpetuity_growth, "exit_ev_ebitda": v.inputs.exit_ev_ebitda,
                     "implied_exit_multiple": v.base.implied_exit_multiple,
                     "implied_perpetuity_growth": v.base.implied_perpetuity_growth},
        "tornado": v.tornado.reset_index().to_dict(orient="records"),
        "comps": v.comps.reset_index().to_dict(orient="records"),
        "hindsight": v.hindsight,
    }


def excel(v: Valuation, path: Path) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        pd.json_normalize(v.assumptions, sep=".").T.rename(columns={0: "value"}).astype(str).to_excel(xw, sheet_name="Assumptions")
        v.historicals.T.to_excel(xw, sheet_name="Historicals")
        pd.Series(v.wacc.to_dict(), name="value").to_excel(xw, sheet_name="WACC")
        v.base.forecast.T.to_excel(xw, sheet_name="DCF")
        pd.DataFrame({k: {"perpetuity": r.per_share_perpetuity, "exit": r.per_share_exit, "blended": r.per_share_blended}
                      for k, r in v.scenarios.items()}).to_excel(xw, sheet_name="Scenarios")
        row = 0
        for name, df in v.sensitivity.items():
            pd.DataFrame({name: []}).to_excel(xw, sheet_name="Sensitivity", startrow=row)
            df.to_excel(xw, sheet_name="Sensitivity", startrow=row + 1)
            row += len(df) + 4
        v.tornado.to_excel(xw, sheet_name="Tornado")
        v.comps.to_excel(xw, sheet_name="Comps")
        v.comps_implied.to_excel(xw, sheet_name="Comps", startrow=len(v.comps) + 3)
        v.capital_allocation.T.to_excel(xw, sheet_name="Capital allocation")
        v.buyback_accretion.to_excel(xw, sheet_name="Capital allocation", startrow=len(v.capital_allocation.T) + 3)


def write_all(v: Valuation, out_dir: str | Path = "reports") -> Path:
    out = Path(out_dir)
    charts(v, out / "figures")
    (out / "valuation_report.md").write_text(markdown(v, "figures"))
    (out / "summary.json").write_text(json.dumps(summary(v), indent=2, default=float))
    excel(v, out / "aapl_valuation.xlsx")
    return out
