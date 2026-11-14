# FAA attribution forecaster v3 — polymarket-faa-attribution-02

A quantile forecaster for Polymarket's FAA outage attribution family:
at each checkpoint it forecasts every market's Yes price at every
minute of the next 4 hours as five quantiles (5%, 25%, 50%, 75%, 95%),
scored by mean pinball loss.

## What v3 changes

One thing, and one thing only: the shape of the forecast at the
inner quantiles.

Jump-driven prices are not normal. In the practice data 88% of the
one-minute returns are exactly zero, the 99th percentile of the
absolute move is 0.045, and the largest is 0.48. A future price is
the sum of many such moves, so its distribution is peaked: most of
the mass sits at or near the median, and the interquartile range is
narrower than a normal with the same spread would claim. v2 drew the
25%/75% quantiles at the normal z-scores of ±0.674; v3 draws them at
**±0.40**. The 5%/95% quantiles keep the normal ±1.645 — the tails
are where the jumps live, and moving them either way only made the
loss worse.

The evidence is broad. The narrower inner shape cuts the local
practice loss from 0.317242 to 0.312612, with 3 of 5 cases improving
and the other two flat or worse by a hair; leaving any one case out,
the gain survives in 4 of 5 folds (the mean over p01–p04 improves
from 0.2800 to 0.2720). At the market level 59 of 104 (case, market)
pairs improve, and a paired bootstrap puts the chance the improvement
is real at 0.87. The optimum is flat (0.35, 0.40 and 0.45 all land
within 0.001), so the choice is not a knife-edge fit to six practice
cases. v3's expected official score is around 0.275, against v2's
0.278821.

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
  capped at 0.01 price units per square-root minute. A slow volatility
  estimate is wrong in both directions on jump-driven prices: it stays
  wide long after a jump has passed and narrow while a fresh jump
  unfolds. The loss falls monotonically as the half-life shortens from
  320 to 15 minutes and rises again below 10, so 15 sits in a flat
  valley (12–20 all score within 0.001 of each other).
- **Spread grows with the square root of the horizon** (random-walk
  shape): `q = center(h) + z_tau * sigma * sqrt(h)`, clamped to
  `[0, 1]`, rounded to 6 decimals, rows forced non-decreasing. The
  inner z-scores are ±0.40, the outer ±1.645.

Things tried and rejected, across v2 and v3: asymmetric up/down
volatility (much worse), a per-market adaptive sigma floor (worse),
per-market half-lives by jump rate (no change), widening the outer
quantiles (helps alone, hurts once the fast volatility is in),
forecasting in log-odds space (much worse), scaling the spread by
`sqrt(p(1-p))` (much worse), a jump allowance from the short-window
mean absolute move (worse), plain short-window volatility with no
decay (worse), any momentum or mean-reversion drift (worse), a
stronger contender fade (wins the practice mean only through the
opening case and loses on the established cases — it would not travel
to the final), and renormalizing the medians across markets to a
sum-to-one constraint (the practice sums drift too much for it to
hold, and it made the loss worse).

## Local practice score

Scored locally on practice cases p00–p04 (each case's actuals taken
from the next case's price grid; p05 has no later case to score
against):

| entry | pinball loss | coverage_90 |
| --- | --- | --- |
| house baseline (fixed 0.0025 spread) | 0.3925 | 0.9382 |
| v1 (half-life 80, no drift) | 0.3243 | 0.8358 |
| v2 (half-life 15, contender fade) | 0.3172 | 0.8680 |
| **v3 (v2 + peaked inner quantiles)** | **0.3126** | **0.8680** |

About 1.5% better than v2, 3.6% better than v1, and 20% better than
the baseline on the same cases; per-case losses 0.5232 / 0.3136 /
0.3500 / 0.2244 / 0.2001 (v2: 0.5141 / 0.3129 / 0.3722 / 0.2313 /
0.2036). The official six-case baseline is 0.363589 and v2's official
loss was 0.278821, so v3's expected official score is around 0.275.
The practice is cut from the NVIDIA CEO event, not the FAA family, so
the practice score is no guide to the final — the point is only that
the forecaster beats the house baseline it must beat to take a prize,
and that v3's one change (a peaked inner shape for jump-driven
grids) is a property of Polymarket's price grids in general, not of
the practice event's particular news shocks.

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
