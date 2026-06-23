import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
import time

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.forexfactory.com/',
}


class ForexFactoryClient:
    BASE_URL = 'https://www.forexfactory.com/calendar'

    def get_calendar_events(self):
        events = []
        for week in ('this', 'next'):
            try:
                url = f'{self.BASE_URL}?week={week}'
                resp = requests.get(url, headers=HEADERS, timeout=20)
                resp.raise_for_status()
                events.extend(self._parse(resp.text))
                time.sleep(1.5)
            except Exception as e:
                logger.error(f'ForexFactory fetch failed ({week} week): {e}')
        return events

    def _parse(self, html):
        soup = BeautifulSoup(html, 'lxml')
        table = soup.find('table', class_='calendar__table')
        if not table:
            logger.warning('ForexFactory calendar table not found — site structure may have changed')
            return []

        events = []
        current_date = None

        for row in table.find_all('tr', class_=lambda c: c and 'calendar__row' in c):
            # Update running date
            date_cell = row.find('td', class_='calendar__date')
            if date_cell:
                raw = date_cell.get_text(strip=True)
                if raw:
                    parsed = self._parse_date(raw)
                    if parsed:
                        current_date = parsed

            impact = self._impact(row)
            if impact not in ('High', 'Holiday', 'Speech'):
                continue

            currency = self._text(row, 'calendar__currency')
            event_name = self._event_name(row)
            if not currency or not event_name:
                continue

            events.append({
                'date': current_date.strftime('%Y-%m-%d') if current_date else '',
                'time': self._text(row, 'calendar__time'),
                'currency': currency,
                'event': event_name,
                'impact': impact,
                'actual': self._text(row, 'calendar__actual'),
                'forecast': self._text(row, 'calendar__forecast'),
                'previous': self._text(row, 'calendar__previous'),
            })

        return events

    def _impact(self, row):
        cell = row.find('td', class_='calendar__impact')
        if not cell:
            return None
        span = cell.find('span')
        if not span:
            return None
        classes = ' '.join(span.get('class', []))
        if 'red' in classes:
            return 'High'
        if 'orange' in classes:
            return 'Medium'
        if 'yellow' in classes:
            return 'Low'
        if 'gray' in classes or 'grey' in classes:
            return 'Holiday'
        if 'speak' in classes or 'speech' in classes:
            return 'Speech'
        return None

    def _event_name(self, row):
        cell = row.find('td', class_='calendar__event')
        if not cell:
            return ''
        span = cell.find('span', class_='calendar__event-title')
        return span.get_text(strip=True) if span else cell.get_text(strip=True)

    def _text(self, row, cls):
        cell = row.find('td', class_=cls)
        return cell.get_text(strip=True) if cell else ''

    def _parse_date(self, raw):
        year = datetime.now().year
        parts = raw.strip().split()
        # Formats: "Mon Jun 23" or "Jun 23"
        try:
            if len(parts) >= 3:
                return datetime.strptime(f'{parts[1]} {parts[2]} {year}', '%b %d %Y')
            if len(parts) == 2:
                return datetime.strptime(f'{parts[0]} {parts[1]} {year}', '%b %d %Y')
        except ValueError:
            pass
        return None
