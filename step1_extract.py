# step1_extract.py
#
# Reads pre-resampled CANDLE_TIMEFRAME candle data (CANDLE_DATA_FILE, see
# config.py), detects 3-candle "box breakout" signals (see strategy.md /
# box_strategy.py), simulates each triggered trade forward on the same
# candles, and writes all results to trades.csv.
#
# Breakout and exit are evaluated at candle granularity: a breakout candle
# that pierces both box levels is skipped as ambiguous (unless its open
# gapped beyond one level), and the SL-hit candle's favorable extreme is
# excluded from max_profit.
#
# Output columns:
#   date, time, day_of_week, type, entry, stop_loss,
#   distance, max_profit, reward_risk, close_time
#


import pandas as pd
import numpy as np

from config import (
    MIN_RR,
    CANDLE_DATA_FILE,
    RAW_TRADES_FILE,
    DATA_START,
)
from box_strategy import box_signal, find_breakout_candle, simulate_trade_candles
from thresholds import generate_thresholds


# ---------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------


def load_ohlcv_csv(filepath):
    df = pd.read_csv(
        filepath,
        sep=";",
        header=None,
        names=["datetime", "open", "high", "low", "close", "volume"],
        skiprows=1,
        low_memory=False,
    )
    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y.%m.%d %H:%M")
    df = df.set_index("datetime").sort_index()

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"])

    # Remove all data before DATA_START (config.py)
    df = df[df.index >= DATA_START]

    return df


# ---------------------------------------------------------------
# BOX DETECTION + TRADE SIMULATION
# ---------------------------------------------------------------

def extract_trades(candles):
    """
    Box = candles (i-2, i-1, i). Breakout candle = i+1.
    Returns a list of trade row dicts.
    """
    c_times = candles.index
    c_open  = candles["open"].to_numpy()
    c_high  = candles["high"].to_numpy()
    c_low   = candles["low"].to_numpy()
    c_close = candles["close"].to_numpy()
    total   = len(candles)

    trades = []
    for i in range(2, total - 1):
        if i % 1000 == 0:
            print(f"  [{i:>7} / {total}]  {c_times[i].date()}")

        c1 = (c_open[i - 2], c_high[i - 2], c_low[i - 2], c_close[i - 2])
        c2 = (c_open[i - 1], c_high[i - 1], c_low[i - 1], c_close[i - 1])
        c3 = (c_open[i],     c_high[i],     c_low[i],     c_close[i])

        valid, box_top, box_bottom = box_signal(c1, c2, c3)
        if not valid:
            continue

        breakout = find_breakout_candle(
            box_top, box_bottom, c_open[i + 1], c_high[i + 1], c_low[i + 1],
        )
        if breakout is None:
            continue

        direction, entry, stop_loss = breakout
        distance = abs(entry - stop_loss)
        if distance == 0:
            continue

        max_profit, reward_risk, close_idx = simulate_trade_candles(
            direction, entry, stop_loss, distance,
            c_high, c_low, i + 1, min_rr=MIN_RR,
        )
        trigger_dt = c_times[i + 1]
        close_time = c_times[close_idx].strftime("%Y-%m-%d %H:%M") if close_idx is not None else None

        trades.append({
            "date"        : trigger_dt.strftime("%Y-%m-%d"),
            "time"        : trigger_dt.strftime("%H:%M"),
            "day_of_week" : trigger_dt.strftime("%A"),
            "type"        : direction,
            "entry"       : round(entry, 6),
            "stop_loss"   : round(stop_loss, 6),
            "distance"    : round(distance, 6),
            "max_profit"  : max_profit,
            "reward_risk" : reward_risk,
            "close_time"  : close_time,
        })

    return trades


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------

def run():
    print("=" * 55)
    print("STEP 1 — BASE DATA EXTRACTION")
    print("=" * 55)

    # -- Load --
    print(f"\nLoading candle data from '{CANDLE_DATA_FILE}'...")
    candles = load_ohlcv_csv(CANDLE_DATA_FILE)
    print(f"  Loaded   : {len(candles):,} candles")
    print(f"  From     : {candles.index[0]}")
    print(f"  To       : {candles.index[-1]}")

    # -- Simulate --
    # Box = candles (i-2, i-1, i); breakout candle = i+1. Iterate every
    # overlapping triple that has a following candle to break it.
    print("\nDetecting box breakouts...")
    trades = extract_trades(candles)

    # -- Save --
    df = pd.DataFrame(trades)
    df.to_csv(RAW_TRADES_FILE, index=False)

    # -- Summary --
    total_trades = len(df)
    normal_sl    = (df["reward_risk"] == "SL").sum()
    wins = total_trades - normal_sl

    print(f"\n{'=' * 55}")
    print(f"STEP 1 COMPLETE")
    print(f"{'=' * 55}")
    print(f"  Total trades   : {total_trades:,}")
    print(f"  Normal SL      : {normal_sl:,}")
    print(f"  Output         : {RAW_TRADES_FILE}")
    print(f"  Wins (RR >= 1) : {wins:,}")

    # -- Available R/R thresholds for downstream steps --
    numeric_rr = pd.to_numeric(df["reward_risk"], errors="coerce")
    positive_rr = numeric_rr[numeric_rr >= MIN_RR]
    thresholds  = generate_thresholds(positive_rr.max() if not positive_rr.empty else None)
    print(f"  R/R thresholds : {thresholds}")
    print()

    return df, thresholds


if __name__ == "__main__":
    run()
