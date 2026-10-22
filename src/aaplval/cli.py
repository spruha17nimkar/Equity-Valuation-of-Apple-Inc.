"""Command line: ``aaplval run``."""

from __future__ import annotations

import argparse

from .config import load_assumptions


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aaplval", description="Equity valuation of Apple Inc.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the valuation and write reports/")
    r.add_argument("--assumptions", help="TOML file (defaults to the packaged assumptions.toml)")
    r.add_argument("--out", default="reports", help="output folder")
    r.add_argument("--refresh", action="store_true", help="re-download data instead of using the cache")
    args = p.parse_args(argv)

    from .model import run
    from .report import write_all

    v = run(load_assumptions(args.assumptions), refresh=args.refresh)
    out = write_all(v, args.out)
    print(f"Valuation date {v.valuation_date.date()}  price ${v.price:.2f}")
    print(f"WACC {v.wacc.wacc:.2%}  (beta {v.wacc.beta:.2f}, cost of equity {v.wacc.cost_of_equity:.2%})")
    print(f"Intrinsic value ${v.intrinsic_value:.2f}  (perpetuity ${v.base.per_share_perpetuity:.2f}, exit ${v.base.per_share_exit:.2f})")
    print(f"Price vs intrinsic {v.premium_to_intrinsic:+.1%}")
    print(f"Reports written to {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
