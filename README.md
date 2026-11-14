# FAA attribution forecaster — polymarket-faa-attribution-02

A volatility-adaptive quantile forecaster for Polymarket's FAA outage
attribution family: at each checkpoint it forecasts every market's Yes
price at every minute of the next 4 hours as five quantiles
(5%, 25%, 50%, 75%, 95%), scored by mean pinball loss.

## How it works

Per market, independently, from that market's own 1-minute price grid:

- **Median = the checkpoint price.** No drift. On the practice data,
  extrapolating recent momentum made the loss worse in every
  configuration tried (shrink 0.3 and 0.6 both lost to shrink 0.0), so
  the forecast carries no trend: at this horizon these prices
  mean-revert faster than they trend.
- **Spread = the market's own recent volatility.** An exponentially
  weighted mean of absolute one-minute returns over the last 120 minutes
  (half-life 80 minutes), scaled by 1.2533 into a standard deviation,
  floored at 0.0004 and capped at 0.01 price units per square-root
  minute. A market that has been jumping gets wide quantiles; a quiet
  one gets narrow ones. The house baseline's fixed 0.0025 spread does
  neither.
- **Spread grows with the square root of the horizon** (random-walk
  shape): `q = x + z_tau * sigma * sqrt(h)`, clamped to [0, 1], rounded
  to 6 decimals, rows forced non-decreasing.

## Local practice score

Scored locally on practice cases p00–p04 (each case's actuals taken from
the next case's price grid; p05 has no later case to score against):

| entry | pinball loss |
| --- | --- |
| house baseline (fixed 0.0025 spread) | 0.3925 |
| this forecaster | **0.3243** |

About 17% better than the baseline on the same cases. The official
six-case baseline is 0.363589. The practice is cut from the NVIDIA CEO
event, not the FAA family, so the practice score is no guide to the
final — the point is only that the forecaster beats the house baseline
it must beat to take a prize.

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
