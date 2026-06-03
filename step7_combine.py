# step7_combine.py
# Combines step 5 (rescore) and step 6 (drawdown) data based on rr_threshold.
# Calculates matrix_number = (10 / |lowest_drawdown|) * score
# Output: step7_matrix_summary.csv

import pandas as pd
import os
from config import RESCORE_FILE, DRAWDOWN_FILE, MATRIX_FILE


def main():
    if not os.path.exists(RESCORE_FILE):
        print(f"ERROR: {RESCORE_FILE} not found. Run step5_rescore.py first.")
        return

    if not os.path.exists(DRAWDOWN_FILE):
        print(f"ERROR: {DRAWDOWN_FILE} not found. Run step6_drawdown.py first.")
        return

    # Read both summary files
    step5_df = pd.read_csv(RESCORE_FILE)
    step6_df = pd.read_csv(DRAWDOWN_FILE)

    # Merge on rr_threshold (both files have total_trades, so pandas adds _x and _y suffixes)
    combined_df = pd.merge(step5_df, step6_df, on="rr_threshold", how="inner", suffixes=("_5", "_6"))
    
    # Use the total_trades from step 5 (rescore) as the primary one
    combined_df["total_trades"] = combined_df["total_trades_5"]

    # Calculate matrix_number = (10 / |lowest_drawdown|) * score
    combined_df["lowest_drawdown_abs"] = combined_df["lowest_drawdown"].abs()
    combined_df["matrix_number"] = (10 / combined_df["lowest_drawdown_abs"]) * combined_df["score"]

    # Sort by rr_threshold for readability
    combined_df = combined_df.sort_values("rr_threshold").reset_index(drop=True)

    # Select final output columns
    output_df = combined_df[["rr_threshold", "total_trades", "score", "lowest_drawdown_abs", 
                              "lowest_drawdown", "starting_index", "matrix_number"]]

    # Save to CSV
    output_file = MATRIX_FILE
    output_df.to_csv(output_file, index=False)
    print(f"Step 7 complete. Combined summary saved to {output_file}.")
    print(f"Total rows: {len(output_df)}")
    print(f"\nSample data:")
    print(output_df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()