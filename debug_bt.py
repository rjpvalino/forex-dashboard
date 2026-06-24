"""Debug: find the actual WR baseline to isolate what's hurting"""
import sys
sys.path.insert(0, 'c:/MyProject/MyFirstClaudeCodeTest/forex-dashboard')

from backtest.engine import _synthetic_candles, _ema_series, _rsi, _calc_atr, _to_weekly
from data.trend_analyzer import TrendAnalyzer

analyzer = TrendAnalyzer()
candles = _synthetic_candles('EUR_USD', 1.09, 0.007, n=700)

SL_MULT = 1.5
TP_MULT = 1.0
WEEKLY_D_WINDOW = 260
DAILY_WINDOW = 60

# Test 1: Pure random entry (no filter at all)
import random
random.seed(42)
wins, losses = 0, 0
for i in range(WEEKLY_D_WINDOW+5, len(candles)):
    if random.random() > 0.5:
        continue  # ~50% chance of entry each bar
    entry = float(candles[i]['mid']['o'])
    direction = 'long' if random.random() > 0.5 else 'short'
    atr = 0.007
    sl = entry - SL_MULT*atr if direction=='long' else entry + SL_MULT*atr
    tp = entry + TP_MULT*atr if direction=='long' else entry - TP_MULT*atr
    for j in range(i+1, min(i+30, len(candles))):
        h = float(candles[j]['mid']['h'])
        l = float(candles[j]['mid']['l'])
        if direction == 'long':
            if l <= sl: losses += 1; break
            if h >= tp: wins   += 1; break
        else:
            if h >= sl: losses += 1; break
            if l <= tp: wins   += 1; break

total = wins + losses
print("TEST 1 - Pure random entry:")
print("  Wins:", wins, "Losses:", losses, "WR:", round(wins/total*100,1) if total else "N/A", "%")
print("  Expected baseline (random walk): SL/(SL+TP) =", round(SL_MULT/(SL_MULT+TP_MULT)*100,1), "%")
print()

# Test 2: EMA touch only (no weekly filter, no slope filter)
wins2, losses2 = 0, 0
EMA_TOUCH_PCT = 0.004
for i in range(WEEKLY_D_WINDOW+5, len(candles)):
    d_window = candles[max(0,i-DAILY_WINDOW):i]
    d_closes = [float(c['mid']['c']) for c in d_window]
    d_lows   = [float(c['mid']['l']) for c in d_window]
    d_highs  = [float(c['mid']['h']) for c in d_window]
    ema_vals = _ema_series(d_closes, 21)
    if len(ema_vals) < 2: continue
    curr_ema = ema_vals[-1]
    atr = _calc_atr(
        [float(c['mid']['h']) for c in d_window[-16:]],
        [float(c['mid']['l']) for c in d_window[-16:]],
        [float(c['mid']['c']) for c in d_window[-16:]], 14)
    if not atr: continue

    touch_long  = d_lows[-1]  <= curr_ema*(1+EMA_TOUCH_PCT) and d_closes[-1] > curr_ema
    touch_short = d_highs[-1] >= curr_ema*(1-EMA_TOUCH_PCT) and d_closes[-1] < curr_ema

    entry = float(candles[i]['mid']['o'])
    direction = 'long' if touch_long else ('short' if touch_short else None)
    if not direction: continue

    sl = entry - SL_MULT*atr if direction=='long' else entry + SL_MULT*atr
    tp = entry + TP_MULT*atr if direction=='long' else entry - TP_MULT*atr

    for j in range(i+1, min(i+30, len(candles))):
        h = float(candles[j]['mid']['h'])
        l = float(candles[j]['mid']['l'])
        if direction == 'long':
            if l <= sl: losses2 += 1; break
            if h >= tp: wins2   += 1; break
        else:
            if h >= sl: losses2 += 1; break
            if l <= tp: wins2   += 1; break

total2 = wins2 + losses2
print("TEST 2 - EMA touch (no other filters):")
print("  Wins:", wins2, "Losses:", losses2, "WR:", round(wins2/total2*100,1) if total2 else "N/A", "%")
print("  Signals fired:", total2)
print()

# Test 3: EMA touch + weekly trend filter only
wins3, losses3 = 0, 0
for i in range(WEEKLY_D_WINDOW+5, len(candles)):
    d_window = candles[max(0,i-DAILY_WINDOW):i]
    w_window = candles[max(0,i-WEEKLY_D_WINDOW):i]
    weekly   = _to_weekly(w_window)

    d_closes = [float(c['mid']['c']) for c in d_window]
    d_lows   = [float(c['mid']['l']) for c in d_window]
    d_highs  = [float(c['mid']['h']) for c in d_window]
    ema_vals = _ema_series(d_closes, 21)
    if len(ema_vals) < 2: continue
    curr_ema = ema_vals[-1]
    atr = _calc_atr(
        [float(c['mid']['h']) for c in d_window[-16:]],
        [float(c['mid']['l']) for c in d_window[-16:]],
        [float(c['mid']['c']) for c in d_window[-16:]], 14)
    if not atr: continue

    w_res = analyzer.analyze_full(weekly[-52:] if len(weekly)>=52 else weekly)
    w_up   = w_res['trend'] == 'Trending Up'   and w_res['adx'] >= 28
    w_down = w_res['trend'] == 'Trending Down' and w_res['adx'] >= 28

    touch_long  = d_lows[-1]  <= curr_ema*(1+EMA_TOUCH_PCT) and d_closes[-1] > curr_ema and w_up
    touch_short = d_highs[-1] >= curr_ema*(1-EMA_TOUCH_PCT) and d_closes[-1] < curr_ema and w_down

    entry = float(candles[i]['mid']['o'])
    direction = 'long' if touch_long else ('short' if touch_short else None)
    if not direction: continue

    sl = entry - SL_MULT*atr if direction=='long' else entry + SL_MULT*atr
    tp = entry + TP_MULT*atr if direction=='long' else entry - TP_MULT*atr

    for j in range(i+1, min(i+30, len(candles))):
        h = float(candles[j]['mid']['h'])
        l = float(candles[j]['mid']['l'])
        if direction == 'long':
            if l <= sl: losses3 += 1; break
            if h >= tp: wins3   += 1; break
        else:
            if h >= sl: losses3 += 1; break
            if l <= tp: wins3   += 1; break

total3 = wins3 + losses3
print("TEST 3 - EMA touch + weekly trend filter:")
print("  Wins:", wins3, "Losses:", losses3, "WR:", round(wins3/total3*100,1) if total3 else "N/A", "%")
print("  Weekly Up signals:", wins3+losses3, "(of", total3, "total)")
