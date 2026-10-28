"""Fixed, bounded subprocess entry point. Private JSON uses stdin, never argv.

There is no web endpoint for this worker and no dynamic code or pickle loading.
"""
import base64
from datetime import date
from decimal import Decimal
import json
import secrets
import sys


def serial(value):
    if isinstance(value, (date, Decimal)):
        return str(value)
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    return value


def encode_dataset(dataset):
    return dict(currency=dataset['currency'], sales_basis=dataset['sales_basis'],
                as_of_date=str(dataset['as_of_date']),
                groups=[{'item_id': item, 'store_id': store, 'rows': serial(rows)}
                        for (item, store), rows in dataset['groups'].items()])


def decode_dataset(data):
    groups = {}
    for group in data['groups']:
        rows = []
        for record in group['rows']:
            row = dict(record, date=date.fromisoformat(record['date']))
            for field in ('unit_price', 'unit_cost'):
                row[field] = Decimal(row[field]) if row[field] is not None else None
            rows.append(row)
        groups[(group['item_id'], group['store_id'])] = rows
    return dict(source_kind='user_csv', source_verified=False, schema_version=1,
                currency=data['currency'], sales_basis=data['sales_basis'],
                as_of_date=date.fromisoformat(data['as_of_date']), groups=groups)


def perform(action, payload):
    if action == 'parse':
        from business_csv import parse_business_csv
        dataset = parse_business_csv(base64.b64decode(payload['content'], validate=True),
                                     payload['meta']['currency'], sales_basis=payload['meta']['sales_basis'],
                                     as_of_date=date.fromisoformat(payload['as_of_date']))
        series = []
        for report in dataset['report']['series']:
            series.append(dict(report, series_id=secrets.token_hex(16),
                               item_id=report['product'], store_id=report['store']))
        return {'dataset': encode_dataset(dataset), 'meta': payload['meta'],
                'report': dataset['report'], 'series': series}
    if action == 'confirm':
        from business_forecast import analyse_business_series
        pending = payload['pending']
        dataset = decode_dataset(pending['dataset'])
        catalog = {entry['series_id']: entry for entry in pending['series']}
        series = []
        for choice in payload['selections']:
            entry = catalog[choice['series_id']]
            result = analyse_business_series(dataset, entry['item_id'], entry['store_id'],
                                             start_date=choice['start_date'], end_date=choice['end_date'])
            series.append({'series_id': entry['series_id'], 'item_id': entry['item_id'],
                           'store_id': entry['store_id'], 'result': serial(result),
                           'start_date': str(result['analysis']['history_start']),
                           'end_date': str(result['analysis']['history_end']),
                           'observations': result['analysis']['observations']})
        return {'meta': pending['meta'], 'report': pending['report'], 'series': series}
    if action == 'inventory':
        from inventory import inventory_risk
        return inventory_risk(payload['item_id'], payload['daily_demand'], **payload['inputs'])
    if action == 'scenarios':
        from scenario import compare_strategies
        return compare_strategies(payload['daily_demand'], **payload['inputs'], currency=payload['currency'])
    raise ValueError('Unsupported worker operation.')


def apply_resource_limits():
    """Bound workers on production Linux; macOS still has wall/CPU limits.

    RLIMIT_AS semantics vary across systems, so this is not a substitute for a
    hosting memory quota. CSV sizes and output sizes are bounded independently.
    """
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
        if sys.platform.startswith('linux'):
            memory = 384 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    except (ImportError, OSError, ValueError):
        pass


def main():
    # CPU bound survives a parent crash; the caller also enforces wall time.
    apply_resource_limits()
    from business_csv import BusinessCSVError
    from business_forecast import BusinessForecastError
    try:
        message = json.load(sys.stdin)
        output = {'ok': True, 'result': serial(perform(message['action'], message['payload']))}
    except BusinessCSVError as error:
        output = {'ok': False, 'code': error.code, 'error': str(error),
                  'status': 422, 'issues': error.errors, 'error_count': error.error_count}
    except BusinessForecastError as error:
        output = {'ok': False, 'code': error.code, 'error': str(error), 'status': 422}
    except ValueError as error:
        # Engine errors name fields/constraints, not submitted business amounts.
        output = {'ok': False, 'code': 'invalid_calculation', 'error': str(error), 'status': 422}
    except Exception:
        output = {'ok': False, 'code': 'processing_failed',
                  'error': 'The private data could not be processed.', 'status': 503}
    json.dump(output, sys.stdout, allow_nan=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
