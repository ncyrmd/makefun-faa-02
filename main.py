#!/usr/bin/env python3
"""Volatility-adaptive quantile forecaster for Polymarket price grids.

Reads one case at a time (makefun/polymarket-case/v1): every trading market
of the family with its Yes price at every minute up to a checkpoint, and
writes, for each market and each of the 240 minutes after the checkpoint,
five quantiles of that minute's price (5%, 25%, 50%, 75%, 95%).

Method (per market, independent):
  * The median stays at the checkpoint price. On the practice data, any
    momentum extrapolation of recent returns made the loss worse in every
    configuration tried, so the forecast carries no drift: prediction-market
    prices at this horizon mean-revert faster than they trend.
  * The spread is learned from the market's own recent moves: an
    exponentially weighted mean of the absolute one-minute returns over the
    last 120 minutes (half-life 80 minutes), scaled by 1.2533 (the
    normal-theory factor turning a mean absolute move into a standard
    deviation), floored at 0.0004 and capped at 0.01 price units per
    square-root minute. A market that has been jumping gets wide quantiles;
    a quiet one gets narrow ones. The house baseline's fixed 0.0025 spread
    does neither.
  * The spread grows with the square root of the horizon, the random-walk
    shape: q_tau(h) = x + z_tau * sigma * sqrt(h), clamped to [0, 1] and
    rounded to 6 decimals, with rows forced non-decreasing.

Local practice score (cases p00-p04, scored against the next case's grid):
loss 0.3243 against the house baseline's 0.3925 on the same cases, about
17% better. The official six-case baseline is 0.363589; p05 has no later
case to score against locally, so it is excluded here.

Standard library only, no network, deterministic: the same case always
writes the same bytes. Reads $MAKEFUN_INPUT_DIR (else /input), writes
$MAKEFUN_OUTPUT_DIR (else /output).
"""

import json
import math
import os
from pathlib import Path

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
# Standard normal quantiles at the five levels, to 6 decimals.
Z_SCORES = [-1.644854, -0.674490, 0.0, 0.674490, 1.644854]

# Recent window (minutes) the volatility estimate looks back over.
LOOKBACK_MINUTES = 120
# Half-life (minutes) of the exponential weights on absolute returns.
VOL_HALF_LIFE = 80
# Mean |return| -> sigma for a normal: E|N(0, s)| = s * sqrt(2/pi).
ABS_TO_SIGMA = 1.2533
# Spread bounds, price units per square-root minute.
SIGMA_FLOOR = 0.0004
SIGMA_CAP = 0.01


def clamp_price(value):
    """Clamp to [0, 1] and round to 6 decimals (0, never -0)."""
    return round(min(1.0, max(0.0, value)), 6) + 0.0


def recent_volatility(prices):
    """EWMA of absolute one-minute returns over the recent window.

    Returns 0.0 when there are no returns to learn from (a market with a
    single price point); the caller floors the resulting sigma.
    """
    count = len(prices)
    if count < 2:
        return 0.0
    start = max(1, count - LOOKBACK_MINUTES)
    decay = 1.0 - 0.5 ** (1.0 / VOL_HALF_LIFE)
    weighted = None
    for i in range(start, count):
        move = abs(prices[i] - prices[i - 1])
        weighted = move if weighted is None else (1.0 - decay) * weighted + decay * move
    return weighted if weighted is not None else 0.0


def forecast_market(prices, horizon):
    """240 rows of five quantiles for one market, from its price grid."""
    if not prices:
        raise ValueError("market has no prices")
    last_price = prices[-1]
    sigma = ABS_TO_SIGMA * recent_volatility(prices)
    sigma = min(SIGMA_CAP, max(SIGMA_FLOOR, sigma))
    rows = []
    for minute in range(1, horizon + 1):
        spread = sigma * math.sqrt(minute)
        row = [clamp_price(last_price + z * spread) for z in Z_SCORES]
        for j in range(1, len(row)):
            if row[j] < row[j - 1]:
                row[j] = row[j - 1]
        rows.append(row)
    return rows


def persistence_rows(last_price, horizon):
    """The house baseline's shape for one market: flat median, fixed spread.

    Used only as a fallback when a market's own data cannot be forecast,
    so one malformed market can never invalidate the whole case (an
    invalid case scores as if every quantile were 0.5 and takes no prize).
    """
    rows = []
    for minute in range(1, horizon + 1):
        spread = 0.0025 * math.sqrt(minute)
        rows.append([clamp_price(last_price + z * spread) for z in Z_SCORES])
    return rows


def forecast_case(case):
    """One forecast entry per market of the case, in the case's order."""
    horizon = case["horizon_minutes"]
    forecasts = []
    for market in case["markets"]:
        try:
            rows = forecast_market(market["prices"], horizon)
        except (ValueError, TypeError):
            prices = market.get("prices") or [0.5]
            rows = persistence_rows(prices[-1], horizon)
        forecasts.append({"id": market["id"], "q": rows})
    return {"forecasts": forecasts}


def main():
    input_dir = Path(INPUT_DIR)
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    case_files = sorted(p for p in input_dir.iterdir() if p.name.endswith(".in"))
    for case_file in case_files:
        case = json.loads(case_file.read_text(encoding="utf-8"))
        if list(case["quantiles"]) != QUANTILES:
            raise ValueError(f"{case_file.name} asks for quantiles "
                             f"{case['quantiles']}, not {QUANTILES}")
        result = forecast_case(case)
        out_path = output_dir / f"{case_file.stem}.out"
        out_path.write_text(json.dumps(result) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
