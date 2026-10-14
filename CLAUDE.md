# Janyar Trade Strategy 2 — Project Guide

## Overview

EUR/USD trading strategy backtesting system. Reads daily candle data (`CANDLE_DATA_FILE` = `EURUSD1440.csv`, timeframe `1D`), detects 3-candle box-breakout signals, simulates each triggered trade at candle granularity, then scores and filters distance buckets by reward/risk ratio. Test bots run equity-curve backtests on the surviving filtered trades. The pipeline runs purely on daily candles — no 1-minute data is involved.

## Dependencies

```
pandas>=2.0.0
numpy>=1.24.0
```

Install: `pip install -r requirements.txt`

## Configuration

All shared constants live in `config.py` — change values there only:

| Constant               | Default            | Description                                                                     |
| ---------------------- | ------------------ | ------------------------------------------------------------------------------- |
| `SL_OFFSET`            | 0.00006            | Offset past the box boundary for the stop loss (EUR/USD: 0.6 pip)               |
| `MIN_RR`               | 1.0                | Minimum reward/risk ratio for a trade to count as a win                         |
| `DISTANCE_BUCKET_SIZE` | 0.0002             | Distance-bucket ruler: `bucket = floor(|entry − SL| / size)` (0.0002 = 2 pips)  |
| `NUM_WORKERS`          | 3                  | Legacy; step 1 now runs single-threaded on candle data                          |
| `CANDLE_TIMEFRAME`     | `1D`               | Candle timeframe of the strategy                                                |
| `CANDLE_DATA_FILE`     | `EURUSD1440.csv`   | Daily candle data the pipeline runs on (MT4-style export; format auto-detected) |
| `DATA_START`           | `2010-09-30 00:00` | Earliest bar kept (matches the start of `CANDLE_DATA_FILE`)                     |

`data_loader.py` provides the shared `load_ohlcv_csv`, which auto-detects the delimiter (tab / `;` / `,`), header vs no-header, and date format, so MT4-style exports and legacy semicolon/header files load identically.

## 7-Step Pipeline

Run steps in order. Each step depends on the previous one's output.

### Step 1 — Extract trades

```
python step1_extract.py
```

Loads `CANDLE_DATA_FILE` (daily candles) via `data_loader.load_ohlcv_csv`, detects 3-candle box breakouts, simulates each triggered trade forward on the same candles, writes all results to `trades.csv`. Runs in seconds — no resampling or multiprocessing involved.

Output columns: `date, time, day_of_week, type, entry, stop_loss, distance, max_profit, reward_risk, close_time`

### Step 2 — Group by distance

```
python step2_grouped.py
```

Reads `trades.csv`, groups by trade type (Buy/Sell) and integer distance bucket (`floor(distance / DISTANCE_BUCKET_SIZE)`), wipes and rebuilds `step2_grouped/`, then writes `step2_grouped/Buy_distance_N.csv` and `Sell_distance_N.csv` for each bucket.

### Step 3 — Filter by R/R threshold

```
python step3_filtered.py
```

For every R/R threshold present in the data, scores each distance-bucket file and keeps only files with `score > 0`. Wipes and rebuilds `step3_filtered/`, writes survivors to `step3_filtered/{threshold}/`. Creates `step3_filtered/surviving_files.csv` manifest (rows sorted by threshold, then direction + numeric distance).

Score formula: `(wins × threshold) - below_threshold_trades - SL_trades - floor(total/10)`

### Step 4 — Build date-ordered lists

```
python step4_lists.py
```

Merges all surviving files per threshold into a single chronologically sorted CSV. Wipes and rebuilds `step4_lists/`. Output: `step4_lists/list_rr_{T}.csv` for each threshold T.

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

| File                           | Candle        | Threshold    | R/R          | Risk         | Fee          | Output                            |
| ------------------------------ | ------------- | ------------ | ------------ | ------------ | ------------ | --------------------------------- |
| `test_bot.py`                  | pre-computed  | configurable | configurable | configurable | configurable | `test_bot_results.csv`            |
| `test_bot_1_25.py`             | pre-computed  | 25           | 1:25         | 0.04%        | 0.004%       | —                                 |
| `test_bot_risk_2.5.py`         | pre-computed  | 1            | 1:1          | fixed $500   | —            | —                                 |
| `1d_test_bot.py`               | 1D candle-sim | 4            | 1:4          | 0.5%         | 0.05%        | `1d_test_bot_results.csv`         |
| `production_ready_test_bot.py` | pre-computed  | configurable | configurable | configurable | configurable | `production_backtest_results.csv` |

**pre-computed** bots load trades directly from the filtered CSVs.
`1d_test_bot.py` runs entirely on `CANDLE_DATA_FILE` with the same candle-granularity logic as step 1, so it reproduces the pipeline's trades exactly (constants `THRESHOLD`, `WIN_RR`, `RISK_PCT`, `FEE_PCT` at the top of the file).
The former 1H/15M live-sim bots were retired: the EUR/USD base data has no 1-minute feed.

### Running a test bot

```
python 1d_test_bot.py
python production_ready_test_bot.py --help
```

## Folder Structure

```
project program/
├── config.py                    # All shared constants
├── data_loader.py               # Shared OHLCV CSV loader (format auto-detect)
├── requirements.txt
├── EURUSD1440.csv               # Daily candle input (MT4-style export)
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
├── 1d_test_bot.py
├── production_ready_test_bot.py
├── step2_grouped/               # Buy/Sell distance CSVs (all trades)
├── step3_filtered/              # Threshold subfolders (e.g. /2/, /5.1/)
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

Detection logic lives in `box_strategy.py` (shared by `step1_extract.py` and `1d_test_bot.py`).

- **Box**: three consecutive candles (overlapping/sliding window: candles `i-2, i-1, i`) whose colors match one of three models form a box spanning the highest high to the lowest low of the three (wicks, not bodies).
  - **Model 1 — alternating**: `bull,bear,bull` or `bear,bull,bear` (no extra rule).
  - **Model 2 — one adjacent same-color pair** (e.g. `bull,bull,bear`): the pair's 2nd candle close must not pass the 1st candle's wick extreme (bull pair → 2nd close ≤ 1st high; bear pair → 2nd close ≥ 1st low).
  - **Model 3 — all same color** (`bull,bull,bull` / `bear,bear,bear`): 2nd close within 1st's wick extreme **and** 3rd close within 2nd's wick extreme.
- **Breakout**: only the **immediately-next candle** (`i+1`) may trigger entry:
  - **Buy**: price reaches `box_top` → entry = `box_top`, SL = `box_bottom − SL_OFFSET`
  - **Sell**: price reaches `box_bottom` → entry = `box_bottom`, SL = `box_top + SL_OFFSET`
  - Pipeline + `1d_test_bot.py` (candle granularity, `find_breakout_candle`): if the breakout candle pierces **both** levels, its open decides (open gapped beyond a level → that side triggered first); an open inside the box leaves the order unknown → skipped. If neither level is reached, no trade.
- **Distance bucket**: `floor(|entry − stop_loss| / DISTANCE_BUCKET_SIZE)` — used to group and filter trades (0.0002 = 2 pips for EUR/USD)
- **Win condition**: price reaches `entry ± (WIN_RR × distance)` before hitting stop loss
- Trade simulation scans candles (pipeline/1D bot: `simulate_trade_candles`) forward from the **breakout candle**; the favorable extreme of the SL-hit candle itself is excluded, since intra-candle order is unknown

## Key Notes

- Bars before `DATA_START` (config.py, currently `2010-09-30 00:00`) are dropped
- The test bot's `step3_filtered/{THRESHOLD}/` folder must be populated (steps 1–3) before running it
- Step 1 runs single-threaded on the candle data; `NUM_WORKERS` is legacy and unused
- Distance buckets use `DISTANCE_BUCKET_SIZE` (0.0002 = 2 pips); `reward_risk` is a scale-free ratio and is unaffected by the unit change
- The matrix number in step 7 is the primary selection criterion — higher is better

<!-- project finished(checking the contribution of github) -->
