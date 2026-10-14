# 3-Candle Box Breakout Strategy

## Overview

The strategy is based on three consecutive candles that form a **box**. Depending on how the next candle behaves relative to that box, a trade is opened.

The active dataset is **EUR/USD daily** (`EURUSD1440.csv`). All price offsets below are in EUR/USD price units (1 pip = 0.0001).

---

## Box Formation

A box is formed from three consecutive candles. Its boundaries are:

- **Box top**: the highest price (wick) reached across all three candles
- **Box bottom**: the lowest price (wick) reached across all three candles
- **Box length (distance)**: `box_top − box_bottom`

The three candles must match one of the three models below.

---

## Trade Entry

After a valid box is formed, only the **immediately next candle** can trigger an entry. If it does not trigger, no trade is taken.

| Direction | Trigger condition                           | Entry price    | Stop loss                     |
| --------- | ------------------------------------------- | -------------- | ----------------------------- |
| **Buy**   | Next candle's price reaches `box_top`       | `box_top`      | `box_bottom − SL_OFFSET`      |
| **Sell**  | Next candle's price reaches `box_bottom`    | `box_bottom`   | `box_top + SL_OFFSET`         |

`SL_OFFSET` is `0.00006` (0.6 pip) in `config.py`.

**Candle granularity (pipeline + 1D test bot):** the breakout candle's own high/low decide. If it pierces both levels, its open breaks the tie — an open gapped beyond a level means that side triggered first; an open inside the box leaves the order unknown, so the signal is ambiguous and skipped.

> The former 1-minute granularity path (1H/15M live-sim bots) is retired: the EUR/USD base data has no 1-minute feed.

---

## Models

### Model 1 — Alternating

**Patterns:** `bullish / bearish / bullish` or `bearish / bullish / bearish`

No extra rule. Any alternating three-candle sequence forms a valid box.

---

### Model 2 — One Adjacent Same-Direction Pair

**Patterns:** `bullish / bullish / bearish` · `bearish / bearish / bullish` · `bearish / bullish / bullish` · `bullish / bearish / bearish`

**Rule:** For the two candles that share the same direction (the adjacent pair):

- **Bullish pair**: the second candle's close must **not** be higher than the first candle's high (wick)
- **Bearish pair**: the second candle's close must **not** be lower than the first candle's low (wick)

If the rule is violated, the pattern is invalid and no box is formed.

---

### Model 3 — All Same Direction

**Patterns:** `bullish / bullish / bullish` or `bearish / bearish / bearish`

**Rule (applied to consecutive pairs — candle 1→2 and candle 2→3):**

- **All bullish**: candle 2 close ≤ candle 1 high (wick) **and** candle 3 close ≤ candle 2 high (wick)
- **All bearish**: candle 2 close ≥ candle 1 low (wick) **and** candle 3 close ≥ candle 2 low (wick)

Note: candles 1 and 3 have no direct rule between them.

If either condition is violated, the pattern is invalid.

---

## Distance Bucket

Trades are grouped by `floor(|entry − stop_loss| / DISTANCE_BUCKET_SIZE)`, with `DISTANCE_BUCKET_SIZE = 0.0002` (2 pips) in `config.py`. This is only the grouping key; `reward_risk` is a ratio and is unaffected by the choice of unit.

---

## Trade Exit

The exit logic is the same as previous strategies: the simulation scans forward from the entry bar and records the maximum favorable move before the stop loss is hit. At candle granularity the scan runs on the strategy candles themselves, and the SL-hit candle's own favorable extreme is excluded (the intra-candle order is unknown).
