# 1d_test_bot.py
# Backtest bot using 1D candle signals filtered by step3_filtered/{THRESHOLD} distance buckets.
# Runs entirely on the daily candle file (CANDLE_DATA_FILE, see config.py) — breakout
# detection and trade simulation use the same candle-granularity logic as step1_extract.py.
# Risk: 0.5% | Commission: 0.05% | R/R: 1:4 (win if rr >= 4)
# Output: 1d_test_bot_results.csv + console summary

import math
import os

import numpy as np
import pandas as pd

from config import FILTERED_FOLDER, CANDLE_DATA_FILE, DATA_START
from box_strategy import box_signal, find_breakout_candle, simulate_trade_candles
from thresholds import fmt_threshold

THRESHOLD = 4
WIN_RR    = 4.0
RISK_PCT  = 0.005
FEE_PCT   = 0.0005


# ---------------------------------------------------------------
# DISTANCE BUCKET FILTER
# ---------------------------------------------------------------

def load_valid_buckets(threshold=THRESHOLD):
    folder = os.path.join(FILTERED_FOLDER, fmt_threshold(threshold))
    if not os.path.exists(folder):
        print(f"ERROR: {folder} not found.")
        if os.path.exists(FILTERED_FOLDER):
            available = sorted(
                d for d in os.listdir(FILTERED_FOLDER)
                if os.path.isdir(os.path.join(FILTERED_FOLDER, d))
            )
            print(f"Available thresholds: {available}")
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
    df = df[df.index >= DATA_START]
    return df


# ---------------------------------------------------------------
# TRADE GENERATION (same candle-level logic as step1_extract.py)
# ---------------------------------------------------------------

def generate_trades(candles, valid_buckets):
    trades = []
    total = len(candles)

    # Box = candles (i-2, i-1, i); breakout candle = i+1. See box_strategy.py.
    c_times = candles.index
    c_open  = candles["open"].to_numpy()
    c_high  = candles["high"].to_numpy()
    c_low   = candles["low"].to_numpy()
    c_close = candles["close"].to_numpy()

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

        bucket = math.floor(distance)
        if (direction, bucket) not in valid_buckets:
            continue

        max_profit, reward_risk, _close_idx = simulate_trade_candles(
            direction, entry, stop_loss, distance,
            c_high, c_low, i + 1,
        )
        trigger_dt = c_times[i + 1]

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
    print(f"1D TEST BOT — 1D Candles | RR 1:{WIN_RR:g} | Risk {RISK_PCT*100:g}% | Fee {FEE_PCT*100:g}%")
    print("=" * 60)

    # Load valid distance buckets from step3_filtered/{THRESHOLD}
    print(f"\nLoading valid distance buckets from {FILTERED_FOLDER}/{fmt_threshold(THRESHOLD)}...")
    valid_buckets = load_valid_buckets(threshold=THRESHOLD)
    if not valid_buckets:
        print("No valid buckets found. Exiting.")
        return
    buy_buckets  = sorted(b for d, b in valid_buckets if d == "Buy")
    sell_buckets = sorted(b for d, b in valid_buckets if d == "Sell")
    print(f"  Buy  buckets : {buy_buckets}")
    print(f"  Sell buckets : {sell_buckets}")

    # Load 1D candles
    print(f"\nLoading daily candles from '{CANDLE_DATA_FILE}'...")
    candles = load_ohlcv_csv(CANDLE_DATA_FILE)
    print(f"  1D candles : {len(candles):,}")
    print(f"  From       : {candles.index[0]}")
    print(f"  To         : {candles.index[-1]}")

    # Generate and filter trades
    print("\nGenerating and filtering 1D trades...")
    trades_df = generate_trades(candles, valid_buckets)
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
    output_file = "1d_test_bot_results.csv"
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
