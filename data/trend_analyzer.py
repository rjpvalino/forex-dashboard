class TrendAnalyzer:
    """
    Dual EMA + ATR-normalized slope trend detection.

    Trending Up:   price AND fast EMA are above slow EMA,
                   AND slow EMA slope > THRESHOLD × ATR per bar.
    Trending Down: mirror of the above.
    Ranging:       EMAs are tangled, slope is flat, or structural alignment fails.

    Why dual EMA matters: a single EMA flags every shallow pullback as a trend change.
    Requiring fast > slow (or fast < slow) filters out mean-reversion chop.

    Why ATR normalization matters: a 0.0010 move in EUR/USD (1 pip) means something
    very different than 0.0010 in USD/JPY. Normalizing by ATR makes the threshold
    relative to that pair's actual volatility.
    """

    FAST = 10
    SLOW = 21
    ATR_PERIOD = 14
    SLOPE_LOOKBACK = 5   # bars over which to measure slow-EMA slope
    THRESHOLD = 0.09     # slow EMA must move > 0.09 × ATR per bar to call a trend

    def analyze(self, candles):
        closes = [float(c['mid']['c']) for c in candles]
        highs  = [float(c['mid']['h']) for c in candles]
        lows   = [float(c['mid']['l']) for c in candles]

        if len(closes) < self.SLOW + self.SLOPE_LOOKBACK:
            return 'Ranging'

        fast_ema = self._ema(closes, self.FAST)
        slow_ema = self._ema(closes, self.SLOW)

        if len(fast_ema) < self.SLOPE_LOOKBACK + 1 or len(slow_ema) < self.SLOPE_LOOKBACK + 1:
            return 'Ranging'

        price  = closes[-1]
        f_last = fast_ema[-1]
        s_last = slow_ema[-1]

        # Both price AND fast EMA must be on the same side of slow EMA
        bull_structure = price > s_last and f_last > s_last
        bear_structure = price < s_last and f_last < s_last

        # ATR-normalised slope: how many ATR units did slow EMA move per bar?
        atr = self._atr(highs, lows, closes, self.ATR_PERIOD)
        if atr and atr > 0:
            lb = min(self.SLOPE_LOOKBACK, len(slow_ema) - 1)
            slope = (slow_ema[-1] - slow_ema[-(lb + 1)]) / (atr * lb)
        else:
            slope = 0.0

        if bull_structure and slope > self.THRESHOLD:
            return 'Trending Up'
        if bear_structure and slope < -self.THRESHOLD:
            return 'Trending Down'
        return 'Ranging'

    def _ema(self, data, period):
        if len(data) < period:
            return []
        k = 2 / (period + 1)
        result = [sum(data[:period]) / period]
        for price in data[period:]:
            result.append(price * k + result[-1] * (1 - k))
        return result

    def _atr(self, highs, lows, closes, period):
        if len(closes) < 2:
            return None
        trs = [
            max(highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]))
            for i in range(1, len(closes))
        ]
        p = min(period, len(trs))
        return sum(trs[-p:]) / p if p > 0 else None
