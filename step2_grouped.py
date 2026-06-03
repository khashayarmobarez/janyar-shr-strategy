import pandas as pd
import math
import os
from config import GROUPED_FOLDER, RAW_TRADES_FILE


def main():
    """
    Step 2 – Group by Distance and Type.
    Reads trades.csv, splits by type (Buy/Sell) and integer distance bucket,
    writes separate CSV files to GROUPED_FOLDER.
    """
    # Ensure input file exists
    if not os.path.exists(RAW_TRADES_FILE):
        print(f"ERROR: {RAW_TRADES_FILE} not found. Run step1_extract.py first.")
        return

    # Load trades
    df = pd.read_csv(RAW_TRADES_FILE)
    print(f"Loaded {len(df)} trades from {RAW_TRADES_FILE}")

    # Compute integer distance bucket
    df["distance_bucket"] = df["distance"].apply(math.floor)

    # Ensure output folder exists
    os.makedirs(GROUPED_FOLDER, exist_ok=True)

    # Group by type and distance_bucket
    grouped = df.groupby(["type", "distance_bucket"])

    files_written = 0
    for (trade_type, bucket), group_df in grouped:
        # Skip empty groups (shouldn't happen, but safe)
        if len(group_df) == 0:
            continue

        # Build filename
        filename = f"{trade_type}_distance_{bucket}.csv"
        filepath = os.path.join(GROUPED_FOLDER, filename)

        # Write CSV (without the distance_bucket column)
        group_df.drop(columns=["distance_bucket"]).to_csv(filepath, index=False)
        files_written += 1
        print(f"  -> {filename} ({len(group_df)} trades)")

    print(f"\nStep 2 complete. {files_written} files written to {GROUPED_FOLDER}.")


if __name__ == "__main__":
    main()