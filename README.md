# FAA attribution forecaster v2 — polymarket-faa-attribution-02

A fast-adapting quantile forecaster for Polymarket's FAA outage
attribution family: at each checkpoint it forecasts every market's Yes
price at every minute of the next 4 hours as five quantiles
(5%, 25%, 50%, 75%, 95%), scored by mean pinball loss.

## How it works

Per market, independently, from that market's own 1-minute price grid:

- **Median = the checkpoint price, with a gentle contender fade.**
  Markets priced 0.10–0.40 at the checkpoint drift down by roughly
  0.015–0.022 over the next four hours on the practice data, while
  markets under 0.10 drift by ~0.000, so the median of a market above
  0.05 sags by 0.005 price units per hour per unit of (price − 0.05).
  The shift is small — at most 0.005 at the four-hour mark for a 0.30
  market. Extrapolating recent momentum still made the loss worse in
  every configuration tried, as did pulling toward the recent mean, so
  the fade is the only drift in the forecast.
- **Spread = the market's own recent volatility, tracked fast.**
  An exponentially weighted mean of absolute one-minute returns over
  the last 120 minutes with a **15-minute half-life** (v1 used 80),
  scaled by 1.2533 into a standard deviation, floored at 0.0004 and
  capped at 0.01 price units per square-root minute. These prices move
  in jumps — 88% of one-minute returns are exactly zero, the 99th
  percentile of the absolute move is 0.045 — so a slow volatility
  estimate is wrong in both directions: it stays wide long after a
  jump has passed and narrow while a fresh jump unfolds. The loss
  falls monotonically as the half-life shortens from 320 to 15 minutes
  and rises again below 10, so 15 sits in a flat valley (12–20 all
  score within 0.001 of each other).
- **Spread grows with the square root of the horizon** (random-walk
  shape): `q = center(h) + z_tau * sigma * sqrt(h)`, clamped to
  `[0, 1]`, rounded to 6 decimals, rows forced non-decreasing.

Things tried and rejected on the practice data: widening the outer
quantiles (helps alone, hurts once the fast volatility is in),
forecasting in log-odds space (much worse), scaling the spread by
`sqrt(p(1-p))` (much worse), a jump allowance from the short-window
mean absolute move (worse), plain short-window volatility with no
decay (worse), and any momentum or mean-reversion drift (worse).

## Local practice score

Scored locally on practice cases p00–p04 (each case's actuals taken
from the next case's price grid; p05 has no later case to score
against):

| entry | pinball loss | coverage_90 |
| --- | --- | --- |
| house baseline (fixed 0.0025 spread) | 0.3925 | 0.9382 |
| v1 (half-life 80, no drift) | 0.3243 | 0.8358 |
| **v2 (half-life 15, contender fade)** | **0.3172** | **0.8680** |

About 2.2% better than v1 and 19% better than the baseline on the
same cases; per-case losses 0.5141 / 0.3129 / 0.3722 / 0.2313 / 0.2036
(v1: 0.5328 / 0.3247 / 0.3698 / 0.2318 / 0.2114). The official
six-case baseline is 0.363589 and v1's official loss was 0.284405, so
v2's expected official score is around 0.277–0.281. The practice is
cut from the NVIDIA CEO event, not the FAA family, so the practice
score is no guide to the final — the point is only that the
forecaster beats the house baseline it must beat to take a prize, and
that v2's two changes (fast volatility tracking for jump-driven
prices, a mild contender fade) are structural, not tuned to the
practice cases' particular news shocks.

## Running it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Python 3.13, standard library only, no network, deterministic. Reads
every `*.in` file in the input directory and writes one `<id>.out` per
case: `{"forecasts": [{"id": ..., "q": [[...] x 240]}]}`.

## Files

- `main.py` — the forecaster (the entrypoint)
- `README.md` — this file
- `LICENSE` — MIT
- `.makefun/owner.json` — payout wallet claim file
