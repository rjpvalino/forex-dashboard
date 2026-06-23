class TrendAnalyzer:
    """
    Trend classification using Wilder's ADX + dual EMA structure.

    ADX measures trend STRENGTH independent of direction:
      < 20  → no meaningful trend (ranging)
      20-25 → weak / developing trend
      25-35 → moderate trend
      > 35  → strong trend

    Direction is confirmed by +DI vs -DI (from the ADX family) AND
    dual EMA structural alignment (price & fast EMA on same side of slow EMA).
    Requiring both guards against false signals from a single indicator.
    """

    EMA_FAST   = 10
    EMA_SLOW   = 21
    ADX_PERIOD = 14

    ADX_RANGING  = 20   # below → ranging
    ADX_WEAK     = 25   # 20-25 → weak trend
    ADX_STRONG   = 35   # > 35  → strong trend

    # Minimum candles needed: ADX warm-up (2×period) + EMA_SLOW
    MIN_CANDLES = ADX_PERIOD * 2 + 21 + 2   # ≈ 51 — callers must supply 50+ D, 52+ W

    def analyze(self, candles):
        return self.analyze_full(candles)['trend']

    def analyze_full(self, candles):
        empty = {'trend': 'Ranging', 'adx': 0.0, 'strength': 'None',
                 'plus_di': 0.0, 'minus_di': 0.0}

        closes = [float(c['mid']['c']) for c in candles]
        highs  = [float(c['mid']['h']) for c in candles]
        lows   = [float(c['mid']['l']) for c in candles]

        if len(closes) < 30:   # absolute minimum for meaningful ADX
            return empty

        adx_val, plus_di, minus_di = self._adx(highs, lows, closes, self.ADX_PERIOD)

        fast_ema = self._ema(closes, self.EMA_FAST)
        slow_ema = self._ema(closes, self.EMA_SLOW)
        if not fast_ema or not slow_ema:
            return empty

        price  = closes[-1]
        f_last = fast_ema[-1]
        s_last = slow_ema[-1]

        bull_structure = price > s_last and f_last > s_last
        bear_structure = price < s_last and f_last < s_last

        is_trending = adx_val >= self.ADX_RANGING

        if is_trending and plus_di > minus_di and bull_structure:
            trend = 'Trending Up'
        elif is_trending and minus_di > plus_di and bear_structure:
            trend = 'Trending Down'
        else:
            trend = 'Ranging'

        if trend == 'Ranging':
            strength = 'None'
        elif adx_val >= self.ADX_STRONG:
            strength = 'Strong'
        elif adx_val >= self.ADX_WEAK:
            strength = 'Moderate'
        else:
            strength = 'Weak'

        return {
            'trend':     trend,
            'adx':       round(adx_val, 1),
            'strength':  strength,
            'plus_di':   round(plus_di, 1),
            'minus_di':  round(minus_di, 1),
        }

    # ── ADX (Wilder's method) ────────────────────────────────────────────
    def _adx(self, highs, lows, closes, period):
        if len(closes) < period * 2 + 2:
            return 0.0, 0.0, 0.0

        trs, pdms, mdms = [], [], []
        for i in range(1, len(closes)):
            h, l, pc = highs[i], lows[i], closes[i - 1]
            ph, pl   = highs[i - 1], lows[i - 1]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
            up, dn = h - ph, pl - l
            pdms.append(up if up > dn and up > 0 else 0.0)
            mdms.append(dn if dn > up and dn > 0 else 0.0)

        # TR / DM: Wilder sum-smoothing (scale = period × avg)
        # Stable: next = prev * (N-1)/N + new_value
        s_tr  = self._wilder_sum(trs,  period)
        s_pdm = self._wilder_sum(pdms, period)
        s_mdm = self._wilder_sum(mdms, period)
        if not s_tr:
            return 0.0, 0.0, 0.0

        # +DI / -DI  (0-100): sums cancel in the ratio
        pdi = [100 * p / t if t > 0 else 0.0 for p, t in zip(s_pdm, s_tr)]
        mdi = [100 * m / t if t > 0 else 0.0 for m, t in zip(s_mdm, s_tr)]

        # DX (0-100)
        dx = [100 * abs(p - m) / (p + m) if (p + m) > 0 else 0.0
              for p, m in zip(pdi, mdi)]

        # ADX: EWM with alpha=1/period so output stays in 0-100
        # Initial = simple average; update = prev*(N-1)/N + new/N
        if len(dx) < period:
            return 0.0, pdi[-1], mdi[-1]
        adx = sum(dx[:period]) / period
        for v in dx[period:]:
            adx = adx * (period - 1) / period + v / period

        return adx, pdi[-1], mdi[-1]

    def _wilder_sum(self, data, period):
        """Sum-scale Wilder smoothing for TR/+DM/-DM.
        Initial = sum of first N; update = prev*(N-1)/N + new.
        Keeps scale proportional to N×avg so DI ratios stay 0-100."""
        if len(data) < period:
            return []
        smoothed = [sum(data[:period])]
        for v in data[period:]:
            smoothed.append(smoothed[-1] * (period - 1) / period + v)
        return smoothed

    def _ema(self, data, period):
        if len(data) < period:
            return []
        k = 2 / (period + 1)
        result = [sum(data[:period]) / period]
        for p in data[period:]:
            result.append(p * k + result[-1] * (1 - k))
        return result
