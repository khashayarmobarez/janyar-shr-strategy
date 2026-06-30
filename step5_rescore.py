# step5_rescore.py
# Re-scores each date-ordered list from step4.
# Informational only — no filtering.
# Output: step5_rescore_summary.csv

import pandas as pd
import math
import os
import numpy as np
from config import LISTS_FOLDER, RESCORE_FILE, MIN_RR


def compute_score(df, threshold):
    total_trades = len(df)
    numeric_rr = pd.to_numeric(df["reward_risk"], errors="coerce")

    wins = numeric_rr >= threshold
    win_score = int(wins.sum()) * threshold

    below_threshold = (numeric_rr > 0) & (numeric_rr < threshold)
    below_score = -int(below_threshold.sum())

    sl_trades = df["reward_risk"] == "SL"
    sl_score = -int(sl_trades.sum())

    penalty = math.floor(total_trades / 10)

    return win_score + below_score + sl_score - penalty


def main():
    if not os.path.exists(LISTS_FOLDER):
        print(f"ERROR: {LISTS_FOLDER} not found. Run step4_lists.py first.")
        return

    summary_rows = []

    for filename in sorted(os.listdir(LISTS_FOLDER)):
        if not filename.startswith("list_rr_") or not filename.endswith(".csv"):
            continue

        # Extract threshold from filename: list_rr_{T}.csv
        T = float(filename.replace("list_rr_", "").replace(".csv", ""))
        filepath = os.path.join(LISTS_FOLDER, filename)
        df = pd.read_csv(filepath)

        if df.empty:
            continue

        score = compute_score(df, T)

        summary_rows.append({
            "rr_threshold" : T,
            "total_trades" : len(df),
            "score"        : score,
        })

        print(f"Threshold {T}: {len(df)} trades, score = {score}")

    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values("rr_threshold").reset_index(drop=True)
    summary_df.to_csv(RESCORE_FILE, index=False)
    print(f"\nStep 5 complete. Summary saved to {RESCORE_FILE}.")


if __name__ == "__main__":
    main()