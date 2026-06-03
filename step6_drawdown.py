# step6_drawdown.py
# Computes the lowest drawdown for each list from step4,
# across every reward level R from 1 to max available.
# Output: step6_drawdown_summary.csv

import pandas as pd
import numpy as np
import os
from config import LISTS_FOLDER, DRAWDOWN_FILE, MIN_RR


def get_trade_values(df, reward_level):
    numeric_rr = pd.to_numeric(df["reward_risk"], errors="coerce")
    values = np.where(
        df["reward_risk"] == "SL", -1.0,
        np.where(
            numeric_rr >= reward_level, float(reward_level),
            -1.0
        )
    )
    return values.astype(float)


def get_loss_event_indices(df):
    is_sl = df["reward_risk"] == "SL"
    return np.flatnonzero(is_sl.to_numpy())


# REPLACE WITH
def compute_lowest_drawdown(values, loss_indices):
    if len(loss_indices) == 0:
        return 0.0, None

    # Full cumulative sum of the entire list
    cumsum = np.cumsum(values)

    # Suffix minimum: suffix_min[i] = min(cumsum[i], cumsum[i+1], ..., cumsum[-1])
    suffix_min = np.minimum.accumulate(cumsum[::-1])[::-1]

    # For each starting index i, the min of the segment cumsum is:
    #   suffix_min[i] - (cumsum[i-1] if i > 0 else 0)
    prev_cumsum = np.empty(len(cumsum))
    prev_cumsum[0] = 0.0
    prev_cumsum[1:] = cumsum[:-1]

    segment_mins = suffix_min[loss_indices] - prev_cumsum[loss_indices]

    best_pos = int(np.argmin(segment_mins))
    lowest   = float(segment_mins[best_pos])
    best_start = int(loss_indices[best_pos])

    return lowest, best_start


def main():
    if not os.path.exists(LISTS_FOLDER):
        print(f"ERROR: {LISTS_FOLDER} not found. Run step4_lists.py first.")
        return

    summary_rows = []

    for filename in sorted(os.listdir(LISTS_FOLDER)):
        if not filename.startswith("list_rr_") or not filename.endswith(".csv"):
            continue

        T = int(filename.replace("list_rr_", "").replace(".csv", ""))
        filepath = os.path.join(LISTS_FOLDER, filename)
        df = pd.read_csv(filepath).reset_index(drop=True)

        if df.empty:
            continue

        # Reward levels: 1 up to the max integer RR in this list
        numeric_rr = pd.to_numeric(df["reward_risk"], errors="coerce")
        positive_rr = numeric_rr[numeric_rr >= MIN_RR]

        if positive_rr.empty:
            continue

        # REPLACE WITH
        loss_indices = get_loss_event_indices(df)
        values = get_trade_values(df, T)
        lowest_dd, best_start = compute_lowest_drawdown(values, loss_indices)

        summary_rows.append({
            "rr_threshold"    : T,
            "lowest_drawdown" : round(lowest_dd, 4),
            "starting_index"  : best_start,
            "total_trades"    : len(df),
        })

        print(f"Threshold {T}: drawdown computed.")


    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values("rr_threshold").reset_index(drop=True)
    summary_df.to_csv(DRAWDOWN_FILE, index=False)
    print(f"\nStep 6 complete. Summary saved to {DRAWDOWN_FILE}.")


if __name__ == "__main__":
    main()