# Handoff — Janyar Trade Strategy 2 (XAU Box-Breakout)

## TL;DR — current state

- Strategy runs on **daily** candles from `XAUUSD1440.csv` (MT4-style export, loaded directly — no resampling needed).
- **The pipeline outputs on disk are STALE**: they come from an experimental *weekly* run (`trades.csv` = 216 weekly trades, 258 thresholds). The daily pipeline has **not** been re-run since the config change. **Run `python run_pipeline.py` before trusting any backtest.**
- Client deliverable: `step3_filtered/surviving_files.csv` has been sorted (threshold ascending, then natural distance order). The `1.1` block contains 99 surviving buckets.

## Data files

| File | Role | Notes |
| --- | --- | --- |
| `XAUUSD1440.csv` | **Active candle input** | Daily (1440 min). Tab-separated, **no header**, `%Y-%m-%d %H:%M`. 5,218 bars, 2009-12-08 → 2026-09-15. Bars on Sun–Fri (no Saturday). |
| `XAU_1m_data.csv` | Raw 1-minute | ~348 MB. Used **only** by `1h_test_bot.py` / `15m_test_bot.py` (they resample it internally). |
| `XAU_1d/4h/1h/15m_data.csv` | Legacy pre-resampled | Not used by the active pipeline. |
| `XAU_1w_data.csv` | Weekly experiment artifact | Generated during the weekly trial; unused by the current daily config. |

## Config (`config.py`)

| Constant | Value | Notes |
| --- | --- | --- |
| `SL_OFFSET` | `0.3` | Pip offset past the box for the stop loss |
| `MIN_RR` | `1.0` | Minimum R/R for a trade to count as a win |
| `CANDLE_TIMEFRAME` | `"1D"` | Strategy candle timeframe |
| `CANDLE_DATA_FILE` | `"XAUUSD1440.csv"` | Loaded by `data_loader.load_ohlcv_csv` (auto-detects format) |
| `DATA_START` | `"2009-12-08 00:00"` | Earliest bar kept (matches the file start) |
| `RAW_DATA_FILE` | `"XAU_1m_data.csv"` | Only for the 1H/15M live-sim bots |

## Key code changes (committed as `7a40539 "new raw data"`)

- **`data_loader.py` (new, shared)** — `load_ohlcv_csv(filepath, apply_start=True)` auto-detects delimiter (tab/`;`/`,`), header vs no-header, and date format (`%Y-%m-%d %H:%M`, `%Y.%m.%d %H:%M`, date-only). Also exposes `resample_ohlcv(df, timeframe)`.
- **`step1_extract.py` + `1d_test_bot.py`** — now import the shared loader (local duplicated loaders removed).
- **`step2_grouped.py`, `step3_filtered.py`, `step4_lists.py`** — output folders are wiped + rebuilt each run (`shutil.rmtree`), so reruns never mix stale data from an older dataset/timeframe.
- **`step3_filtered.py`** — `write_manifest` now sorts `surviving_files.csv` / `removed_files.csv` by threshold ascending, then by direction + numeric distance (`Buy_distance_9` < `Buy_distance_25` < `Buy_distance_111`). (Re-applied after a rollback — was previously only sorted manually.)
- **`test_bot.py`** — tuned parameters: `THRESHOLD = 5.1`, `WIN_RR = 5.1`, `RISK_PCT = 0.0263` (2.63%), `FEE_PCT = 0.00263` (0.263%), start $15,000.

## Running the pipeline

```powershell
$env:PYTHONIOENCODING="utf-8"; python run_pipeline.py
```

- `PYTHONIOENCODING` is required because the script prints `→` (cp1252 console can't encode it).
- Steps 1 → 7 in order: extract trades → group by distance bucket → filter by R/R threshold (writes `step3_filtered/{T}/` + manifests) → date-ordered lists → re-score → drawdown → matrix.
- Step 3 is the slow part (sweeps every threshold × every bucket file).
- Steps 2/3/4 wipe their folders first; steps 5/6/7 overwrite their summary CSVs.

## Test bots

| File | Candle | Threshold | R/R | Risk | Fee | Output |
| --- | --- | --- | --- | --- | --- | --- |
| `test_bot.py` | pre-computed | 5.1 (tuned) | 1:5.1 | 2.63% | 0.263% | `test_bot_results.csv` |
| `test_bot_1_25.py` | pre-computed | 25 | 1:25 | 0.04% | 0.004% | — |
| `test_bot_risk_2.5.py` | pre-computed | 1 | 1:1 | fixed $500 | — | — |
| `1h_test_bot.py` | 1H live-sim | 4 | 1:4 | 0.5% | 0.05% | `1h_test_bot_results.csv` |
| `15m_test_bot.py` | 15M live-sim | 823 | 1:823 | 0.002% | 0.0002% | `15m_test_bot_results.csv` |
| `1d_test_bot.py` | candle-sim (`CANDLE_DATA_FILE`) | 4 | 1:4 | 0.5% | 0.05% | `1d_test_bot_results.csv` |
| `production_ready_test_bot.py` | pre-computed | configurable | configurable | configurable | configurable | `production_backtest_results.csv` |

- **pre-computed** bots read trades from `step3_filtered/{THRESHOLD}/` — they need the pipeline (steps 1–3) run first.
- **live-sim** bots (`1h`, `15m`) re-read `XAU_1m_data.csv`, resample, and re-simulate — independent verification pass.
- `1d_test_bot.py` reproduces the pipeline's candle-granularity logic on `CANDLE_DATA_FILE`.

## Client deliverable

- `step3_filtered/surviving_files.csv` — sorted, one `threshold,filename` row per surviving bucket.
- Threshold `1.1` → 99 rows (61 Buy: distances 22–313; 38 Sell: distances 29–423).
- The next pipeline run regenerates it sorted automatically (step3 fix re-applied).

## Caveats / gotchas

- **Stale outputs right now**: `trades.csv`, `step2_grouped/`, `step3_filtered/`, `step4_lists/`, step5–7 summaries all reflect the weekly experiment, not the current daily config. Re-run the pipeline.
- **`inf` in `step7_matrix_summary.csv`**: `matrix_number = (10 / |lowest_drawdown|) × score`; when a threshold has zero losses, `lowest_drawdown = 0` → division by zero → `inf`. These rows are degenerate — do not treat them as the best candidate; use the highest finite `matrix_number`.
- `test_bot.py`'s `THRESHOLD = 5.1` was tuned on an earlier daily run — re-check it against the freshly regenerated step7 matrix.
- Do not re-point `CANDLE_DATA_FILE` at a weekly file unless you also generate it (`data_loader.resample_ohlcv` can produce one; a standalone `resample_data.py` existed during the weekly experiment but was removed).
- Git working tree is clean; last commit `7a40539` ("new raw data").

## Suggested next steps

1. `$env:PYTHONIOENCODING="utf-8"; python run_pipeline.py` (regenerates all outputs for daily data).
2. Inspect `step7_matrix_summary.csv` (skip `inf` rows) and choose the threshold to trade.
3. Set `THRESHOLD` / `WIN_RR` in `test_bot.py` to match, then run `python test_bot.py`.
4. Filter `surviving_files.csv` for the chosen threshold to hand the client their bucket list.