# Janyar Trade Strategy 2 — Project Guide

## Overview

Gold (XAU) trading strategy backtesting system. Reads raw 1-minute OHLCV data, resamples to `CANDLE_TIMEFRAME` candles (default 4-hour), simulates one trade per candle close (Buy if candle closed up, Sell if it closed down), then scores and filters distance buckets by reward/risk ratio. Test bots run equity-curve backtests on the surviving filtered trades.

## Dependencies

```
pandas>=2.0.0
numpy>=1.24.0
```

Install: `pip install -r requirements.txt`

## Configuration

All shared constants live in `config.py` — change values there only:

| Constant        | Default           | Description                                                        |
| --------------- | ----------------- | ------------------------------------------------------------------ |
| `ENTRY_OFFSET`  | 0.3               | Pip offset added/subtracted from close price for entry             |
| `SL_OFFSET`     | 0.3               | Pip offset added to low (Buy SL) or subtracted from high (Sell SL) |
| `MIN_RR`        | 1.0               | Minimum reward/risk ratio for a trade to count as a win            |
| `NUM_WORKERS`   | 3                 | Parallel CPU cores used in step 1 simulation                       |
| `CANDLE_TIMEFRAME` | `4h`           | Resample timeframe + breakout-window size (`15min` restores old behavior) |
| `RAW_DATA_FILE` | `XAU_1m_data.csv` | Input 1-minute candle data                                         |

## 7-Step Pipeline

Run steps in order. Each step depends on the previous one's output.

### Step 1 — Extract trades

```
python step1_extract.py
```

Loads `XAU_1m_data.csv`, resamples to `CANDLE_TIMEFRAME` candles (default 4H), simulates one trade per candle (multiprocessing), writes all results to `trades.csv`.

Output columns: `date, time, day_of_week, type, entry, stop_loss, distance, max_profit, reward_risk, close_time`

### Step 2 — Group by distance

```
python step2_grouped.py
```

Reads `trades.csv`, groups by trade type (Buy/Sell) and integer distance bucket, writes `step2_grouped/Buy_distance_N.csv` and `Sell_distance_N.csv` for each bucket.

### Step 3 — Filter by R/R threshold

```
python step3_filtered.py
```

For every R/R threshold present in the data, scores each distance-bucket file and keeps only files with `score > 0`. Writes survivors to `step3_filtered/{threshold}/`. Creates `step3_filtered/surviving_files.csv` manifest.

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
| `production_ready_test_bot.py` | pre-computed | configurable | configurable | configurable | configurable | `production_backtest_results.csv` |

**pre-computed** bots load trades directly from the filtered CSVs.
**live-sim** bots (`1h_test_bot.py`, `15m_test_bot.py`) re-read raw 1M data, resample, and re-simulate every trade — giving an independent verification pass.

### Running a test bot

```
python 15m_test_bot.py
python 1h_test_bot.py
python production_ready_test_bot.py --help
```

## Folder Structure

```
project program/
├── config.py                    # All shared constants
├── requirements.txt
├── XAU_1m_data.csv              # Raw input (~348 MB)
├── XAU_15m_data.csv             # Pre-resampled 15M data
├── XAU_1h_data.csv              # Pre-resampled 1H data
├── XAU_4h_data.csv              # Pre-resampled 4H data
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

Detection logic lives in `box_strategy.py` (shared by `step1_extract.py`, `15m_test_bot.py`, `1h_test_bot.py`).

- **Box**: three consecutive candles (overlapping/sliding window: candles `i-2, i-1, i`) whose colors match one of three models form a box spanning the highest high to the lowest low of the three (wicks, not bodies).
  - **Model 1 — alternating**: `bull,bear,bull` or `bear,bull,bear` (no extra rule).
  - **Model 2 — one adjacent same-color pair** (e.g. `bull,bull,bear`): the pair's 2nd candle close must not pass the 1st candle's wick extreme (bull pair → 2nd close ≤ 1st high; bear pair → 2nd close ≥ 1st low).
  - **Model 3 — all same color** (`bull,bull,bull` / `bear,bear,bear`): 2nd close within 1st's wick extreme **and** 3rd close within 2nd's wick extreme.
  - A candle with `close == open` (doji) invalidates the triple.
- **Breakout**: only the **immediately-next candle** (`i+1`) may trigger entry. Within its 1M bars, the first bar to reach a breakout level opens the trade:
  - **Buy**: price reaches `box_top + ENTRY_OFFSET` → entry = `box_top + ENTRY_OFFSET`, SL = `box_bottom − SL_OFFSET`
  - **Sell**: price reaches `box_bottom − ENTRY_OFFSET` → entry = `box_bottom − ENTRY_OFFSET`, SL = `box_top + SL_OFFSET`
  - If a single 1M bar reaches both levels (engulfing), the signal is ambiguous and skipped; otherwise the earlier-reached level wins. If neither level is reached, no trade.
- **Distance bucket**: `floor(|entry − stop_loss|)` — used to group and filter trades
- **Win condition**: price reaches `entry ± (WIN_RR × distance)` before hitting stop loss
- Trade simulation scans 1M bars forward from the **breakout (entry) bar**

## Key Notes

- Data starts from `2011-01-03 04:00` (earlier bars are dropped)
- `step3_filtered/823/` must be populated before running `15m_test_bot.py`
- Increase `NUM_WORKERS` in `config.py` to speed up step 1 (uses Python multiprocessing)
- The matrix number in step 7 is the primary selection criterion — higher is better
