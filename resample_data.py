# resample_data.py
#
# Builds a pre-resampled candle file from the daily base (XAUUSD1440.csv) so the
# pipeline can run on a coarser timeframe (e.g. weekly). Mirrors the existing
# pre-resampled files (XAU_1d_data.csv, XAU_4h_data.csv, ...).
#
# Usage:
#   python resample_data.py                    # weekly  -> XAU_1w_data.csv
#   python resample_data.py 4h XAU_4h_data.csv # custom timeframe/output

import sys

from data_loader import load_ohlcv_csv, resample_ohlcv

BASE_FILE         = "XAUUSD1440.csv"
DEFAULT_TIMEFRAME = "1W"
DEFAULT_OUTPUT    = "XAU_1w_data.csv"


def main():
    timeframe = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TIMEFRAME
    output    = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT

    print(f"Loading base candles from '{BASE_FILE}'...")
    base = load_ohlcv_csv(BASE_FILE, apply_start=False)
    print(f"  {len(base):,} bars  {base.index[0]} -> {base.index[-1]}")

    resampled = resample_ohlcv(base, timeframe)
    resampled.index.name = "Date"
    resampled.to_csv(output, sep=";", date_format="%Y.%m.%d %H:%M")

    print(f"Resampled to {timeframe}: {len(resampled):,} bars")
    print(f"  {resampled.index[0]} -> {resampled.index[-1]}")
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
