"""
ADX Trend Confluence — Walk-Forward Backtest Engine
=====================================================
Strategy rules:
  Entry : Daily ADX ≥ 25 AND Weekly ADX ≥ 20, same trend direction,
          confirmed on 2 consecutive daily bars. Enter at next bar OPEN.
  Long  : Both timeframes 'Trending Up'
  Short : Both timeframes 'Trending Down'
  SL    : 1.5 × ATR(14) from entry
  TP    : 2.5 × ATR(14) from entry   (R:R ≈ 1.67)
  Trail : Move stop to breakeven once 1×ATR profit is reached
  MaxHold: 30 bars — close at market on bar 30 if neither SL/TP hit

No look-ahead bias: at bar i, only bars 0..i-1 are used for indicators.
Entry price is the OPEN of bar i (the bar after the confirmed signal).
"""

import sys
import os
import random
import math
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from data.trend_analyzer import TrendAnalyzer

logger = logging.getLogger(__name__)
_analyzer = TrendAnalyzer()

# ── Strategy constants ────────────────────────────────────────────────────────
DAILY_ADX_MIN    = 25
WEEKLY_ADX_MIN   = 20
SL_MULT          = 1.5
TP_MULT          = 2.5
TRAIL_MULT       = 1.0   # move to BE after 1×ATR profit
MAX_HOLD         = 30    # bars
SIGNAL_CONFIRM   = 2     # consecutive bars before entry
DAILY_WINDOW     = 55    # sliding history for daily ADX
WEEKLY_D_WINDOW  = 260   # daily bars fed into weekly resampler → ~52 weekly bars


class BacktestEngine:
    def __init__(self, initial_equity=10000.0, risk_pct=0.01):
        self.initial_equity = initial_equity
        self.risk_pct = risk_pct

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, instrument, candles):
        """Bar-by-bar walk-forward simulation on provided OANDA candle list."""
        if len(candles) < 80:
            return None

        closes = [float(c['mid']['c']) for c in candles]
        highs  = [float(c['mid']['h']) for c in candles]
        lows   = [float(c['mid']['l']) for c in candles]
        opens  = [float(c['mid']['o']) for c in candles]
        times  = [c.get('time', '')     for c in candles]

        equity       = self.initial_equity
        peak         = equity
        max_dd       = 0.0
        equity_curve = [round(equity, 2)]
        trades       = []
        position     = None
        consec       = 0
        last_sig     = None

        # Start after enough bars for both windows
        start_bar = max(DAILY_WINDOW, WEEKLY_D_WINDOW)

        for i in range(start_bar, len(candles)):
            # ── Manage open position ─────────────────────────────────────────
            if position:
                h, l  = highs[i], lows[i]
                d     = position['direction']
                entry = position['entry']
                bars  = i - position['entry_bar']

                if d == 'long' and h >= entry + position['trail_dist']:
                    position['sl'] = max(position['sl'], entry)
                if d == 'short' and l <= entry - position['trail_dist']:
                    position['sl'] = min(position['sl'], entry)

                exit_px, reason = None, None
                if d == 'long':
                    if l <= position['sl']:        exit_px, reason = position['sl'], 'SL'
                    elif h >= position['tp']:      exit_px, reason = position['tp'],  'TP'
                    elif bars >= MAX_HOLD:         exit_px, reason = closes[i],       'Time'
                else:
                    if h >= position['sl']:        exit_px, reason = position['sl'], 'SL'
                    elif l <= position['tp']:      exit_px, reason = position['tp'],  'TP'
                    elif bars >= MAX_HOLD:         exit_px, reason = closes[i],       'Time'

                if exit_px is not None:
                    raw = (exit_px - entry) * position['size']
                    if d == 'short':
                        raw = -raw
                    equity   += raw
                    peak      = max(peak, equity)
                    dd        = (peak - equity) / peak if peak > 0 else 0.0
                    max_dd    = max(max_dd, dd)
                    equity_curve.append(round(equity, 2))

                    trades.append({
                        'instrument':  instrument.replace('_', '/'),
                        'direction':   d,
                        'entry_px':    round(entry, 5),
                        'exit_px':     round(exit_px, 5),
                        'exit_reason': reason,
                        'pnl':         round(raw, 2),
                        'bars_held':   bars,
                        'entry_time':  position['entry_time'],
                        'exit_time':   times[i],
                        'daily_adx':   position['daily_adx'],
                        'weekly_adx':  position['weekly_adx'],
                    })
                    position = None

            # ── Compute indicators (no-lookahead: bars 0..i-1) ───────────────
            if position is None:
                d_window = candles[max(0, i - DAILY_WINDOW):i]
                w_window = candles[max(0, i - WEEKLY_D_WINDOW):i]
                weekly   = _to_weekly(w_window)

                d_res  = _analyzer.analyze_full(d_window)
                w_res  = _analyzer.analyze_full(weekly[-52:] if len(weekly) >= 52 else weekly)
                atr    = _calc_atr(highs[max(0, i-16):i], lows[max(0, i-16):i], closes[max(0, i-16):i], 14)
                if not atr:
                    continue

                if (d_res['trend'] == 'Trending Up'
                        and w_res['trend'] == 'Trending Up'
                        and d_res['adx'] >= DAILY_ADX_MIN
                        and w_res['adx'] >= WEEKLY_ADX_MIN):
                    sig = 'long'
                elif (d_res['trend'] == 'Trending Down'
                        and w_res['trend'] == 'Trending Down'
                        and d_res['adx'] >= DAILY_ADX_MIN
                        and w_res['adx'] >= WEEKLY_ADX_MIN):
                    sig = 'short'
                else:
                    sig = None

                if sig and sig == last_sig:
                    consec += 1
                else:
                    consec = 1 if sig else 0
                last_sig = sig

                if consec >= SIGNAL_CONFIRM and sig:
                    entry = opens[i]
                    risk  = atr * SL_MULT
                    if risk <= 0:
                        continue
                    sl    = entry - risk if sig == 'long' else entry + risk
                    tp    = entry + atr * TP_MULT if sig == 'long' else entry - atr * TP_MULT
                    size  = (equity * self.risk_pct) / risk

                    position = {
                        'direction':  sig,
                        'entry':      entry,
                        'entry_bar':  i,
                        'entry_time': times[i],
                        'sl':         sl,
                        'tp':         tp,
                        'trail_dist': atr * TRAIL_MULT,
                        'size':       size,
                        'daily_adx':  round(d_res['adx'], 1),
                        'weekly_adx': round(w_res['adx'], 1),
                    }
                    consec, last_sig = 0, None

        return _metrics(instrument, trades, equity, self.initial_equity, max_dd, equity_curve)

    def run_demo(self):
        """Run backtest on synthetic data (no OANDA credentials needed)."""
        pairs = {
            'EUR_USD': (1.09,  0.0070),
            'GBP_USD': (1.22,  0.0090),
            'USD_JPY': (140.0, 0.70),
            'USD_CHF': (0.91,  0.0065),
            'USD_CAD': (1.37,  0.0080),
            'AUD_USD': (0.65,  0.0065),
            'NZD_USD': (0.60,  0.0060),
        }
        results = []
        for instr, (start, atr) in pairs.items():
            candles = _synthetic_candles(instr, start, atr, n=500)
            r = self.run(instr, candles)
            if r:
                results.append(r)
        return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_weekly(daily):
    """Resample daily candles into approximate weekly candles (5-bar blocks)."""
    weekly, block = [], []
    for c in daily:
        block.append(c)
        if len(block) == 5:
            weekly.append(_merge(block))
            block = []
    if block:
        weekly.append(_merge(block))
    return weekly


def _merge(candles):
    return {
        'mid': {
            'o': candles[0]['mid']['o'],
            'h': str(max(float(c['mid']['h']) for c in candles)),
            'l': str(min(float(c['mid']['l']) for c in candles)),
            'c': candles[-1]['mid']['c'],
        },
        'complete': True,
        'time': candles[-1].get('time', ''),
    }


def _calc_atr(highs, lows, closes, period):
    if len(closes) < 2:
        return None
    trs = [max(highs[i] - lows[i],
               abs(highs[i] - closes[i-1]),
               abs(lows[i] - closes[i-1]))
           for i in range(1, len(closes))]
    p = min(period, len(trs))
    return sum(trs[-p:]) / p if p > 0 else None


def _metrics(instrument, trades, final_eq, initial_eq, max_dd, equity_curve):
    n = len(trades)
    if n == 0:
        return {
            'instrument': instrument.replace('_', '/'),
            'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
            'profit_factor': 0, 'net_pnl': 0, 'total_return': 0,
            'max_drawdown': 0, 'avg_win': 0, 'avg_loss': 0,
            'expectancy': 0, 'equity_curve': equity_curve, 'trade_log': [],
        }

    wins   = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    gp     = sum(t['pnl'] for t in wins)
    gl     = abs(sum(t['pnl'] for t in losses))
    wr     = len(wins) / n
    avg_w  = gp / len(wins)  if wins   else 0
    avg_l  = gl / len(losses) if losses else 0

    return {
        'instrument':   instrument.replace('_', '/'),
        'total_trades': n,
        'wins':         len(wins),
        'losses':       len(losses),
        'win_rate':     round(wr * 100, 1),
        'profit_factor': round(gp / gl, 2) if gl > 0 else 999.0,
        'net_pnl':      round(final_eq - initial_eq, 2),
        'total_return': round((final_eq - initial_eq) / initial_eq * 100, 2),
        'max_drawdown': round(max_dd * 100, 2),
        'avg_win':      round(avg_w, 2),
        'avg_loss':     round(avg_l, 2),
        'expectancy':   round(wr * avg_w - (1 - wr) * avg_l, 2),
        'equity_curve': equity_curve,
        'trade_log':    trades,
    }


def _synthetic_candles(instrument, start_price, daily_atr, n=500):
    """Realistic random-walk with trend/range regimes for demo backtesting."""
    random.seed(abs(hash(instrument)) % 9999)
    price   = start_price
    candles = []
    trend, trend_bars, trend_str = 0, 0, 0.0

    for _ in range(n):
        if trend_bars <= 0:
            roll = random.random()
            if roll < 0.33:
                trend, trend_bars = 1,  random.randint(25, 70)
                trend_str = random.uniform(0.25, 0.65)
            elif roll < 0.66:
                trend, trend_bars = -1, random.randint(25, 70)
                trend_str = random.uniform(0.25, 0.65)
            else:
                trend, trend_bars = 0,  random.randint(15, 45)
                trend_str = 0.0
        trend_bars -= 1

        drift = trend * trend_str * daily_atr * 0.12
        noise = random.gauss(0, daily_atr * 0.35)
        chg   = drift + noise
        wick  = abs(random.gauss(0, daily_atr * 0.22))
        o = price
        c = price + chg
        h = max(o, c) + wick
        l = min(o, c) - wick
        price = c

        candles.append({
            'mid': {'o': str(o), 'h': str(h), 'l': str(l), 'c': str(c)},
            'complete': True,
            'time': 'synthetic',
        })
    return candles
