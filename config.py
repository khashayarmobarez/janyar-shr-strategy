# All shared constants. Change values here only.

# Box-breakout model (see strategy.md / box_strategy.py):
#   SL_OFFSET = distance past the opposite box boundary for the stop loss
#               (Buy SL = box_bottom - SL_OFFSET, Sell SL = box_top + SL_OFFSET).
#   EUR/USD scale: 0.00008 is 0.8 pip.
SL_OFFSET       = 0.00008
MIN_RR          = 1.0

# Ruler for distance-bucket grouping (step2_grouped.py, 1d_test_bot.py):
#   bucket = floor(|entry - stop_loss| / DISTANCE_BUCKET_SIZE)
#   0.0004 == 4 pips for EUR/USD. (Gold used 1.0 == 1 dollar.)
DISTANCE_BUCKET_SIZE = 0.0003


PENALTY_PER_N_TRADES        = 10
NUM_WORKERS                 = 3   # parallel CPU cores (legacy; step1 now runs single-threaded on candle data)

# Candle timeframe of the strategy. A pandas offset alias accepted by both
# df.resample(...) and pd.Timedelta(...).
CANDLE_TIMEFRAME    = "1D"

# Daily candle data the pipeline runs on. EURUSD1440.csv is an MT4-style daily
# export: tab-separated, no header, "%Y-%m-%d %H:%M" timestamps, spanning
# 2010-09-30 -> present. step1 and 1d_test_bot.py read this file directly via
# data_loader.load_ohlcv_csv.
CANDLE_DATA_FILE    = "EURUSD1440.csv"

# Earliest bar to keep. Bars before this timestamp are dropped during
# extraction (step1) and in the test bots. CANDLE_DATA_FILE begins 2010-09-30,
# so "2010-09-30 00:00" keeps everything available.
DATA_START          = "2010-09-30 00:00"

RAW_TRADES_FILE     = "trades.csv"
GROUPED_FOLDER      = "step2_grouped"
FILTERED_FOLDER     = "step3_filtered"
LISTS_FOLDER        = "step4_lists"
RESCORE_FILE        = "step5_rescore_summary.csv"
DRAWDOWN_FILE       = "step6_drawdown_summary.csv"
MATRIX_FILE         = "step7_matrix_summary.csv"
