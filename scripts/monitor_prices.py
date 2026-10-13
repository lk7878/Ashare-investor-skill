"""Read-only public quotes and deduplicated research alerts. Never submits orders."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
from urllib.request import Request, urlopen

CN = timezone(timedelta(hours=8))


def read_quotes(codes):
    symbols = [code if code.startswith(('sh', 'sz')) else
               ('sh' if code.startswith('6') else 'sz') + code for code in codes]
    url = 'https://qt.gtimg.cn/q=' + ','.join(symbols)
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=20) as response:
        raw = response.read().decode('gbk')
    result = {}
    for line in raw.splitlines():
        match = re.search(r'v_(sh|sz)(\d{6})="(.*)"', line)
        if not match:
            continue
        f = match[3].split('~')
        if len(f) < 38:
            continue
        try:
            price, volume = float(f[3]), float(f[6])
            at = datetime.strptime(f[30], '%Y%m%d%H%M%S').replace(tzinfo=CN)
            if not math.isfinite(price) or price <= 0 or not math.isfinite(volume):
                continue
            result[match[2]] = {'name': f[1], 'price': price,
                                'quote_at': at.isoformat(), 'volume_lots': volume,
                                'source': url}
        except (ValueError, IndexError):
            continue
    return result


def price_state(stock, price, today):
    """Price review classification only; financial and account checks remain external."""
    if stock.get('model_invalidated', False):
        return 'MODEL_INVALIDATED', {}
    if stock.get('watch_only', False):
        for level in sorted(stock.get('watch_levels', []), key=lambda item: item['ceiling']):
            ceiling = level['ceiling']
            crossed = price < ceiling if level.get('exclusive', False) else price <= ceiling
            if crossed:
                return level['kind'], {'review_ceiling': ceiling,
                                       'instruction': level['instruction']}
        trigger = stock.get('watch_below')
        return ('WATCH_REVIEW', {}) if trigger is not None and price <= trigger else ('WAIT', {})
    if stock.get('confirmed_shares', 0) > 0:
        crossed = [p for p in stock.get('sell_review_limits', []) if price >= p]
        if crossed:
            return 'SELL_REVIEW_' + str(len(crossed)), {'review_floor': max(crossed)}
    if today < stock.get('buy_start', '1900-01-01'):
        return 'WAIT', {}
    band = stock.get('buy_band')
    if not band:
        return 'WAIT', {}
    if price < band[0]:
        return 'DEEP_DROP_REVALUE', {'old_lower': band[0]}
    if price > band[1]:
        return 'WAIT', {}
    pending = [s for s in stock.get('buy_stages', [])
               if s.get('confirmed_filled', 0) < s['shares']]
    if not pending:
        return 'WAIT', {}
    affordable = [s for s in pending if price <= s['limit']]
    if not affordable:
        return 'BUY_BAND_REVIEW', {}
    # Crossing several levels does not authorize summing all batches.
    first = pending[0]
    return 'BUY_REVIEW_' + affordable[-1]['id'], {
        'pending_batch': first['id'], 'planned_max_limit': first['limit'],
        'planned_remaining_shares': first['shares'] - first.get('confirmed_filled', 0),
        'earliest_execution_date': stock.get('earliest_add_date', stock.get('buy_start')),
        'crossed_batch_ids': [s['id'] for s in affordable],
        'instruction': 'Review fundamentals, liquidity and real cash first. At most one pending batch; no execution inferred.'}


def evaluate(plan, quotes, state, now):
    now = now.astimezone(CN)
    today = now.date().isoformat()
    updated = json.loads(json.dumps(state))
    previous = updated.setdefault('last_state', {})
    sent = updated.setdefault('sent_on', {})
    events, snapshots = [], []

    def emit(code, kind, details):
        token = plan['plan_id'] + ':' + code + ':' + kind
        if previous.get(code) != token and sent.get(token) != today:
            events.append({'code': code, 'kind': kind, **details})
            sent[token] = today
        previous[code] = token

    closed = now.weekday() >= 5 or today in plan.get('closed_dates', [])
    if closed:
        return {'status': 'MARKET_CLOSED', 'as_of': now.isoformat(),
                'events': [], 'quotes': quotes}, updated
    if today > plan['valid_until']:
        emit('PLAN', 'MODEL_EXPIRED', {'valid_until': plan['valid_until']})
        return {'status': 'REVALUATION_REQUIRED', 'events': events, 'quotes': quotes}, updated
    for stock in plan['stocks']:
        code = stock['code']
        quote = quotes.get(code)
        details = {'name': stock['name'], 'confirmed_shares': stock.get('confirmed_shares', 0)}
        if not quote:
            emit(code, 'DATA_MISSING', details)
            continue
        at = datetime.fromisoformat(quote['quote_at']).astimezone(CN)
        age = (now - at).total_seconds()
        if at.date() != now.date() or age > plan.get('max_quote_age_seconds', 600) or age < -120:
            emit(code, 'STALE_QUOTE', {**details, **quote})
            continue
        if quote.get('volume_lots', 0) <= 0:
            emit(code, 'NO_TRADES_VERIFY_SUSPENSION', {**details, **quote})
            continue
        # A refreshed holding may have an earlier research expiry than the
        # surrounding multi-stock plan. Keep fetching its quote, but suppress
        # all old buy/sell levels until a substantive revaluation is recorded.
        stock_until = min(plan['valid_until'], stock.get('valid_until', plan['valid_until']))
        if today > stock_until:
            snapshots.append({**details, **quote, 'price_state': 'MODEL_EXPIRED'})
            emit(code, 'MODEL_EXPIRED', {**details, **quote, 'valid_until': stock_until})
            continue
        kind, extra = price_state(stock, quote['price'], today)
        snapshots.append({**details, **quote, 'price_state': kind})
        old = previous.get(code, '')
        if kind == 'WAIT':
            if old.endswith(('DATA_MISSING', 'STALE_QUOTE', 'NO_TRADES_VERIFY_SUSPENSION')):
                emit(code, 'DATA_RECOVERED', {**details, **quote})
            previous[code] = plan['plan_id'] + ':' + code + ':WAIT'
        else:
            emit(code, kind, {**details, **quote, **extra})
    updated['checked_at'] = now.isoformat()
    # Bound dedup metadata without re-enabling unchanged-state alerts.
    cutoff = (now.date() - timedelta(days=14)).isoformat()
    updated['sent_on'] = {k: v for k, v in sent.items() if v >= cutoff}
    return {'status': 'REVIEW_ALERTS' if events else 'NO_CHANGE',
            'as_of': now.isoformat(), 'events': events, 'snapshots': snapshots,
            'scope': 'Public quote checks only. No financial clearance or broker orders.'}, updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8-sig'))
    state_path = Path(plan['state_path'])
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    try:
        quotes = read_quotes([s['code'] for s in plan['stocks']])
        error = None
    except Exception as exc:
        quotes, error = {}, type(exc).__name__
    output, updated = evaluate(plan, quotes, state, datetime.now(CN))
    if error:
        output['quote_fetch_error'] = error
    if not args.preview:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(state_path)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
