# step1_extract.py
#
# Reads 1-minute forex candle data, resamples to CANDLE_TIMEFRAME candles
# (see config.py), detects 3-candle "box breakout" signals (see strategy.md /
# box_strategy.py), simulates each triggered trade forward, and writes all
# results to trades.csv.
#
# Output columns:
#   date, time, day_of_week, type, entry, stop_loss,
#   distance, max_profit, reward_risk, close_time
#


import pandas as pd
import numpy as np
from multiprocessing import Pool

from config import (
    MIN_RR,
    RAW_DATA_FILE,
    RAW_TRADES_FILE,
    NUM_WORKERS,
    CANDLE_TIMEFRAME,
    DATA_START,
)
from box_strategy import box_signal, find_breakout
from thresholds import generate_thresholds


# ---------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------


def load_minute_data(filepath):
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
# RESAMPLING
# ---------------------------------------------------------------

def resample_candles(minute_df):
    """
    Resamples 1-minute data into CANDLE_TIMEFRAME OHLCV candles (see config.py).
    Candle label is the START of the period.
    Candle close time = label + CANDLE_TIMEFRAME.
    Drops incomplete candles (e.g. partial periods at start/end of data).
    """
    ohlcv = minute_df.resample(CANDLE_TIMEFRAME, label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    # Drop candles where we have no data
    ohlcv = ohlcv.dropna(subset=["open", "close"])
    return ohlcv



# ---------------------------------------------------------------
# TRADE SIMULATION
# ---------------------------------------------------------------

def simulate_trade(direction, entry, stop_loss, distance, minute_times, minute_high, minute_low, start_dt):
    start_pos = int(np.searchsorted(minute_times, start_dt.to_datetime64(), side="left"))

    if start_pos >= len(minute_times):
        return 0.0, "SL", None

    if direction == "Buy":
        sub_high = minute_high[start_pos:]
        sub_low  = minute_low[start_pos:]
        normal_hits   = np.flatnonzero(sub_low <= stop_loss)
        favorable_arr = sub_high - entry
    else:
        sub_high = minute_high[start_pos:]
        sub_low  = minute_low[start_pos:]
        normal_hits   = np.flatnonzero(sub_high >= stop_loss)
        favorable_arr = entry - sub_low

    tp_hits = np.flatnonzero(favorable_arr >= MIN_RR * distance)

    if normal_hits.size:
        exit_idx = int(normal_hits[0])
        max_favorable = float(np.max(favorable_arr[:exit_idx])) if exit_idx > 0 else 0.0
        if max_favorable < 0:
            max_favorable = 0.0
        rr = max_favorable / distance
        if tp_hits.size and int(tp_hits[0]) < exit_idx:
            close_ts = pd.Timestamp(minute_times[start_pos + int(tp_hits[0])])
        else:
            close_ts = pd.Timestamp(minute_times[start_pos + exit_idx])
        close_time = close_ts.strftime("%Y-%m-%d %H:%M")
        return round(max_favorable, 6), round(rr, 1) if rr >= MIN_RR else "SL", close_time

    # End of data without SL hit
    max_favorable = float(np.max(favorable_arr)) if len(favorable_arr) else 0.0
    if max_favorable < 0:
        max_favorable = 0.0
    rr = max_favorable / distance if distance > 0 else 0.0
    if tp_hits.size:
        close_ts = pd.Timestamp(minute_times[start_pos + int(tp_hits[0])])
    else:
        close_ts = pd.Timestamp(minute_times[start_pos + len(favorable_arr) - 1])
    close_time = close_ts.strftime("%Y-%m-%d %H:%M")
    return round(max_favorable, 6), round(rr, 1) if rr >= MIN_RR else "SL", close_time


# ---------------------------------------------------------------
# PARALLEL WORKER
# ---------------------------------------------------------------

# Module-level globals populated once per worker process by _init_worker.
# Using an initializer avoids pickling the large arrays with every task.
_minute_times = None
_minute_high  = None
_minute_low   = None
# Candle arrays (needed to build the 3-candle box) + the candle timeframe.
_c_times = None
_c_open  = None
_c_high  = None
_c_low   = None
_c_close = None
_tf      = None


def _init_worker(mt, mh, ml, ct, co, ch, cl, cc, tf):
    global _minute_times, _minute_high, _minute_low
    global _c_times, _c_open, _c_high, _c_low, _c_close, _tf
    _minute_times, _minute_high, _minute_low = mt, mh, ml
    _c_times, _c_open, _c_high, _c_low, _c_close = ct, co, ch, cl, cc
    _tf = tf


def _process_box(i):
    """
    Box = candles (i-2, i-1, i). Breakout candle = i+1.
    Returns a trade row dict, or None when no valid box / no breakout entry.
    """
    c1 = (_c_open[i - 2], _c_high[i - 2], _c_low[i - 2], _c_close[i - 2])
    c2 = (_c_open[i - 1], _c_high[i - 1], _c_low[i - 1], _c_close[i - 1])
    c3 = (_c_open[i],     _c_high[i],     _c_low[i],     _c_close[i])

    valid, box_top, box_bottom = box_signal(c1, c2, c3)
    if not valid:
        return None

    win_start = pd.Timestamp(_c_times[i + 1])
    win_end   = win_start + _tf
    breakout = find_breakout(
        box_top, box_bottom, win_start, win_end,
        _minute_times, _minute_high, _minute_low,
    )
    if breakout is None:
        return None

    direction, entry, stop_loss, trigger_dt = breakout
    distance = abs(entry - stop_loss)
    if distance == 0:
        return None

    max_profit, reward_risk, close_time = simulate_trade(
        direction, entry, stop_loss, distance,
        _minute_times, _minute_high, _minute_low, trigger_dt,
    )
    return {
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
    }


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------

def run():
    print("=" * 55)
    print("STEP 1 — BASE DATA EXTRACTION")
    print("=" * 55)

    # -- Load --
    print(f"\nLoading 1-minute data from '{RAW_DATA_FILE}'...")
    minute_df = load_minute_data(RAW_DATA_FILE)
    minute_times = minute_df.index.values
    minute_high = minute_df["high"].to_numpy()
    minute_low = minute_df["low"].to_numpy()
    print(f"  Loaded   : {len(minute_df):,} 1-minute candles")
    print(f"  From     : {minute_df.index[0]}")
    print(f"  To       : {minute_df.index[-1]}")

    # -- Resample --
    print(f"\nResampling to {CANDLE_TIMEFRAME} candles...")
    candles = resample_candles(minute_df)
    print(f"  {CANDLE_TIMEFRAME} candles : {len(candles):,}")

    # -- Simulate (parallel) --
    # Box = candles (i-2, i-1, i); breakout candle = i+1. Iterate every
    # overlapping triple that has a following candle to break it.
    print(f"\nDetecting box breakouts across {NUM_WORKERS} workers...")
    c_times = candles.index.values
    c_open  = candles["open"].to_numpy()
    c_high  = candles["high"].to_numpy()
    c_low   = candles["low"].to_numpy()
    c_close = candles["close"].to_numpy()
    tf = pd.Timedelta(CANDLE_TIMEFRAME)

    box_indices = list(range(2, len(candles) - 1))
    with Pool(
        processes=NUM_WORKERS,
        initializer=_init_worker,
        initargs=(minute_times, minute_high, minute_low,
                  c_times, c_open, c_high, c_low, c_close, tf),
    ) as pool:
        results = pool.map(_process_box, box_indices)

    trades = [r for r in results if r is not None]

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
