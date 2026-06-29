# 1h_test_bot.py
# Backtest bot using 1H candle signals filtered by step3_filtered/4 distance buckets.
# Risk: 0.5% | Commission: 0.05% | R/R: 1:4 (win if rr >= 4)
# Output: 1h_test_bot_results.csv + console summary

import math
import os

import numpy as np
import pandas as pd

from config import FILTERED_FOLDER, RAW_DATA_FILE, DATA_START
from box_strategy import box_signal, find_breakout

WIN_RR   = 4.0
RISK_PCT = 0.005
FEE_PCT  = 0.0005


# ---------------------------------------------------------------
# DISTANCE BUCKET FILTER
# ---------------------------------------------------------------

def load_valid_buckets(threshold=4):
    folder = os.path.join(FILTERED_FOLDER, str(threshold))
    if not os.path.exists(folder):
        print(f"ERROR: {folder} not found.")
        return set()

    buckets = set()
    for filename in os.listdir(folder):
        if not filename.endswith(".csv"):
            continue
        # e.g. "Buy_distance_10.csv"
        parts = filename.replace(".csv", "").split("_distance_")
        if len(parts) != 2:
            continue
        direction = parts[0]   # "Buy" or "Sell"
        try:
            bucket = int(parts[1])
        except ValueError:
            continue
        buckets.add((direction, bucket))

    return buckets


# ---------------------------------------------------------------
# DATA LOADING (same as step1_extract.py)
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
    df = df[df.index >= DATA_START]
    return df


def resample_to_1h(minute_df):
    ohlcv = minute_df.resample("1h", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    ohlcv = ohlcv.dropna(subset=["open", "close"])
    return ohlcv


# ---------------------------------------------------------------
# TRADE SIMULATION (same logic as step1_extract.py)
# ---------------------------------------------------------------

def simulate_trade(direction, entry, stop_loss, distance, minute_times, minute_high, minute_low, start_dt):
    start_pos = int(np.searchsorted(minute_times, start_dt.to_datetime64(), side="left"))

    if start_pos >= len(minute_times):
        return 0.0, "SL"

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

    if normal_hits.size:
        exit_idx = int(normal_hits[0])
        max_favorable = float(np.max(favorable_arr[:exit_idx])) if exit_idx > 0 else 0.0
        if max_favorable < 0:
            max_favorable = 0.0
        rr = max_favorable / distance
        return round(max_favorable, 6), round(rr, 1) if rr >= 1.0 else "SL"

    max_favorable = float(np.max(favorable_arr)) if len(favorable_arr) else 0.0
    if max_favorable < 0:
        max_favorable = 0.0
    rr = max_favorable / distance if distance > 0 else 0.0
    return round(max_favorable, 6), round(rr, 1) if rr >= 1.0 else "SL"


# ---------------------------------------------------------------
# TRADE GENERATION
# ---------------------------------------------------------------

def generate_trades(candles_1h, minute_times, minute_high, minute_low, valid_buckets):
    trades = []
    total = len(candles_1h)

    # Box = candles (i-2, i-1, i); breakout candle = i+1. See box_strategy.py.
    c_times = candles_1h.index.values
    c_open  = candles_1h["open"].to_numpy()
    c_high  = candles_1h["high"].to_numpy()
    c_low   = candles_1h["low"].to_numpy()
    c_close = candles_1h["close"].to_numpy()
    tf = pd.Timedelta(hours=1)

    for i in range(2, total - 1):
        if i % 2000 == 0:
            print(f"  [{i:>7} / {total}]  {pd.Timestamp(c_times[i]).date()}")

        c1 = (c_open[i - 2], c_high[i - 2], c_low[i - 2], c_close[i - 2])
        c2 = (c_open[i - 1], c_high[i - 1], c_low[i - 1], c_close[i - 1])
        c3 = (c_open[i],     c_high[i],     c_low[i],     c_close[i])

        valid, box_top, box_bottom = box_signal(c1, c2, c3)
        if not valid:
            continue

        win_start = pd.Timestamp(c_times[i + 1])
        win_end   = win_start + tf
        breakout = find_breakout(
            box_top, box_bottom, win_start, win_end,
            minute_times, minute_high, minute_low,
        )
        if breakout is None:
            continue

        direction, entry, stop_loss, trigger_dt = breakout
        distance = abs(entry - stop_loss)
        if distance == 0:
            continue

        bucket = math.floor(distance)
        if (direction, bucket) not in valid_buckets:
            continue

        max_profit, reward_risk = simulate_trade(
            direction, entry, stop_loss, distance,
            minute_times, minute_high, minute_low, trigger_dt,
        )

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
        })

    return pd.DataFrame(trades)


# ---------------------------------------------------------------
# BACKTEST
# ---------------------------------------------------------------

def calculate_pnl(row, balance):
    risk_amount = balance * RISK_PCT
    fee         = balance * FEE_PCT

    rr = row["reward_risk"]
    if rr == "SL":
        return -(risk_amount + fee)

    try:
        if float(rr) >= WIN_RR:
            return WIN_RR * risk_amount - fee
        else:
            return -(risk_amount + fee)
    except (ValueError, TypeError):
        return -(risk_amount + fee)


def run_backtest(trades_df, initial_capital=10000):
    if trades_df.empty:
        print("No trades to simulate.")
        return None, None

    balance = initial_capital
    equity_curve = []
    stats = {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl": 0.0,
        "buy_trades": 0,
        "sell_trades": 0,
        "buy_wins": 0,
        "sell_wins": 0,
        "max_equity": initial_capital,
        "max_drawdown": 0.0,
    }
    yearly_data = {}

    for idx, row in trades_df.iterrows():
        pnl     = calculate_pnl(row, balance)
        balance += pnl

        stats["total_trades"] += 1
        stats["total_pnl"]    += pnl

        if pnl > 0:
            stats["wins"] += 1
            if row["type"] == "Buy":
                stats["buy_wins"] += 1
            else:
                stats["sell_wins"] += 1
        else:
            stats["losses"] += 1

        if row["type"] == "Buy":
            stats["buy_trades"] += 1
        else:
            stats["sell_trades"] += 1

        if balance > stats["max_equity"]:
            stats["max_equity"] = balance

        drawdown = (stats["max_equity"] - balance) / stats["max_equity"]
        if drawdown > stats["max_drawdown"]:
            stats["max_drawdown"] = drawdown

        year = row["date"][:4]
        if year not in yearly_data:
            yearly_data[year] = {
                "trades": 0, "pnl": 0.0,
                "start_balance": balance - pnl,
                "end_balance": balance,
            }
        else:
            yearly_data[year]["end_balance"] = balance
        yearly_data[year]["trades"] += 1
        yearly_data[year]["pnl"]    += pnl

        equity_curve.append({
            "trade_index" : idx + 1,
            "date"        : row["date"],
            "time"        : row["time"],
            "type"        : row["type"],
            "entry"       : row["entry"],
            "stop_loss"   : row["stop_loss"],
            "distance"    : row["distance"],
            "reward_risk" : row["reward_risk"],
            "pnl"         : pnl,
            "balance"     : balance,
            "drawdown_pct": drawdown * 100,
        })

    stats["final_balance"] = balance
    stats["yearly_data"]   = yearly_data
    return pd.DataFrame(equity_curve), stats


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------

def main():
    print("=" * 60)
    print("1H TEST BOT — 1H Candles | RR 1:4 | Risk 0.5% | Fee 0.05%")
    print("=" * 60)

    # Load valid distance buckets from step3_filtered/4
    print("\nLoading valid distance buckets from step3_filtered/4...")
    valid_buckets = load_valid_buckets(threshold=4)
    if not valid_buckets:
        print("No valid buckets found. Exiting.")
        return
    buy_buckets  = sorted(b for d, b in valid_buckets if d == "Buy")
    sell_buckets = sorted(b for d, b in valid_buckets if d == "Sell")
    print(f"  Buy  buckets : {buy_buckets}")
    print(f"  Sell buckets : {sell_buckets}")

    # Load 1m data
    print(f"\nLoading 1-minute data from '{RAW_DATA_FILE}'...")
    minute_df = load_minute_data(RAW_DATA_FILE)
    minute_times = minute_df.index.values
    minute_high  = minute_df["high"].to_numpy()
    minute_low   = minute_df["low"].to_numpy()
    print(f"  Loaded   : {len(minute_df):,} 1-minute candles")
    print(f"  From     : {minute_df.index[0]}")
    print(f"  To       : {minute_df.index[-1]}")

    # Resample to 1H
    print("\nResampling to 1H candles...")
    candles_1h = resample_to_1h(minute_df)
    print(f"  1H candles : {len(candles_1h):,}")

    # Generate and filter trades
    print("\nGenerating and filtering 1H trades...")
    trades_df = generate_trades(candles_1h, minute_times, minute_high, minute_low, valid_buckets)
    print(f"\n  Total filtered trades : {len(trades_df):,}")
    if trades_df.empty:
        print("No trades after filtering. Exiting.")
        return
    print(f"  Buys  : {(trades_df['type'] == 'Buy').sum():,}")
    print(f"  Sells : {(trades_df['type'] == 'Sell').sum():,}")

    # Run backtest
    print("\nRunning backtest...")
    result, stats = run_backtest(trades_df, initial_capital=10000)
    if result is None:
        return

    # Save results
    output_file = "1h_test_bot_results.csv"
    result.to_csv(output_file, index=False)
    print(f"Results saved to {output_file}")

    # Summary
    print("\n" + "=" * 60)
    print("BACKTEST SUMMARY")
    print("=" * 60)
    print(f"  Total trades     : {stats['total_trades']}")
    print(f"  - Buys           : {stats['buy_trades']}")
    print(f"  - Sells          : {stats['sell_trades']}")
    win_rate = stats['wins'] / stats['total_trades'] * 100
    print(f"  Wins             : {stats['wins']} ({win_rate:.1f}%)")
    print(f"  Losses           : {stats['losses']}")
    print(f"  - Buy wins       : {stats['buy_wins']}")
    print(f"  - Sell wins      : {stats['sell_wins']}")
    print(f"  Total PnL        : ${stats['total_pnl']:.2f}")
    print(f"  Final balance    : ${stats['final_balance']:.2f}")
    print(f"  Max drawdown     : {stats['max_drawdown']*100:.2f}%")
    print(f"  Max equity       : ${stats['max_equity']:.2f}")
    print("=" * 60)

    print("\nWin/Loss by Type:")
    if stats['buy_trades']:
        print(f"  Buy  win rate : {stats['buy_wins']/stats['buy_trades']*100:.1f}%"
              f" ({stats['buy_wins']}/{stats['buy_trades']})")
    if stats['sell_trades']:
        print(f"  Sell win rate : {stats['sell_wins']/stats['sell_trades']*100:.1f}%"
              f" ({stats['sell_wins']}/{stats['sell_trades']})")

    print("\n" + "=" * 60)
    print("YEARLY PERFORMANCE")
    print("=" * 60)
    print(f"  {'Year':<8} {'Trades':>8} {'PnL':>12} {'Return':>10} {'End Balance':>14}")
    print(f"  {'----':<8} {'------':>8} {'---------':>12} {'------':>10} {'-----------':>14}")
    for year in sorted(stats['yearly_data'].keys()):
        y = stats['yearly_data'][year]
        yearly_return = (y['end_balance'] - y['start_balance']) / y['start_balance'] * 100
        print(f"  {year:<8} {y['trades']:>8} ${y['pnl']:>10.2f}"
              f" {yearly_return:>9.1f}% ${y['end_balance']:>12.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
