import oandapyV20
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.pricing as pricing
from data.trend_analyzer import TrendAnalyzer
import logging

logger = logging.getLogger(__name__)
_analyzer = TrendAnalyzer()


class OandaClient:
    def __init__(self, api_key, account_id, environment='practice'):
        self.api = oandapyV20.API(access_token=api_key, environment=environment)
        self.account_id = account_id

    def get_pair_data(self, instrument):
        mid, bid, ask = self._get_price(instrument)
        # 50 daily candles  → enough history for 21 EMA + 14 ATR + 5-bar slope
        # 52 weekly candles → 1 year of context so slow EMA captures full range cycles
        daily_candles  = self._get_candles(instrument, 'D', 50)
        weekly_candles = self._get_candles(instrument, 'W', 52)

        daily  = _analyzer.analyze_full(daily_candles)
        weekly = _analyzer.analyze_full(weekly_candles)

        daily_change = 0.0
        if len(daily_candles) >= 2:
            prev_close = float(daily_candles[-2]['mid']['c'])
            daily_change = round(((mid - prev_close) / prev_close) * 100, 3) if prev_close else 0.0

        pip_digits = 3 if 'JPY' in instrument else 5

        return {
            'instrument':     instrument,
            'display':        instrument.replace('_', '/'),
            'bid':            round(bid, pip_digits),
            'ask':            round(ask, pip_digits),
            'mid':            round(mid, pip_digits),
            'daily_change':   daily_change,
            'daily_trend':    daily['trend'],
            'daily_adx':      daily['adx'],
            'daily_strength': daily['strength'],
            'weekly_trend':   weekly['trend'],
            'weekly_adx':     weekly['adx'],
            'weekly_strength':weekly['strength'],
            'agreement':      self._agreement(daily['trend'], weekly['trend']),
            'base':           instrument.split('_')[0],
            'quote':          instrument.split('_')[1],
        }

    def _get_price(self, instrument):
        r = pricing.PricingInfo(accountID=self.account_id, params={"instruments": instrument})
        self.api.request(r)
        p = r.response['prices'][0]
        bid = float(p['bids'][0]['price'])
        ask = float(p['asks'][0]['price'])
        return (bid + ask) / 2, bid, ask

    def _get_candles(self, instrument, granularity, count):
        r = instruments.InstrumentsCandles(
            instrument=instrument,
            params={"count": count, "granularity": granularity, "price": "M"}
        )
        self.api.request(r)
        return r.response['candles']

    def _agreement(self, daily, weekly):
        if daily == weekly and daily != 'Ranging':
            return 'Yes'
        if daily == 'Ranging' or weekly == 'Ranging':
            return 'Partial'
        return 'No'
