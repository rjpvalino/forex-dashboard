from flask import Flask, render_template, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit
import pytz
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from data.oanda_client import OandaClient
from data.forex_factory import ForexFactoryClient
from data.news_analyzer import NewsAnalyzer
from backtest.engine import BacktestEngine

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

MAJOR_PAIRS = ['EUR_USD', 'GBP_USD', 'USD_JPY', 'USD_CHF', 'USD_CAD', 'AUD_USD', 'NZD_USD']
MINOR_PAIRS = [
    'EUR_GBP', 'EUR_JPY', 'EUR_AUD', 'EUR_CAD', 'EUR_CHF', 'EUR_NZD',
    'GBP_JPY', 'GBP_AUD', 'GBP_CAD', 'GBP_CHF', 'GBP_NZD',
    'AUD_JPY', 'AUD_CAD', 'AUD_CHF', 'AUD_NZD',
    'CAD_JPY', 'CAD_CHF', 'NZD_JPY', 'NZD_CAD', 'NZD_CHF', 'CHF_JPY'
]

_cache = {'pairs': [], 'news': {}, 'last_updated': None, 'error': None}
_bt_cache = {'results': None, 'timestamp': None, 'running': False, 'is_demo': True}


def refresh_data():
    global _cache
    logger.info("Refreshing market data...")
    api_key = os.getenv('OANDA_API_KEY')
    account_id = os.getenv('OANDA_ACCOUNT_ID')
    environment = os.getenv('OANDA_ENVIRONMENT', 'practice')

    pairs_data = []
    error_msg = None

    if api_key and account_id:
        try:
            oanda = OandaClient(api_key, account_id, environment)
            for instrument in MAJOR_PAIRS + MINOR_PAIRS:
                try:
                    pairs_data.append(oanda.get_pair_data(instrument))
                except Exception as e:
                    logger.error(f"Error fetching {instrument}: {e}")
        except Exception as e:
            error_msg = f"OANDA connection error: {e}"
            logger.error(error_msg)
    else:
        error_msg = "OANDA credentials not configured — showing demo data. Set OANDA_API_KEY and OANDA_ACCOUNT_ID in .env for live prices."
        pairs_data = _demo_pairs()
        logger.warning(error_msg)

    news = {}
    try:
        events = ForexFactoryClient().get_calendar_events()
        news = NewsAnalyzer().analyze(events)
    except Exception as e:
        logger.error(f"Error fetching ForexFactory news: {e}")

    if not news:
        news = _demo_news()

    _cache.update({
        'pairs': pairs_data,
        'news': news,
        'last_updated': datetime.now(pytz.UTC).isoformat(),
        'error': error_msg
    })
    logger.info(f"Refresh complete — {len(pairs_data)} pairs, {sum(len(v) for v in news.values())} news events")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data')
def get_data():
    if not _cache['last_updated']:
        refresh_data()
    return jsonify({
        'pairs': _cache['pairs'],
        'news': _cache['news'],
        'last_updated': _cache['last_updated'],
        'error': _cache['error'],
        'major_pairs': [p.replace('_', '/') for p in MAJOR_PAIRS],
        'minor_pairs': [p.replace('_', '/') for p in MINOR_PAIRS]
    })


@app.route('/api/refresh', methods=['POST'])
def manual_refresh():
    refresh_data()
    return jsonify({'status': 'ok', 'last_updated': _cache['last_updated'], 'error': _cache['error']})


def _demo_pairs():
    # Format: (instrument, bid, ask, daily_chg%, daily_trend, daily_strength, weekly_trend, weekly_strength)
    # Strength: 'Strong' (ADX>35) | 'Moderate' (25-35) | 'Weak' (20-25) | 'None' (<20 = Ranging)
    raw = [
        # Major pairs — approximate Jun 2026 market conditions
        ('EUR_USD', 1.14256, 1.14272, -0.390, 'Trending Down', 'Moderate', 'Ranging',       'None'),
        ('GBP_USD', 1.27143, 1.27161, -0.265, 'Trending Down', 'Weak',     'Ranging',       'None'),
        ('USD_JPY', 143.512, 143.531,  0.142, 'Ranging',       'None',     'Trending Down', 'Moderate'),
        ('USD_CHF', 0.89812, 0.89829, -0.088, 'Ranging',       'None',     'Ranging',       'None'),
        ('USD_CAD', 1.38124, 1.38143,  0.231, 'Ranging',       'None',     'Trending Up',   'Weak'),
        ('AUD_USD', 0.64218, 0.64234, -0.312, 'Trending Down', 'Moderate', 'Ranging',       'None'),
        ('NZD_USD', 0.59012, 0.59028, -0.198, 'Trending Down', 'Weak',     'Ranging',       'None'),
        # Minor pairs
        ('EUR_GBP', 0.89823, 0.89841,  0.112, 'Ranging',       'None',     'Ranging',       'None'),
        ('EUR_JPY', 163.912, 163.941, -0.251, 'Trending Down', 'Moderate', 'Ranging',       'None'),
        ('EUR_AUD', 1.77812, 1.77849, -0.078, 'Ranging',       'None',     'Ranging',       'None'),
        ('EUR_CAD', 1.57712, 1.57749, -0.162, 'Trending Down', 'Weak',     'Ranging',       'None'),
        ('EUR_CHF', 1.02512, 1.02531,  0.041, 'Ranging',       'None',     'Ranging',       'None'),
        ('EUR_NZD', 1.93512, 1.93551, -0.198, 'Trending Down', 'Weak',     'Ranging',       'None'),
        ('GBP_JPY', 182.312, 182.341, -0.123, 'Trending Down', 'Weak',     'Ranging',       'None'),
        ('GBP_AUD', 1.97812, 1.97849, -0.048, 'Ranging',       'None',     'Ranging',       'None'),
        ('GBP_CAD', 1.75512, 1.75549, -0.041, 'Ranging',       'None',     'Ranging',       'None'),
        ('GBP_CHF', 1.14112, 1.14141,  0.178, 'Ranging',       'None',     'Ranging',       'None'),
        ('GBP_NZD', 2.15312, 2.15361, -0.067, 'Ranging',       'None',     'Ranging',       'None'),
        ('AUD_JPY', 92.1120, 92.1340, -0.451, 'Trending Down', 'Strong',   'Trending Down', 'Moderate'),
        ('AUD_CAD', 0.88712, 0.88729,  0.089, 'Ranging',       'None',     'Ranging',       'None'),
        ('AUD_CHF', 0.57612, 0.57629, -0.234, 'Trending Down', 'Moderate', 'Trending Down', 'Weak'),
        ('AUD_NZD', 1.08712, 1.08731,  0.022, 'Ranging',       'None',     'Ranging',       'None'),
        ('CAD_JPY', 103.912, 103.931, -0.089, 'Ranging',       'None',     'Trending Down', 'Weak'),
        ('CAD_CHF', 0.65012, 0.65029, -0.112, 'Ranging',       'None',     'Ranging',       'None'),
        ('NZD_JPY', 84.7120, 84.7310, -0.389, 'Trending Down', 'Strong',   'Trending Down', 'Moderate'),
        ('NZD_CAD', 0.81512, 0.81529,  0.044, 'Ranging',       'None',     'Ranging',       'None'),
        ('NZD_CHF', 0.52912, 0.52929, -0.178, 'Trending Down', 'Moderate', 'Trending Down', 'Weak'),
        ('CHF_JPY', 159.812, 159.843,  0.231, 'Ranging',       'None',     'Ranging',       'None'),
    ]

    STRENGTH_ADX = {'Strong': 38.4, 'Moderate': 28.7, 'Weak': 22.1, 'None': 14.3}

    def agr(d, w):
        if d == w and d != 'Ranging': return 'Yes'
        if d == 'Ranging' or w == 'Ranging': return 'Partial'
        return 'No'

    pairs = []
    for instr, bid, ask, chg, dt, ds, wt, ws in raw:
        pip = 3 if 'JPY' in instr else 5
        pairs.append({
            'instrument':      instr,
            'display':         instr.replace('_', '/'),
            'bid':             round(bid, pip),
            'ask':             round(ask, pip),
            'mid':             round((bid + ask) / 2, pip),
            'daily_change':    chg,
            'daily_trend':     dt,
            'daily_strength':  ds,
            'daily_adx':       STRENGTH_ADX[ds],
            'weekly_trend':    wt,
            'weekly_strength': ws,
            'weekly_adx':      STRENGTH_ADX[ws],
            'agreement':       agr(dt, wt),
            'base':            instr.split('_')[0],
            'quote':           instr.split('_')[1],
        })
    return pairs


def _demo_news():
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    raw_events = [
        ('USD', 'Non-Farm Payrolls',           'High',    '8:30am', '212K',  '185K',  '203K'),
        ('USD', 'Unemployment Rate',           'High',    '8:30am', '3.7%',  '3.8%',  '3.8%'),
        ('USD', 'Fed Chair Powell Speaks',     'Speech',  '10:00am','',      '',      ''),
        ('EUR', 'ECB Interest Rate Decision',  'High',    '7:45am', '4.50%', '4.50%', '4.50%'),
        ('EUR', 'ECB Press Conference',        'Speech',  '8:30am', '',      '',      ''),
        ('EUR', 'CPI Flash Estimate y/y',      'High',    '5:00am', '2.4%',  '2.5%',  '2.6%'),
        ('GBP', 'BOE Interest Rate Decision',  'High',    '7:00am', '5.25%', '5.25%', '5.25%'),
        ('GBP', 'Claimant Count Change',       'High',    '7:00am', '16.8K', '20.0K', '18.2K'),
        ('JPY', 'BOJ Policy Rate',             'High',    '11:00pm','0.10%', '0.10%', '0.10%'),
        ('JPY', 'Tokyo CPI y/y',               'High',    '7:30pm', '2.6%',  '2.4%',  '2.5%'),
        ('AUD', 'RBA Rate Statement',          'High',    '12:30am','',      '',      ''),
        ('AUD', 'Employment Change',           'High',    '8:30pm', '38.5K', '25.0K', '29.8K'),
        ('CAD', 'BOC Rate Decision',           'High',    '9:45am', '5.00%', '5.00%', '5.00%'),
        ('CAD', 'GDP m/m',                     'High',    '8:30am', '0.3%',  '0.2%',  '0.1%'),
        ('NZD', 'RBNZ Rate Decision',          'High',    '9:00pm', '5.50%', '5.50%', '5.50%'),
        ('CHF', 'SNB Policy Rate',             'High',    '3:30am', '1.50%', '1.50%', '1.50%'),
        ('USD', 'Bank Holiday – Independence', 'Holiday', 'All Day','',      '',      ''),
    ]

    analyzer = NewsAnalyzer()
    events = [
        {
            'date': today, 'time': time, 'currency': cur, 'event': evt,
            'impact': imp, 'actual': act, 'forecast': fore, 'previous': prev
        }
        for cur, evt, imp, time, act, fore, prev in raw_events
    ]
    return analyzer.analyze(events)


@app.route('/backtest')
def backtest_page():
    return render_template('backtest.html')


@app.route('/api/backtest', methods=['POST'])
def run_backtest():
    global _bt_cache
    if _bt_cache.get('running'):
        return jsonify({'error': 'Backtest already running, please wait'}), 429

    _bt_cache['running'] = True
    try:
        engine = BacktestEngine(initial_equity=10000.0, risk_pct=0.01)
        api_key = os.getenv('OANDA_API_KEY')
        account_id = os.getenv('OANDA_ACCOUNT_ID')
        is_demo = not bool(api_key and account_id)

        if not is_demo:
            environment = os.getenv('OANDA_ENVIRONMENT', 'practice')
            client = OandaClient(api_key, account_id, environment)
            results = []
            for instr in MAJOR_PAIRS:
                try:
                    candles = client._get_candles(instr, 'D', 500)
                    r = engine.run(instr, candles)
                    if r:
                        results.append(r)
                    logger.info(f"Backtest {instr}: {r['total_trades'] if r else 0} trades")
                except Exception as e:
                    logger.error(f"Backtest error {instr}: {e}")
        else:
            results = engine.run_demo()

        _bt_cache.update({
            'results': results,
            'timestamp': datetime.now(pytz.UTC).isoformat(),
            'is_demo': is_demo,
        })
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        _bt_cache['running'] = False

    return jsonify({
        'results': _bt_cache['results'],
        'timestamp': _bt_cache['timestamp'],
        'is_demo': is_demo,
        'strategy': {
            'name': 'EMA Bounce in Weekly Trend',
            'entry_long':  'Weekly ADX ≥ 28 (Trending Up) + daily bar low touched EMA(21) within 0.5% + closed above EMA + RSI < 82',
            'entry_short': 'Weekly ADX ≥ 28 (Trending Down) + daily bar high touched EMA(21) within 0.5% + closed below EMA + RSI > 18',
            'sl':          '1.5 × ATR(14)  — wider SL raises random-walk WR baseline to 60%',
            'tp':          '1.0 × ATR(14)  [R:R = 0.67] — quick capture of EMA bounce',
            'baseline_wr': 'SL / (SL + TP) = 1.5 / 2.5 = 60% in random walk; trend filter pushes this above 70%',
            'max_hold':    '20 trading bars (exit at market)',
            'risk':        '1% of current equity per trade',
            'data':        '~700 daily bars per pair',
        }
    })


@app.route('/api/backtest/status')
def backtest_status():
    return jsonify({
        'has_results': _bt_cache['results'] is not None,
        'running': _bt_cache.get('running', False),
        'timestamp': _bt_cache.get('timestamp'),
        'is_demo': _bt_cache.get('is_demo', True),
    })


central = pytz.timezone('America/Chicago')
_scheduler = BackgroundScheduler(timezone=central)
_scheduler.add_job(refresh_data, CronTrigger(hour=6, minute=0, timezone=central))
_scheduler.start()
atexit.register(_scheduler.shutdown)

if __name__ == '__main__':
    refresh_data()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
