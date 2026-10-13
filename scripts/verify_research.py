"""Local, input-only research checks. Does not verify sources or recommend trades."""

import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
import json


def number(raw, name):
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name}: expected a finite decimal") from None
    if not value.is_finite():
        raise ValueError(f"{name}: expected a finite decimal")
    return value


def timestamp(raw, name):
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise ValueError(f"{name}: use an ISO timestamp with timezone") from None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}: timezone is required")
    return value


def time_check(as_of, published_at, available_at, retrieved_at):
    cutoff = timestamp(as_of, "as_of")
    published = timestamp(published_at, "published_at")
    available = timestamp(available_at, "available_at")
    retrieved = timestamp(retrieved_at, "retrieved_at")
    issues = []
    if available < published:
        issues.append("AVAILABLE_BEFORE_PUBLICATION")
    if available > cutoff or published > cutoff:
        issues.append("NOT_PUBLICLY_AVAILABLE_AT_CUTOFF")
    if retrieved < available:
        issues.append("RETRIEVED_BEFORE_AVAILABILITY")
    return {
        "status": "REVIEW_REQUIRED" if issues else "CHECK_PASS",
        "issues": issues,
        "scope": "User-provided public-data timestamps only; not a trading-calendar check.",
    }


def market_cap(price, shares, reported, tolerance):
    p, s, r, t = [number(v, n) for v, n in zip(
        (price, shares, reported, tolerance), ("price", "shares", "reported", "tolerance")
    )]
    if p <= 0 or s <= 0 or r < 0 or not 0 <= t <= 1:
        raise ValueError("positive price/shares, nonnegative reported, and tolerance in [0,1] required")
    with localcontext() as ctx:
        ctx.prec = 50
        expected = p * s
        error = abs(r - expected) / expected
        return {
            "status": "CHECK_PASS" if error <= t else "REVIEW_REQUIRED",
            "calculated": str(expected),
            "reported": str(r),
            "relative_error": str(error),
            "tolerance": str(t),
            "scope": "One share class; caller must align currency, scale and date.",
        }


def valuation_cap(value, margin):
    v, m = number(value, "value"), number(margin, "margin")
    if v <= 0 or not 0 <= m < 1:
        raise ValueError("positive value and margin in [0,1) required")
    with localcontext() as ctx:
        ctx.prec = 50
        return {
            "status": "CHECK_PASS",
            "buy_cap": str(v * (1 - m)),
            "scope": "Arithmetic under supplied assumptions; not a validated fair value or buy signal.",
        }


def dividend_cover(fcf, dividend):
    f, d = number(fcf, "fcf"), number(dividend, "dividend")
    if d < 0:
        raise ValueError("dividend must be nonnegative")
    if f <= 0 or d == 0:
        return {
            "status": "NOT_MEANINGFUL",
            "coverage": None,
            "payout_ratio": None,
            "reason": "Positive cash flow and positive dividend required for conventional ratios.",
        }
    with localcontext() as ctx:
        ctx.prec = 50
        return {
            "status": "CHECK_PASS",
            "coverage": str(f / d),
            "payout_ratio": str(d / f),
            "cash_surplus_after_dividend": str(f - d),
            "scope": "Arithmetic only; sector, period and cash-flow definition must be checked separately.",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    commands = {
        "time-check": (time_check, ("as-of", "published-at", "available-at", "retrieved-at")),
        "market-cap": (market_cap, ("price", "shares", "reported", "tolerance")),
        "valuation-cap": (valuation_cap, ("value", "margin")),
        "dividend-cover": (dividend_cover, ("fcf", "dividend")),
    }
    for name, (_, fields) in commands.items():
        sub = subs.add_parser(name)
        for field in fields:
            sub.add_argument("--" + field, required=True)
    args = vars(parser.parse_args())
    func = commands[args.pop("command")][0]
    try:
        result = func(**args)
    except (ValueError, InvalidOperation, OverflowError) as exc:
        result = {"status": "INVALID_INPUT", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return {"REVIEW_REQUIRED": 1, "INVALID_INPUT": 2}.get(result["status"], 0)


if __name__ == "__main__":
    raise SystemExit(main())
