# gta6-twitch-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/XTxiaoting14332/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/XTxiaoting14332/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

A forecaster for a game launch day's Twitch audience. Given everything recorded up to the end of the release day's first hour (that hour's viewer count included), `main.py` writes, for each of hours 2 to 24, five quantiles (5%, 25%, 50%, 75%, 95%) of that hour's concurrent viewers in the game's Twitch category.

Method: the case file carries past big launches with their full hourly curves. Launches that unlocked at midnight local time, rolling across time zones — this launch's pattern — share a day shape relative to their first hour: a shallow dip in the small hours, then a climb as the Americas wake up, peaking in the UTC evening. The program pools those launches' log-ratios ln(viewers_h / viewers_1) hour by hour, weights each launch by how closely its pre-day jump (first hour versus the four hours before the day) matches this case's, smooths the pooled quantiles across neighbouring hours, and scales them by the case's own hour-1 count. Pure Python standard library, offline, deterministic.

## Run it

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `*.in` case file in the input directory and writes one `<id>.out` forecast per case to the output directory (defaults: `/input` and `/output` when the variables are unset).

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
