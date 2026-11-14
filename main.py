#!/usr/bin/env python3
"""Peaked-shape quantile forecaster for Polymarket price grids, v3.

Reads one case at a time (makefun/polymarket-case/v1): every trading
market of the family with its Yes price at every minute up to a
checkpoint, and writes, for each market and each of the 240 minutes after
the checkpoint, five quantiles of that minute's price (5%, 25%, 50%,
75%, 95%).

What changed since v2, and why. v2 (median = checkpoint price with a
small contender fade, spread from a 15-minute-half-life EWMA of absolute
one-minute returns) scored a local practice loss of 0.317242 and an
official 0.278821. v3 changes exactly one thing: the shape of the
forecast distribution at the inner quantiles.

  * Jump-driven prices are not normal. 88% of the one-minute returns
    in the practice data are exactly zero, the 99th percentile of the
    absolute move is 0.045, and the largest is 0.48. The price at a
    future minute is the sum of many such moves, so its distribution is
    peaked: most of the mass sits at or near the median, and the
    interquartile range is narrower than a normal with the same spread
    would claim. v2 drew the 25%/75% quantiles at the normal z-scores
    of +/-0.674; v3 draws them at +/-0.40. The 5%/95% quantiles keep
    the normal +/-1.645: the tails are where the jumps live, and
    widening or narrowing them (tried in v2 and again here) only made
    the loss worse, so the outer shape is left alone.
  * The evidence for the narrower inner shape is broad, not one case.
    Shrinking the inner z from 0.674 to 0.40 cuts the local practice
    loss from 0.317242 to 0.312612, with 3 of 5 cases improving and the
    other two flat or worse by a hair; leaving any one case out, the
    gain survives in 4 of 5 folds (the mean over p01-p04 improves from
    0.2800 to 0.2720). At the market level 59 of 104 (case, market)
    pairs improve, and a paired bootstrap over them puts the chance
    the improvement is real at 0.87. The optimum is flat (0.35, 0.40
    and 0.45 all land within 0.001 of each other), so the choice is
    not a knife-edge fit to six practice cases.
  * Everything else is v2's, untouched: the 15-minute-half-life jump
    volatility tracker (a slow tracker stays wide after a jump has
    passed and narrow while a fresh one unfolds), the contender fade
    (0.005 per hour per unit of price above 0.05, linear in the
    horizon), the square-root horizon growth, the 0.0004 sigma floor
    and the 0.01 cap. Stronger fades were tested and rejected: they
    win the practice mean only through the opening case and lose on
    the established cases, so they would not travel to the final.

Local practice score (cases p00-p04, scored against the next case's
grid; p05 has no later case to score against locally): loss 0.312612,
coverage_90 0.8680, per-case losses 0.5232 / 0.3136 / 0.3500 / 0.2244 /
0.2001 — about 1.5% better than v2's 0.317242 and 20% better than the
house baseline's 0.3925 on the same cases. v2's official loss was
0.278821 against a local 0.317242, so v3's expected official score is
around 0.275. The final phase grades on live FAA markets, not on this
practice event, so the practice number is a guide, not a promise: the
inner-shape change is a property of Polymarket's jump-driven grids in
general, not of the NVIDIA event in particular, which is why it is
the one change v3 makes.

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
# Quantile multipliers. The outer two are the standard normal z-scores;
# the inner two are shrunk (see the module docstring): jump-driven
# prices pile mass near the median, so the interquartile range is
# narrower than a normal with the same spread. 0.40 sits at the center
# of a flat valley (0.35-0.45 all score within 0.001), and the gain
# survives leaving any one practice case out in 4 of 5 folds.
OUTER_Z = 1.644854
INNER_Z = 0.40
Z_VALUES = [-OUTER_Z, -INNER_Z, 0.0, INNER_Z, OUTER_Z]

# Minutes of history the volatility tracker looks back over.
LOOKBACK_MINUTES = 120
# Half-life (minutes) of the exponential weights on absolute returns.
# 15, not 80: jump-driven prices need a fast volatility tracker.
VOL_HALF_LIFE = 15
# Mean |return| -> sigma for a normal: E|N(0, s)| = s * sqrt(2/pi).
ABS_TO_SIGMA = 1.2533
# Spread bounds, price units per square-root minute.
SIGMA_FLOOR = 0.0004
SIGMA_CAP = 0.01
# Contender fade: median sag per hour, per unit of (price - 0.05).
CONTENDER_DECAY = 0.005
# Prices at or below this do not fade (they already sit near zero).
DECAY_FLOOR_PRICE = 0.05


def clamp_price(value):
    """Clamp to [0, 1] and round to 6 decimals (0, never -0)."""
    return round(min(1.0, max(0.0, value)), 6) + 0.0


def window_abs_moves(prices):
    """Absolute one-minute returns over the recent window, oldest first."""
    count = len(prices)
    start = max(1, count - LOOKBACK_MINUTES)
    return [abs(prices[i] - prices[i - 1]) for i in range(start, count)]


def track_jump_sigma(prices):
    """EWMA of absolute one-minute returns, as a per-minute sigma.

    The weights decay with a 15-minute half-life, so a jump widens the
    forecast within minutes and the widening fades within the hour.
    Returns 0.0 when there are no returns to learn from; the caller
    floors the resulting sigma.
    """
    moves = window_abs_moves(prices)
    if not moves:
        return 0.0
    decay = 1.0 - 0.5 ** (1.0 / VOL_HALF_LIFE)
    level = moves[0]
    for move in moves[1:]:
        level = (1.0 - decay) * level + decay * move
    return level


def contender_sag(price, minute):
    """How far the median sags below the checkpoint price by `minute`.

    Contenders fade; near-zero prices do not. Linear in the horizon so
    the sag is 0.005 * (price - 0.05) per hour for a market above 0.05.
    """
    excess = price - DECAY_FLOOR_PRICE
    if excess <= 0.0:
        return 0.0
    return CONTENDER_DECAY * (minute / 60.0) * excess


def quantiles_for_market(prices, horizon):
    """240 rows of five quantiles for one market, from its price grid."""
    if not prices:
        raise ValueError("market has no prices")
    last_price = prices[-1]
    sigma = ABS_TO_SIGMA * track_jump_sigma(prices)
    sigma = min(SIGMA_CAP, max(SIGMA_FLOOR, sigma))
    rows = []
    for minute in range(1, horizon + 1):
        center = last_price - contender_sag(last_price, minute)
        spread = sigma * math.sqrt(minute)
        row = [clamp_price(center + z * spread) for z in Z_VALUES]
        for j in range(1, len(row)):
            if row[j] < row[j - 1]:
                row[j] = row[j - 1]
        rows.append(row)
    return rows


def baseline_rows(last_price, horizon):
    """The house baseline's shape for one market: flat median, fixed spread.

    Used only when a market's own data cannot be forecast, so one
    malformed market can never invalidate the whole case (an invalid
    case scores as if every quantile were 0.5 and takes no prize).
    """
    rows = []
    for minute in range(1, horizon + 1):
        spread = 0.0025 * math.sqrt(minute)
        rows.append([clamp_price(last_price + z * spread) for z in Z_VALUES])
    return rows


def forecast_case(case):
    """One forecast entry per market of the case, in the case's order."""
    horizon = case["horizon_minutes"]
    forecasts = []
    for market in case["markets"]:
        try:
            rows = quantiles_for_market(market["prices"], horizon)
        except (ValueError, TypeError):
            prices = market.get("prices") or [0.5]
            rows = baseline_rows(prices[-1], horizon)
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
