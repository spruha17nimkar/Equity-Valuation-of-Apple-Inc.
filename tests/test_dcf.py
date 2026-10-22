import pytest

from aaplval.dcf import DCFInputs, grid, project, value


@pytest.fixture
def inp():
    return DCFInputs(
        base_revenue=100.0, years=(1, 2), revenue_growth=(0.10, 0.10), ebit_margin=(0.30, 0.30),
        cash_tax_rate=0.20, da_pct_revenue=0.05, capex_pct_revenue=(0.05, 0.05), nwc_pct_incremental_revenue=0.10,
        wacc=0.10, perpetuity_growth=0.02, exit_ev_ebitda=10.0, perpetuity_weight=0.5,
        net_cash=20.0, shares=10.0, cost_of_equity=0.10, roll_forward_years=0.0,
    )


def test_fcff_by_hand(inp):
    f = project(inp)
    # Year 1: revenue 110, EBIT 33, NOPAT 26.4, D&A = capex = 5.5, dNWC = 0.1 * 10 = 1
    assert f.loc[1, "revenue"] == pytest.approx(110)
    assert f.loc[1, "fcff"] == pytest.approx(25.4)
    # Year 2: revenue 121, NOPAT 29.04, dNWC 1.1
    assert f.loc[2, "fcff"] == pytest.approx(27.94)
    assert f.loc[1, "discount_factor"] == pytest.approx(1.1 ** -0.5)


def test_terminal_values_and_equity_bridge(inp):
    r = value(inp)
    f = r.forecast
    pv = 25.4 * 1.1 ** -0.5 + 27.94 * 1.1 ** -1.5
    tv_g = 27.94 * 1.02 / 0.08
    tv_x = f.loc[2, "ebitda"] * 10
    assert r.pv_fcff == pytest.approx(pv)
    assert r.tv_perpetuity == pytest.approx(tv_g)
    assert r.per_share_perpetuity == pytest.approx((pv + tv_g / 1.21 + 20) / 10)
    assert r.per_share_exit == pytest.approx((pv + tv_x / 1.21 + 20) / 10)
    assert r.per_share_blended == pytest.approx((r.per_share_perpetuity + r.per_share_exit) / 2)


def test_cross_checks_are_consistent(inp):
    r = value(inp)
    # Using the implied multiple as the exit multiple must reproduce the perpetuity value, and vice versa.
    same = value(inp.shifted(exit_ev_ebitda=r.implied_exit_multiple))
    assert same.per_share_exit == pytest.approx(r.per_share_perpetuity)
    back = value(inp.shifted(perpetuity_growth=r.implied_perpetuity_growth))
    assert back.per_share_perpetuity == pytest.approx(r.per_share_exit)


def test_roll_forward_and_dividends(inp):
    base = value(inp).per_share_perpetuity
    rolled = value(inp.shifted(roll_forward_years=0.5, dividends_per_share_since_base=1.0)).per_share_perpetuity
    assert rolled == pytest.approx(base * 1.1 ** 0.5 - 1.0)


def test_value_falls_with_wacc_and_rises_with_growth(inp):
    assert value(inp.shifted(wacc=0.01)).per_share_blended < value(inp).per_share_blended
    assert value(inp.shifted(revenue_growth=0.02)).per_share_blended > value(inp).per_share_blended


def test_wacc_must_exceed_growth(inp):
    with pytest.raises(ValueError):
        value(inp.shifted(perpetuity_growth=0.12))


def test_grid_marks_invalid_cells_nan(inp):
    g = grid(inp, {"wacc": [0.02, 0.10]}, {"perpetuity_growth": [0.01, 0.03]}, "per_share_perpetuity",
             lambda i, w, gr: i.shifted(wacc=w - i.wacc, perpetuity_growth=gr))
    assert g.isna().sum().sum() == 1
    assert g.loc[0.10, 0.01] < g.loc[0.10, 0.03]
