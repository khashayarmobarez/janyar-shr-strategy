# data_loader.py
#
# Shared OHLCV CSV loader used by step1_extract.py and 1d_test_bot.py.
#
# Auto-detects the file layout so both the legacy semicolon/header/period-date
# files (e.g. XAU_1d_data.csv) and MT4-style exports (tab-separated, no header,
# hyphenated dates, e.g. XAUUSD1440.csv) load identically.
#
# Returns a DataFrame indexed by a sorted DatetimeIndex with columns:
#   open, high, low, close, volume

import pandas as pd

from config import DATA_START

_COLUMNS = ["datetime", "open", "high", "low", "close", "volume"]
_DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M", "%Y-%m-%d", "%Y.%m.%d")


def _looks_like_datetime(token):
    """True when a single field parses with one of the known date formats."""
    for fmt in _DATETIME_FORMATS:
        try:
            pd.to_datetime([token], format=fmt)
            return True
        except (ValueError, TypeError):
            continue
    return False


def _sniff_reader(filepath):
    """Return (sep, skiprows) by inspecting the file's first line."""
    with open(filepath, "r", encoding="utf-8-sig") as f:
        first = f.readline()

    if "\t" in first:
        sep = "\t"
    elif ";" in first:
        sep = ";"
    else:
        sep = ","

    # A header row's first field is not a datetime (e.g. "Date").
    token = first.split(sep)[0].strip()
    skiprows = 0 if _looks_like_datetime(token) else 1
    return sep, skiprows


def _parse_datetime(series):
    for fmt in _DATETIME_FORMATS:
        try:
            return pd.to_datetime(series, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(series, format="mixed")


def load_ohlcv_csv(filepath):
    sep, skiprows = _sniff_reader(filepath)

    df = pd.read_csv(
        filepath,
        sep=sep,
        header=None,
        names=_COLUMNS,
        skiprows=skiprows,
        low_memory=False,
    )
    df["datetime"] = _parse_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"])

    # Remove all data before DATA_START (config.py)
    df = df[df.index >= DATA_START]

    return df
