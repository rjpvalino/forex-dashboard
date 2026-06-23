import logging

logger = logging.getLogger(__name__)

# Metrics where a higher-than-expected value is BEARISH for that currency
INVERSE_METRICS = frozenset([
    'unemployment', 'jobless claims', 'initial claims', 'continuing claims',
    'deficit', 'trade deficit', 'current account deficit'
])


class NewsAnalyzer:
    def analyze(self, events):
        by_currency = {}
        for event in events:
            currency = event.get('currency', '').upper().strip()
            if not currency or len(currency) != 3:
                continue
            event['direction'] = self._direction(event)
            by_currency.setdefault(currency, []).append(event)

        # Attach overall bias per currency
        for currency, evts in by_currency.items():
            bullish = sum(1 for e in evts if e['direction'] == 'Bullish')
            bearish = sum(1 for e in evts if e['direction'] == 'Bearish')
            if bullish > bearish:
                bias = 'Bullish'
            elif bearish > bullish:
                bias = 'Bearish'
            else:
                bias = 'Mixed'
            by_currency[currency] = {'events': evts, 'bias': bias}

        return by_currency

    def _direction(self, event):
        impact = event.get('impact', '')
        if impact == 'Holiday':
            return 'Neutral'
        if impact == 'Speech':
            return 'Watch'

        actual = self._parse_num(event.get('actual', ''))
        forecast = self._parse_num(event.get('forecast', ''))

        if actual is None or forecast is None:
            return 'Pending'

        name = event.get('event', '').lower()
        is_inverse = any(kw in name for kw in INVERSE_METRICS)

        if actual > forecast:
            return 'Bearish' if is_inverse else 'Bullish'
        if actual < forecast:
            return 'Bullish' if is_inverse else 'Bearish'
        return 'Neutral'

    def _parse_num(self, raw):
        if not raw or raw.strip() in ('', '-', 'N/A'):
            return None
        cleaned = raw.strip().replace('%', '').replace(',', '').replace(' ', '')
        multipliers = {'K': 1e3, 'M': 1e6, 'B': 1e9, 'T': 1e12}
        if cleaned and cleaned[-1].upper() in multipliers:
            try:
                return float(cleaned[:-1]) * multipliers[cleaned[-1].upper()]
            except ValueError:
                return None
        try:
            return float(cleaned)
        except ValueError:
            return None
