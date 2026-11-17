#!/usr/bin/env python3
"""Forecast a game launch day's hourly Twitch viewers, hours 2-24, from hour 1.

Reads one case file (makefun/twitch-ccu-case/v1) per *.in file in the input
directory and writes one .out file per case: for each hour 2..24 of the
release day, five quantiles (0.05, 0.25, 0.5, 0.75, 0.95) of that hour's
viewer count.

Method: the case carries past big launches ("comparables"), each with hourly
viewer counts spanning its own release day.  For launches that unlocked at
midnight local time rolling across time zones -- the pattern of this case --
the shape of the day relative to its first hour is fairly stable: a shallow
dip in the small hours, then a climb as the Americas wake up, peaking in the
UTC evening.  We pool the log-ratios ln(viewers_h / viewers_1) of the rolling
launches hour by hour and read the five quantiles off each hour's pooled
sample, then scale by this case's own hour-1 print.

One signal separates the risers from the decliners: how the first hour
compares with the four hours just before the day began.  A launch whose big
wave already happened before the day (a PC unlock the evening before, an
early-access crowd) starts at its peak and fades, which shows up as a first
hour well above the pre-day level; a launch still waiting on the Americas
starts modestly and climbs.  Each comparable is therefore weighted by how
close its own pre-day jump is to this case's, and the pooled quantiles are
smoothed across neighbouring hours.  Pure standard library, no network,
fully deterministic.
"""

import json
import math
import os
from datetime import datetime, timedelta, timezone

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
HOURS = range(2, 25)
# Similarity weighting on the pre-day jump: bandwidth (in log units) and the
# floor weight every comparable keeps.  Tuned on leave-one-out over the
# comparables; see the build notes.
JUMP_BW = 0.75
JUMP_FLOOR = 0.15
# Calibration of the pooled spread: the log-distance of every quantile from
# the median is multiplied by this before the forecast is written.
SPREAD_SCALE = 1.0


def parse_ts(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )


def day_curve(comp):
    """Release-day hourly viewers of one comparable, {hour 1..24: viewers}.

    Returns None when the release day's first hour is missing or not
    positive (the comparable cannot anchor a ratio curve then)."""
    try:
        start = parse_ts(comp["day_start"])
    except (KeyError, TypeError, ValueError):
        return None
    day = {}
    for row in comp.get("hourly") or []:
        try:
            at = parse_ts(row["from"])
        except (KeyError, TypeError, ValueError):
            continue
        delta = at - start
        if timedelta(0) <= delta < timedelta(hours=24):
            hour = delta.seconds // 3600 + 1
            viewers = row.get("viewers")
            if isinstance(viewers, (int, float)) and viewers >= 0:
                day[hour] = float(viewers)
    if not day.get(1):
        return None
    return day


def is_rolling(comp):
    """True when the comparable unlocked at midnight local time, rolling.

    The case's own launches (and the final's) unlock that way; launches with
    one simultaneous global unlock have a completely different day shape
    (near-zero first hour, then a spike), so they must not enter the pool."""
    text = (comp.get("unlock") or "").lower()
    return "midnight local" in text or "rolling" in text


def quantile(sorted_vals, tau):
    """Linear-interpolation quantile of an ascending list."""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = tau * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def weighted_quantile(pairs, tau):
    """Quantile of [(value, weight)] by interpolation on cumulative weight."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    if len(pairs) == 1 or total <= 0:
        return pairs[0][0]
    target = tau * total
    acc = 0.0
    for i, (val, w) in enumerate(pairs):
        acc += w
        if acc >= target:
            if i == 0:
                return val
            prev_val, prev_w = pairs[i - 1]
            before = acc - w
            if w <= 0:
                return val
            frac = (target - before) / w
            return prev_val + (val - prev_val) * frac
    return pairs[-1][0]


def pre_day_jump(hourly_rows, day_start):
    """ln(hour-1 viewers / mean of the 4 hourly rows before the day).

    Computed from rows shaped like a comparable's `hourly` or a case's
    `history_hourly` (each {from, viewers}); None when it cannot be formed."""
    try:
        start = parse_ts(day_start)
    except (TypeError, ValueError):
        return None
    by_time = {}
    for row in hourly_rows or []:
        try:
            at = parse_ts(row["from"])
        except (KeyError, TypeError, ValueError):
            continue
        viewers = row.get("viewers")
        if isinstance(viewers, (int, float)) and viewers >= 0:
            by_time[at] = float(viewers)
    first = by_time.get(start)
    pre = [by_time.get(start - timedelta(hours=k)) for k in (1, 2, 3, 4)]
    pre = [v for v in pre if v]
    if not first or not pre:
        return None
    mean_pre = sum(pre) / len(pre)
    if mean_pre <= 0:
        return None
    return math.log(first / mean_pre)


def pooled_log_ratios(comps, target_jump):
    """{hour: [(ln(viewers_h / viewers_1), weight)]} over the given pool.

    A comparable's weight falls off with the distance between its own
    pre-day jump and the case's, with a floor so none is fully excluded."""
    curves = []
    for comp in comps:
        day = day_curve(comp)
        if day is None:
            continue
        weight = 1.0
        if target_jump is not None:
            jump = pre_day_jump(comp.get("hourly"), comp["day_start"])
            if jump is not None:
                dist = (jump - target_jump) / JUMP_BW
                weight = JUMP_FLOOR + (1.0 - JUMP_FLOOR) * math.exp(
                    -dist * dist)
        curves.append((day, weight))
    pool = {}
    for hour in HOURS:
        pairs = []
        for day, weight in curves:
            v = day.get(hour)
            if v:
                pairs.append((math.log(v / day[1]), weight))
        if pairs:
            pool[hour] = pairs
    return pool, len(curves)


def forecast(case):
    """The 23 forecast rows for one case."""
    known = case["known"]
    if isinstance(known, list):
        known = known[0]
    p = float(known["viewers"])
    if not p >= 1.0:
        p = 1.0
    target_jump = pre_day_jump(case.get("history_hourly"), case["day_start"])
    comps = case.get("comparables") or []
    rolling = [c for c in comps if is_rolling(c)]
    pool, n_pool = pooled_log_ratios(rolling, target_jump)
    if n_pool < 6:
        pool, n_pool = pooled_log_ratios(comps, target_jump)
    # Log-quantile of every level for every hour, then a light smoothing
    # across neighbouring hours: the true day shape is smooth, the pooled
    # sample of a dozen launches is not.
    log_q = {}
    for hour in HOURS:
        pairs = pool.get(hour)
        if pairs:
            raw = [weighted_quantile(pairs, tau) for tau in LEVELS]
            med = raw[len(LEVELS) // 2]
            log_q[hour] = [med + SPREAD_SCALE * (v - med) for v in raw]
        else:
            log_q[hour] = [0.0] * len(LEVELS)
    smooth = {}
    for hour in HOURS:
        acc = []
        for k in range(len(LEVELS)):
            near = [log_q[h][k] for h in (hour - 1, hour, hour + 1)
                    if h in log_q]
            acc.append(sum(near) / len(near))
        smooth[hour] = acc
    rows = []
    for hour in HOURS:
        qs = [p * math.exp(v) for v in smooth[hour]]
        # Quantiles of one sample are already ordered; enforce it anyway and
        # keep every value inside the allowed range.
        qs = [min(max(q, 1.0), 1e9) for q in qs]
        qs.sort()
        rows.append({"hour": hour, "q": qs})
    return rows


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    for name in sorted(os.listdir(in_dir)):
        if not name.endswith(".in"):
            continue
        with open(os.path.join(in_dir, name), encoding="utf-8") as fh:
            case = json.load(fh)
        out = {"hours": forecast(case)}
        out_name = name[: -len(".in")] + ".out"
        with open(os.path.join(out_dir, out_name), "w", encoding="utf-8") as fh:
            json.dump(out, fh)


if __name__ == "__main__":
    main()
