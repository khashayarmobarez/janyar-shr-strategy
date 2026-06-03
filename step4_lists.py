# step4_lists.py
# Merges all surviving files per threshold into a single date-ordered list.
# Output: step4_lists/list_rr_{T}.csv for each threshold T.

import pandas as pd
import os
from config import FILTERED_FOLDER, LISTS_FOLDER


def main():
    if not os.path.exists(FILTERED_FOLDER):
        print(f"ERROR: {FILTERED_FOLDER} not found. Run step3_filtered.py first.")
        return

    os.makedirs(LISTS_FOLDER, exist_ok=True)

    # Each subdirectory in FILTERED_FOLDER is a threshold value
    for threshold_dir in sorted(os.listdir(FILTERED_FOLDER), key=lambda x: int(x) if x.isdigit() else -1):
        subfolder = os.path.join(FILTERED_FOLDER, threshold_dir)

        if not os.path.isdir(subfolder) or not threshold_dir.isdigit():
            continue

        T = int(threshold_dir)
        frames = []

        for filename in os.listdir(subfolder):
            if not filename.endswith(".csv"):
                continue
            filepath = os.path.join(subfolder, filename)
            df = pd.read_csv(filepath)
            if not df.empty:
                frames.append(df)

        if not frames:
            print(f"Threshold {T}: no surviving trades, skipping.")
            continue

        merged = pd.concat(frames, ignore_index=True)

        # Sort by date then time ascending
        merged["_datetime"] = pd.to_datetime(
            merged["date"].astype(str) + " " + merged["time"].astype(str)
        )
        merged = merged.sort_values("_datetime").drop(columns=["_datetime"])
        merged = merged.reset_index(drop=True)

        out_path = os.path.join(LISTS_FOLDER, f"list_rr_{T}.csv")
        merged.to_csv(out_path, index=False)
        print(f"Threshold {T}: {len(merged)} trades → {out_path}")

    print(f"\nStep 4 complete. Lists saved to {LISTS_FOLDER}.")


if __name__ == "__main__":
    main()