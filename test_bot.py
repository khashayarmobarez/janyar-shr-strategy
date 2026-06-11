# test_bot.py
# Backtest bot on survived trades from step3_filtered/{THRESHOLD}/ (pre-computed;
# the candle timeframe follows whatever step1-3 produced via config.CANDLE_TIMEFRAME).
# Loads ALL surviving distance files for THRESHOLD; configurable RR / risk / fee.
# Starting capital: $10,000 | Exit at 1:WIN_RR RR or stop loss
# Output: test_bot_results.csv + console summary

import pandas as pd
import os
from config import FILTERED_FOLDER

# --- Configurable parameters (tune after inspecting the step7 4H matrix) ---
THRESHOLD = 19      # which step3_filtered/{THRESHOLD}/ folder to load
WIN_RR    = 19.0    # reward:risk; a win pays WIN_RR * risk_amount
RISK_PCT  = 0.0013  # risk per trade as a fraction of current equity
FEE_PCT   = 0.00013 # fee per trade as a fraction of current equity


def load_survived_trades(threshold=THRESHOLD):
    """
    Load all surviving Buy/Sell distance files from step3_filtered/{threshold}/,
    merge them, drop duplicates, and sort chronologically.
    """
    subfolder = os.path.join(FILTERED_FOLDER, str(threshold))
    if not os.path.exists(subfolder):
        print(f"ERROR: {subfolder} not found.")
        return pd.DataFrame()

    frames = []
    for filename in os.listdir(subfolder):
        if not filename.endswith(".csv"):
            continue
        df = pd.read_csv(os.path.join(subfolder, filename))
        if not df.empty:
            frames.append(df)

    if not frames:
        print(f"No trades found for threshold {threshold}")
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True).drop_duplicates()

    # Sort by date then time ascending
    merged["_datetime"] = pd.to_datetime(
        merged["date"].astype(str) + " " + merged["time"].astype(str)
    )
    merged = merged.sort_values("_datetime").drop(columns=["_datetime"])
    merged = merged.reset_index(drop=True)

    return merged


def calculate_trade_pnl(row, account_balance, risk_pct=RISK_PCT, fee_pct=FEE_PCT):
    """
    Calculate PnL for a single trade with percentage-based risk.
    - Risk per trade: RISK_PCT of current equity
    - Fee per trade: FEE_PCT of current equity (deducted every trade)
    - If reward_risk >= WIN_RR: trade hit 1:WIN_RR TP -> win (WIN_RR × risk_amount)
    - If reward_risk == "SL" (or below WIN_RR): trade lost -> lose (risk_amount)

    Returns: (pnl, risk_pct_used)
    """
    risk_amount = account_balance * risk_pct
    fee = account_balance * fee_pct

    rr = row["reward_risk"]

    if rr == "SL":
        return -(risk_amount + fee), risk_pct

    try:
        rr_val = float(rr)
        if rr_val >= WIN_RR:
            return (WIN_RR * risk_amount - fee), risk_pct
        else:
            return -(risk_amount + fee), risk_pct
    except (ValueError, TypeError):
        return -(risk_amount + fee), risk_pct


def run_backtest(trades_df, initial_capital=10000, risk_pct=RISK_PCT, fee_pct=FEE_PCT):
    """
    Run the backtest simulation with percentage-based risk.
    """
    if trades_df.empty:
        print("No trades to simulate.")
        return None

    account_balance = initial_capital
    initial_capital = initial_capital
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

    # Yearly tracking
    yearly_data = {}

    for idx, row in trades_df.iterrows():
        pnl, risk_pct_used = calculate_trade_pnl(row, account_balance, risk_pct, fee_pct)
        account_balance += pnl
        stats["total_trades"] += 1
        stats["total_pnl"] += pnl

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

        if account_balance > stats["max_equity"]:
            stats["max_equity"] = account_balance

        drawdown = (stats["max_equity"] - account_balance) / stats["max_equity"]
        if drawdown > stats["max_drawdown"]:
            stats["max_drawdown"] = drawdown

        # Extract year
        year = row["date"][:4]
        if year not in yearly_data:
            yearly_data[year] = {"trades": 0, "pnl": 0.0, "start_balance": account_balance - pnl, "end_balance": account_balance}
        else:
            yearly_data[year]["end_balance"] = account_balance
        yearly_data[year]["trades"] += 1
        yearly_data[year]["pnl"] += pnl

        open_dt  = pd.to_datetime(row["date"] + " " + row["time"])
        close_dt = pd.to_datetime(row["close_time"]) if "close_time" in row and pd.notna(row["close_time"]) else None
        duration_h = round((close_dt - open_dt).total_seconds() / 3600, 1) if close_dt else None

        equity_curve.append({
            "trade_index": idx + 1,
            "date": row["date"],
            "time": row["time"],
            "type": row["type"],
            "entry": row["entry"],
            "stop_loss": row["stop_loss"],
            "distance": row["distance"],
            "reward_risk": row["reward_risk"],
            "close_time": row.get("close_time"),
            "duration_hours": duration_h,
            "pnl": pnl,
            "balance": account_balance,
            "drawdown_pct": drawdown * 100,
        })

    # Add final balance to stats
    stats["final_balance"] = account_balance
    stats["yearly_data"] = yearly_data

    return pd.DataFrame(equity_curve), stats


def main():
    print("=" * 60)
    print(f"TEST BOT - Backtest on Survived Trades (Threshold = {THRESHOLD})")
    print("=" * 60)

    # Load survived trades
    print(f"\nLoading survived trades (threshold={THRESHOLD}, all files)...")
    trades_df = load_survived_trades(threshold=THRESHOLD)

    if trades_df.empty:
        print("No survived trades found. Exiting.")
        return

    print(f"  Total survived trades: {len(trades_df)}")
    print(f"  Buys: {(trades_df['type'] == 'Buy').sum()}")
    print(f"  Sells: {(trades_df['type'] == 'Sell').sum()}")

    # Run backtest
    print("\nRunning backtest...")
    print(f"  Initial capital: $10,000")
    print(f"  Risk per trade: {RISK_PCT*100:.3g}% of equity")
    print(f"  Fee per trade: {FEE_PCT*100:.3g}% of equity")
    print(f"  Exit: 1:{WIN_RR:g} RR (TP = {WIN_RR:g}x SL distance) or stop loss")
    print()

    result, stats = run_backtest(trades_df, initial_capital=10000, risk_pct=RISK_PCT, fee_pct=FEE_PCT)

    if result is None:
        return

    # Save results
    output_file = "test_bot_results.csv"
    result.to_csv(output_file, index=False)
    print(f"Results saved to {output_file}")

    # Print summary
    print("\n" + "=" * 60)
    print("BACKTEST SUMMARY")
    print("=" * 60)
    print(f"  Total trades     : {stats['total_trades']}")
    print(f"  - Buys           : {stats['buy_trades']}")
    print(f"  - Sells          : {stats['sell_trades']}")
    print(f"  Wins             : {stats['wins']} ({stats['wins']/stats['total_trades']*100:.1f}%)")
    print(f"  Losses           : {stats['losses']} ({stats['losses']/stats['total_trades']*100:.1f}%)")
    print(f"  - Buy wins       : {stats['buy_wins']}")
    print(f"  - Sell wins      : {stats['sell_wins']}")
    print(f"  Total PnL        : ${stats['total_pnl']:.2f}")
    print(f"  Final balance    : ${stats['final_balance']:.2f}")
    print(f"  Max drawdown     : {stats['max_drawdown']*100:.2f}%")
    print(f"  Max equity       : ${stats['max_equity']:.2f}")

    durations = result["duration_hours"].dropna()
    if not durations.empty:
        print(f"  Avg duration     : {durations.mean():.1f} h")
        print(f"  Max duration     : {durations.max():.1f} h")
    print("=" * 60)

    # Win/loss distribution
    print("\nWin/Loss by Type:")
    print(f"  Buy win rate: {stats['buy_wins']/stats['buy_trades']*100:.1f}% ({stats['buy_wins']}/{stats['buy_trades']})")
    print(f"  Sell win rate: {stats['sell_wins']/stats['sell_trades']*100:.1f}% ({stats['sell_wins']}/{stats['sell_trades']})")

    # Yearly performance
    print("\n" + "=" * 60)
    print("YEARLY PERFORMANCE")
    print("=" * 60)
    print(f"  {'Year':<8} {'Trades':>8} {'PnL':>12} {'Return':>10} {'End Balance':>14}")
    print(f"  {'----':<8} {'------':>8} {'---------':>12} {'------':>10} {'-----------':>14}")
    
    for year in sorted(stats['yearly_data'].keys()):
        y = stats['yearly_data'][year]
        start_bal = y['start_balance']
        end_bal = y['end_balance']
        yearly_return = ((end_bal - start_bal) / start_bal) * 100
        print(f"  {year:<8} {y['trades']:>8} ${y['pnl']:>10.2f} {yearly_return:>9.1f}% ${end_bal:>12.2f}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()