# thresholds.py
# Shared helpers for the reward/risk (R/R) threshold sweep.
#
# The pipeline scores trades against a set of candidate thresholds. The grid is
# fine-grained below 10 and integer-spaced above it:
#   0.1, 0.2, ..., 1.0, 1.1, ..., 9.9, 10.0, then 11, 12, 13, ...
# capped at the maximum reward_risk present in the data.

import math


def fmt_threshold(T):
    """Folder/file label for a threshold.

    0.1 -> '0.1', 1.0 -> '1', 10.0 -> '10', 1.3 -> '1.3'. Round-trips with
    float(label), so producers (step3/step4) and consumers (step5/step6, test
    bots) agree on names.
    """
    return f"{float(T):g}"


def generate_thresholds(max_rr):
    """Candidate thresholds: 0.1 steps up to min(10.0, max_rr), then integers
    11..floor(max_rr). Returns [] when max_rr is missing/NaN."""
    if max_rr is None or (isinstance(max_rr, float) and math.isnan(max_rr)):
        return []
    max_rr = float(max_rr)
    out = [round(i / 10, 1) for i in range(1, 101) if i / 10 <= max_rr + 1e-9]  # 0.1 .. 10.0
    out += [float(n) for n in range(11, int(math.floor(max_rr)) + 1)]          # 11 .. floor(max)
    return out
