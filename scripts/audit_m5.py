"""Audit full M5 source files and select active series without using holdout sales."""
import argparse
import csv
import json
import sqlite3
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from prepare_m5 import digest


def rows(path, expected):
    with path.open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected:
            raise ValueError('Unexpected schema in %s: %s' % (path.name, reader.fieldnames))
        for number, row in enumerate(reader, 2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed row %s:%d' % (path.name, number))
            yield row


def audit(raw_dir):
    raw = Path(raw_dir)
    calendar_fields = ['date', 'wm_yr_wk', 'weekday', 'wday', 'month', 'year', 'd', 'event_name_1', 'event_type_1', 'event_name_2', 'event_type_2', 'snap_CA', 'snap_TX', 'snap_WI']
    sales_fields = ['id', 'item_id', 'dept_id', 'cat_id', 'store_id', 'state_id'] + ['d_%d' % n for n in range(1, 1914)]
    price_fields = ['store_id', 'item_id', 'wm_yr_wk', 'sell_price']
    days, weeks = {}, set()
    previous = None
    for row in rows(raw / 'calendar.csv', calendar_fields):
        day = date.fromisoformat(row['date'])
        if row['d'] in days or (previous and day != previous + timedelta(days=1)):
            raise ValueError('Duplicate or nonconsecutive calendar')
        if row['d'] != 'd_%d' % (len(days) + 1):
            raise ValueError('Unexpected calendar day numbering')
        if int(row['year']) != day.year or int(row['month']) != day.month or row['weekday'] != day.strftime('%A'):
            raise ValueError('Calendar date attributes disagree')
        if int(row['wday']) != ((day.weekday() + 2) % 7) + 1:
            raise ValueError('Calendar weekday index disagrees')
        if any(row['snap_' + state] not in ('0', '1') for state in ('CA', 'TX', 'WI')):
            raise ValueError('Invalid SNAP flag')
        days[row['d']] = row['date']
        weeks.add(row['wm_yr_wk'])
        previous = day
    pairs, ids, candidates = set(), set(), []
    zero_cells = 0
    for row in rows(raw / 'sales_train_validation.csv', sales_fields):
        pair = (row['item_id'], row['store_id'])
        if pair in pairs or row['id'] in ids:
            raise ValueError('Duplicate sales series')
        if not all(row[k] for k in sales_fields[:6]):
            raise ValueError('Missing identifier')
        if row['id'] != '_'.join(pair) + '_validation':
            raise ValueError('Unexpected sales identifier')
        values = [int(row['d_%d' % n]) for n in range(1, 1914)]
        if min(values) < 0:
            raise ValueError('Negative sales')
        zero_cells += values.count(0)
        pairs.add(pair)
        ids.add(row['id'])
        if row['store_id'] == 'CA_1':
            training = values[-365:-14]
            candidates.append({'item_id': pair[0], 'store_id': pair[1], 'category': row['cat_id'], 'training_nonzero_days': sum(v > 0 for v in training), 'training_total_units': sum(training)})
    selected = []
    for category, count in [('FOODS', 2), ('HOUSEHOLD', 2), ('HOBBIES', 1)]:
        eligible = sorted((r for r in candidates if r['category'] == category and r['training_nonzero_days'] >= 280), key=lambda r: (-r['training_nonzero_days'], -r['training_total_units'], r['item_id']))
        if len(eligible) < count:
            raise ValueError('Insufficient active candidates in ' + category)
        selected.extend(eligible[:count])
    price_count = zero_prices = 0
    with tempfile.TemporaryDirectory(prefix='marginguard-audit-') as temp:
        db = sqlite3.connect(str(Path(temp) / 'price_keys.sqlite'))
        try:
            db.execute('CREATE TABLE keys (item TEXT, store TEXT, week TEXT, PRIMARY KEY (item, store, week)) WITHOUT ROWID')
            batch = []
            for row in rows(raw / 'sell_prices.csv', price_fields):
                pair = (row['item_id'], row['store_id'])
                if pair not in pairs or row['wm_yr_wk'] not in weeks:
                    raise ValueError('Price reference missing from sales/calendar')
                price = Decimal(row['sell_price'])
                if not price.is_finite() or price < 0:
                    raise ValueError('Invalid price')
                price_count += 1
                zero_prices += price == 0
                batch.append(pair + (row['wm_yr_wk'],))
                if len(batch) == 10000:
                    db.executemany('INSERT INTO keys VALUES (?, ?, ?)', batch)
                    batch.clear()
            db.executemany('INSERT INTO keys VALUES (?, ?, ?)', batch)
        finally:
            db.close()
    return {'schemas': {'calendar.csv': calendar_fields, 'sales_train_validation.csv': sales_fields[:6] + ['d_1 ... d_1913 (1913 consecutive columns)'], 'sell_prices.csv': price_fields},
            'calendar_rows': len(days), 'calendar_start': days['d_1'], 'calendar_end': days['d_%d' % len(days)],
            'sales_series': len(pairs), 'sales_days': 1913, 'sales_start': days['d_1'], 'sales_end': days['d_1913'],
            'sales_cells_checked': len(pairs) * 1913, 'zero_sales_cells': zero_cells, 'price_rows': price_count, 'zero_prices': zero_prices,
            'duplicate_keys': 0, 'invalid_sales_or_prices': 0, 'selected': selected,
            'selection_training_start': days['d_1549'], 'selection_training_end': days['d_1899'],
            'selection_rule': 'CA_1; 2 FOODS, 2 HOUSEHOLD, 1 HOBBIES; at least 280/351 nonzero training days; descending nonzero days then total units, item ID tie-break; holdout excluded',
            'sha256': {name: digest(raw / name) for name in ['calendar.csv', 'sales_train_validation.csv', 'sell_prices.csv']}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', default='data/raw')
    parser.add_argument('--output', default='data/source_audit.json')
    args = parser.parse_args()
    result = audit(args.raw_dir)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
