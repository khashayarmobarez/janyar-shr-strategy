# All shared constants. Change values here only.

# Box-breakout model (see strategy.md / box_strategy.py):
#   ENTRY_OFFSET = buffer beyond the box boundary at which entry triggers
#                  (Buy = box_top + ENTRY_OFFSET, Sell = box_bottom - ENTRY_OFFSET).
#   SL_OFFSET    = distance past the opposite box boundary for the stop loss
#                  (Buy SL = box_bottom - SL_OFFSET, Sell SL = box_top + SL_OFFSET).
ENTRY_OFFSET    = 0.3
SL_OFFSET       = 0.3
MIN_RR          = 1.0


PENALTY_PER_N_TRADES        = 10
NUM_WORKERS                 = 3   # parallel CPU cores for step1 simulation; change to 4 or 5 to use more

# Candle timeframe the pipeline resamples 1M data to, and the size of the
# breakout-detection window. A pandas offset alias accepted by both
# df.resample(...) and pd.Timedelta(...). Set "15min" to restore the old behavior.
CANDLE_TIMEFRAME    = "4h"

RAW_DATA_FILE       = "XAU_1m_data.csv"
RAW_TRADES_FILE     = "trades.csv"
GROUPED_FOLDER      = "step2_grouped"
FILTERED_FOLDER     = "step3_filtered"
LISTS_FOLDER        = "step4_lists"
RESCORE_FILE        = "step5_rescore_summary.csv"
DRAWDOWN_FILE       = "step6_drawdown_summary.csv"
MATRIX_FILE         = "step7_matrix_summary.csv"
