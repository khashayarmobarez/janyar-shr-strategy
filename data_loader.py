# data_loader.py
#
# Shared OHLCV CSV loader used by step1_extract.py and 1d_test_bot.py.
#
# Auto-detects the file layout so the various exports we receive load the same:
#   - MT4-style exports: tab-separated, no header, "%Y-%m-%d %H:%M" dates
#   - legacy files:      semicolon-separated, header row, "%Y.%m.%d %H:%M" dates
#   - Investing.com:     comma-separated, quoted header
#                        ("Date","Price","Open","High","Low","Vol.","Change %"),
#                        "%m/%d/%Y" dates, newest-first, "Price" = close
#
# When a header row is present, columns are matched by name (Price -> close,
# Vol./Volume -> volume, Change % ignored). Otherwise columns are positional:
# datetime, open, high, low, close, volume.
#
# Returns a DataFrame indexed by a sorted DatetimeIndex with columns:
#   open, high, low, close, volume

import pandas as pd

from config import DATA_START

_STD_COLUMNS = ["datetime", "open", "high", "low", "close", "volume"]
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y.%m.%d %H:%M",
    "%Y-%m-%d",
    "%Y.%m.%d",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
)
_ALIASES = {
    "date": "datetime", "datetime": "datetime", "time": "datetime", "timestamp": "datetime",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close", "price": "close", "adj close": "close", "adjclose": "close",
    "vol": "volume", "vol.": "volume", "volume": "volume",
}


def _looks_like_datetime(token):
    """True when a single field parses with one of the known date formats."""
    for fmt in _DATE_FORMATS:
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
    token = first.split(sep)[0].strip().strip('"')
    skiprows = 0 if _looks_like_datetime(token) else 1
    return sep, skiprows


def _parse_datetime(series):
    for fmt in _DATE_FORMATS:
        try:
            return pd.to_datetime(series, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(series, format="mixed")


def _read_named(filepath, sep):
    """Read a file that has a header row, mapping columns by name."""
    raw = pd.read_csv(filepath, sep=sep, header=0, low_memory=False, encoding="utf-8-sig")
    raw.columns = [str(c).strip().strip('"').lower() for c in raw.columns]

    cols = {}
    for name in raw.columns:
        std = _ALIASES.get(name)
        if std and std not in cols:
            cols[std] = raw[name]

    if "datetime" not in cols:
        raise ValueError(f"{filepath}: no date column found among {list(raw.columns)}")
    if "volume" not in cols:
        cols["volume"] = pd.NA
    return pd.DataFrame(cols)


def load_ohlcv_csv(filepath):
    sep, skiprows = _sniff_reader(filepath)

    if skiprows == 0:
        df = pd.read_csv(
            filepath, sep=sep, header=None, names=_STD_COLUMNS,
            low_memory=False, encoding="utf-8-sig",
        )
    else:
        df = _read_named(filepath, sep)

    df["datetime"] = _parse_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"])

    # Remove all data before DATA_START (config.py)
    df = df[df.index >= DATA_START]

    return df
