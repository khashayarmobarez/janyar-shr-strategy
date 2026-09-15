# Janyar Trade Strategy 2 — Project Guide

## Overview

Gold (XAU) trading strategy backtesting system. Reads pre-resampled `CANDLE_TIMEFRAME` candle data (`CANDLE_DATA_FILE`, currently **weekly `1W`**), detects 3-candle box-breakout signals, simulates each triggered trade at candle granularity, then scores and filters distance buckets by reward/risk ratio. Test bots run equity-curve backtests on the surviving filtered trades. The raw 1-minute file is only needed by the 1H/15M live-sim bots.

The daily base file is `XAUUSD1440.csv` (MT4-style export). Any coarser timeframe is produced from it by `resample_data.py` into a `XAU_*_data.csv` file; the pipeline itself never resamples.

## Dependencies

```
pandas>=2.0.0
numpy>=1.24.0
```

Install: `pip install -r requirements.txt`

## Configuration

All shared constants live in `config.py` — change values there only:

| Constant           | Default           | Description                                                                    |
| ------------------ | ----------------- | ------------------------------------------------------------------------------ |
| `SL_OFFSET`        | 0.3               | Pip offset added to low (Buy SL) or subtracted from high (Sell SL)             |
| `MIN_RR`           | 1.0               | Minimum reward/risk ratio for a trade to count as a win                        |
| `NUM_WORKERS`      | 3                 | Legacy; step 1 now runs single-threaded on candle data                         |
| `CANDLE_TIMEFRAME` | `1W`              | Candle timeframe of the strategy                                               |
| `CANDLE_DATA_FILE` | `XAU_1w_data.csv` | Pre-resampled candle data the pipeline runs on (must match `CANDLE_TIMEFRAME`) |
| `DATA_START`       | `2009-12-06 00:00`| Earliest bar kept (matches the first weekly bin of the base data)              |
| `RAW_DATA_FILE`    | `XAU_1m_data.csv` | 1-minute data (only used by the 1H/15M live-sim bots)                          |

## Resampling / switching timeframe

`XAUUSD1440.csv` is the daily base. Regenerate the pipeline's candle file with:

```
python resample_data.py                    # 1W  -> XAU_1w_data.csv (default)
python resample_data.py 4h XAU_4h_data.csv # custom timeframe -> output file
```

Then set `CANDLE_TIMEFRAME` and `CANDLE_DATA_FILE` in `config.py` to match. Weekly bins are
Sunday-to-Saturday (`label="left", closed="left"`), i.e. first-open / highest-high / lowest-low /
last-close per trading week. The loader (`data_loader.py`) auto-detects delimiters, headers, and
date formats, so both the MT4-style base file and the generated `XAU_*_data.csv` files load.

## 7-Step Pipeline

Run steps in order. Each step depends on the previous one's output.

### Step 1 — Extract trades

```
python step1_extract.py
```

Loads `CANDLE_DATA_FILE` (weekly candles) directly, detects 3-candle box breakouts, simulates each triggered trade forward on the same candles, writes all results to `trades.csv`. Runs in seconds — no 1-minute data, resampling, or multiprocessing involved.

Output columns: `date, time, day_of_week, type, entry, stop_loss, distance, max_profit, reward_risk, close_time`

### Step 2 — Group by distance

```
python step2_grouped.py
```

Reads `trades.csv`, groups by trade type (Buy/Sell) and integer distance bucket, writes `step2_grouped/Buy_distance_N.csv` and `Sell_distance_N.csv` for each bucket. `step2_grouped/` is wiped and rebuilt each run, so switching datasets/timeframes leaves no stale buckets behind.

### Step 3 — Filter by R/R threshold

```
python step3_filtered.py
```

For every R/R threshold present in the data, scores each distance-bucket file and keeps only files with `score > 0`. Writes survivors to `step3_filtered/{threshold}/` (rebuilt from scratch each run). Creates `step3_filtered/surviving_files.csv` manifest.

Score formula: `(wins × threshold) - below_threshold_trades - SL_trades - floor(total/10)`

### Step 4 — Build date-ordered lists

```
python step4_lists.py
```

Merges all surviving files per threshold into a single chronologically sorted CSV. Output: `step4_lists/list_rr_{T}.csv` for each threshold T.

### Step 5 — Re-score lists

```
python step5_rescore.py
```

Applies the same scoring formula to each merged list. Output: `step5_rescore_summary.csv`.

### Step 6 — Drawdown analysis

```
python step6_drawdown.py
```

Computes the lowest drawdown starting point for each threshold list. Uses cumulative sum + suffix minimum for efficiency. Output: `step6_drawdown_summary.csv`.

### Step 7 — Combine into matrix

```
python step7_combine.py
```

Joins step 5 and step 6 outputs, computes `matrix_number = (10 / |lowest_drawdown|) × score`. Output: `step7_matrix_summary.csv`. Use this matrix to decide which threshold to trade.

## Test Bots

All test bots load distance buckets from `step3_filtered/{threshold}/`, simulate trades on candle signals, and run an equity-curve backtest.

| File                           | Candle       | Threshold    | R/R          | Risk         | Fee          | Output                            |
| ------------------------------ | ------------ | ------------ | ------------ | ------------ | ------------ | --------------------------------- |
| `test_bot.py`                  | pre-computed | configurable | configurable | configurable | configurable | `test_bot_results.csv`            |
| `test_bot_1_25.py`             | pre-computed | 25           | 1:25         | 0.04%        | 0.004%       | —                                 |
| `test_bot_risk_2.5.py`         | pre-computed | 1            | 1:1          | fixed $500   | —            | —                                 |
| `1h_test_bot.py`               | 1H live-sim  | 4            | 1:4          | 0.5%         | 0.05%        | `1h_test_bot_results.csv`         |
| `15m_test_bot.py`              | 15M live-sim | 823          | 1:823        | 0.002%       | 0.0002%      | `15m_test_bot_results.csv`        |
| `1d_test_bot.py`               | candle-sim   | 4            | 1:4          | 0.5%         | 0.05%        | `1d_test_bot_results.csv`         |
| `production_ready_test_bot.py` | pre-computed | configurable | configurable | configurable | configurable | `production_backtest_results.csv` |

**pre-computed** bots load trades directly from the filtered CSVs.
`test_bot.py` is timeframe-agnostic: it consumes whatever steps 1–7 produced. If its configured `THRESHOLD` folder is absent (e.g. after switching to weekly `1W`), it auto-selects the best **finite** `matrix_number` from `step7_matrix_summary.csv` whose folder exists (degenerate `inf` rows are skipped).
**live-sim** bots (`1h_test_bot.py`, `15m_test_bot.py`) re-read raw 1M data, resample, and re-simulate every trade — giving an independent verification pass.
`1d_test_bot.py` runs entirely on `CANDLE_DATA_FILE` (currently weekly `1W`) with the same candle-granularity logic as step 1, so it reproduces the pipeline's trades exactly and needs no 1M data (constants `THRESHOLD`, `WIN_RR`, `RISK_PCT`, `FEE_PCT` at the top of the file).

### Running a test bot

```
python 15m_test_bot.py
python 1h_test_bot.py
python 1d_test_bot.py
python production_ready_test_bot.py --help
```

## Folder Structure

```
project program/
├── config.py                    # All shared constants
├── requirements.txt
├── XAUUSD1440.csv               # Daily base (MT4-style export)
├── XAU_1w_data.csv              # Pre-resampled weekly data (active pipeline input)
├── XAU_1m_data.csv              # Raw 1-minute input (~348 MB; 1H/15M bots only)
├── XAU_15m_data.csv             # Pre-resampled 15M data
├── XAU_1h_data.csv              # Pre-resampled 1H data
├── XAU_4h_data.csv              # Pre-resampled 4H data
├── XAU_1d_data.csv              # Pre-resampled 1D data (legacy; not the active input)
├── resample_data.py             # Build XAU_*_data.csv from the daily base
├── data_loader.py               # Auto-detecting OHLCV loader + resampler
├── trades.csv                   # Step 1 output
├── step1_extract.py
├── step2_grouped.py
├── step3_filtered.py
├── step4_lists.py
├── step5_rescore.py
├── step6_drawdown.py
├── step7_combine.py
├── test_bot.py
├── test_bot_1_25.py
├── test_bot_risk_2.5.py
├── 1h_test_bot.py
├── 15m_test_bot.py
├── 1d_test_bot.py
├── production_ready_test_bot.py
├── step2_grouped/               # Buy/Sell distance CSVs (all trades)
├── step3_filtered/              # Threshold subfolders (e.g. /2/, /823/)
│   ├── surviving_files.csv
│   └── {threshold}/
│       ├── Buy_distance_N.csv
│       └── Sell_distance_N.csv
├── step4_lists/                 # list_rr_{T}.csv per threshold
├── step5_rescore_summary.csv
├── step6_drawdown_summary.csv
└── step7_matrix_summary.csv
```

## Trade Logic — 3-candle box breakout

Detection logic lives in `box_strategy.py` (shared by `step1_extract.py`, `1d_test_bot.py`, `15m_test_bot.py`, `1h_test_bot.py`).

- **Box**: three consecutive candles (overlapping/sliding window: candles `i-2, i-1, i`) whose colors match one of three models form a box spanning the highest high to the lowest low of the three (wicks, not bodies).
  - **Model 1 — alternating**: `bull,bear,bull` or `bear,bull,bear` (no extra rule).
  - **Model 2 — one adjacent same-color pair** (e.g. `bull,bull,bear`): the pair's 2nd candle close must not pass the 1st candle's wick extreme (bull pair → 2nd close ≤ 1st high; bear pair → 2nd close ≥ 1st low).
  - **Model 3 — all same color** (`bull,bull,bull` / `bear,bear,bear`): 2nd close within 1st's wick extreme **and** 3rd close within 2nd's wick extreme.
- **Breakout**: only the **immediately-next candle** (`i+1`) may trigger entry:
  - **Buy**: price reaches `box_top` → entry = `box_top`, SL = `box_bottom − SL_OFFSET`
  - **Sell**: price reaches `box_bottom` → entry = `box_bottom`, SL = `box_top + SL_OFFSET`
  - Pipeline + `1d_test_bot.py` (candle granularity, `find_breakout_candle`): if the breakout candle pierces **both** levels, its open decides (open gapped beyond a level → that side triggered first); an open inside the box leaves the order unknown → skipped. If neither level is reached, no trade.
  - 1H/15M live-sim bots (`find_breakout`): within the breakout candle's 1M bars, the first bar to reach a level opens the trade; a single 1M bar reaching both levels is ambiguous and skipped.
- **Distance bucket**: `floor(|entry − stop_loss|)` — used to group and filter trades
- **Win condition**: price reaches `entry ± (WIN_RR × distance)` before hitting stop loss
- Trade simulation scans candles (pipeline/`1d_test_bot.py`: `simulate_trade_candles`) or 1M bars (1H/15M bots) forward from the **breakout candle**; the favorable extreme of the SL-hit candle itself is excluded, since intra-candle order is unknown

## Key Notes

- Bars before `DATA_START` (config.py, currently `2009-12-06 00:00`) are dropped
- To switch timeframe: `python resample_data.py`, point `CANDLE_TIMEFRAME`/`CANDLE_DATA_FILE` at the result, then re-run the whole pipeline (steps 2–4 self-clean stale outputs)
- The test bot's `step3_filtered/{THRESHOLD}/` folder must be populated (steps 1–3) before running it
- Step 1 runs single-threaded on the candle data; `NUM_WORKERS` is legacy and unused
- The matrix number in step 7 is the primary selection criterion — higher is better; `inf` rows (zero drawdown ⇒ division by zero) are degenerate and skipped by `test_bot.py`

<!-- project finished(checking the contribution of github) -->
