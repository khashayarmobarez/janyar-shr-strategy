# box_strategy.py
#
# Shared 3-candle "box breakout" detection logic, used by step1_extract.py
# and the live-sim bots (15m_test_bot.py, 1h_test_bot.py) so the three never
# drift apart.
#
# Concept (see strategy.md):
#   - Three consecutive candles whose colors match one of three models form a
#     "box" spanning the highest high to the lowest low of the three.
#   - The IMMEDIATELY-NEXT candle that pierces the box triggers a trade:
#       pierce the top    -> Buy   (entry = box_top)
#       pierce the bottom -> Sell  (entry = box_bottom)
#   - Stop loss: Buy = box_bottom - SL_OFFSET, Sell = box_top + SL_OFFSET.
#
# A candle tuple is (open, high, low, close).

import numpy as np
import pandas as pd

from config import SL_OFFSET


def classify(open_, close):
    """Candle color: bull if close > open, bear otherwise."""
    return "bull" if close > open_ else "bear"


def box_signal(c1, c2, c3):
    """
    Decide whether three consecutive candles form a valid box.

    Each c is (open, high, low, close).
    Returns (valid, box_top, box_bottom). box_top/box_bottom are None when invalid.
    """
    cols = [classify(c[0], c[3]) for c in (c1, c2, c3)]
    k1, k2, k3 = cols
    valid = False

    # Model 1 - alternating (no extra rule)
    if (k1, k2, k3) in (("bull", "bear", "bull"), ("bear", "bull", "bear")):
        valid = True

    # Model 3 - all same color
    elif k1 == k2 == k3:
        if k1 == "bull":
            # 2nd close <= 1st high  AND  3rd close <= 2nd high
            valid = (c2[3] <= c1[1]) and (c3[3] <= c2[1])
        else:  # bear
            # 2nd close >= 1st low   AND  3rd close >= 2nd low
            valid = (c2[3] >= c1[2]) and (c3[3] >= c2[2])

    # Model 2 - exactly one adjacent same-color pair
    else:
        if k1 == k2:
            first, second, kind = c1, c2, k1
        else:  # k2 == k3 (only remaining possibility here)
            first, second, kind = c2, c3, k2
        if kind == "bull":
            valid = second[3] <= first[1]   # 2nd close not above 1st high
        else:
            valid = second[3] >= first[2]   # 2nd close not below 1st low

    if not valid:
        return False, None, None

    box_top    = max(c1[1], c2[1], c3[1])
    box_bottom = min(c1[2], c2[2], c3[2])
    return True, box_top, box_bottom


def find_breakout(box_top, box_bottom, win_start, win_end,
                  minute_times, minute_high, minute_low):
    """
    Scan the 1-minute bars of the breakout candle (the window [win_start, win_end))
    for the first bar that reaches a box-breakout entry level.

    Buy entry  = box_top
    Sell entry = box_bottom

    Returns (direction, entry, stop_loss, trigger_dt) or None when no entry triggers.
    If a single 1-min bar reaches both levels, the signal is ambiguous and skipped.
    """
    lo = int(np.searchsorted(minute_times, np.datetime64(win_start), side="left"))
    hi = int(np.searchsorted(minute_times, np.datetime64(win_end), side="left"))
    if hi <= lo:
        return None

    sub_high = minute_high[lo:hi]
    sub_low  = minute_low[lo:hi]

    buy_entry  = box_top
    sell_entry = box_bottom

    buy_hits  = np.flatnonzero(sub_high >= buy_entry)
    sell_hits = np.flatnonzero(sub_low <= sell_entry)
    buy_idx  = int(buy_hits[0])  if buy_hits.size  else None
    sell_idx = int(sell_hits[0]) if sell_hits.size else None

    if buy_idx is None and sell_idx is None:
        return None
    if buy_idx is not None and sell_idx is not None:
        if buy_idx == sell_idx:
            return None  # same 1-min bar crosses both sides -> ambiguous
        take_buy = buy_idx < sell_idx
    else:
        take_buy = buy_idx is not None

    if take_buy:
        direction   = "Buy"
        entry       = buy_entry
        stop_loss   = box_bottom - SL_OFFSET
        trigger_pos = lo + buy_idx
    else:
        direction   = "Sell"
        entry       = sell_entry
        stop_loss   = box_top + SL_OFFSET
        trigger_pos = lo + sell_idx

    trigger_dt = pd.Timestamp(minute_times[trigger_pos])
    return direction, entry, stop_loss, trigger_dt
