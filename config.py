# All shared constants. Change values here only.

# Box-breakout model (see strategy.md / box_strategy.py):
#   SL_OFFSET = distance past the opposite box boundary for the stop loss
#               (Buy SL = box_bottom - SL_OFFSET, Sell SL = box_top + SL_OFFSET).
SL_OFFSET       = 0.3
MIN_RR          = 1.0


PENALTY_PER_N_TRADES        = 10
NUM_WORKERS                 = 3   # parallel CPU cores (legacy; step1 now runs single-threaded on candle data)

# Candle timeframe of the strategy. A pandas offset alias accepted by both
# df.resample(...) and pd.Timedelta(...).
CANDLE_TIMEFRAME    = "1D"

# Pre-resampled candle data the pipeline runs on. Must match CANDLE_TIMEFRAME
# (e.g. XAU_4h_data.csv for "4h"). step1 and 1d_test_bot.py read this file
# directly; the 1M file is only needed by the 1h/15m live-sim bots.
CANDLE_DATA_FILE    = "XAU_1d_data.csv"

# Earliest 1M bar to keep. Bars before this timestamp are dropped during
# extraction (step1) and in the live-sim test bots. Raw data begins 2004.06.11,
# so "2004-01-01 00:00" keeps everything available.
DATA_START          = "2004-01-01 00:00"

RAW_DATA_FILE       = "XAU_1m_data.csv"
RAW_TRADES_FILE     = "trades.csv"
GROUPED_FOLDER      = "step2_grouped"
FILTERED_FOLDER     = "step3_filtered"
LISTS_FOLDER        = "step4_lists"
RESCORE_FILE        = "step5_rescore_summary.csv"
DRAWDOWN_FILE       = "step6_drawdown_summary.csv"
MATRIX_FILE         = "step7_matrix_summary.csv"
