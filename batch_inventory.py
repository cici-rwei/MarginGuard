"""Join confirmed business forecasts and dated stock snapshots for review.

This module performs no forecasting or financial calculation. Every assessed row
calls inventory.inventory_risk unchanged. Product/store matches are exact; stock
must be closing stock on the selected history's final date. Counts classify the
core's primary status, so overlapping warning flags never double-count a row.
"""
from datetime import date, timedelta
from decimal import Decimal
import re

from inventory import inventory_risk
from phase2_inputs import number, units

RISK_CODES = ('stockout', 'reorder_attention', 'excess', 'sufficient', 'not_assessed')
SORT_OPTIONS = ('priority', 'product', 'stock_asc', 'demand_desc')
PRIMARY = {
    'Stockout Risk': ('stockout', 1, 'Evaluate Reorder'),
    'Reorder Attention': ('reorder_attention', 2, 'Evaluate Reorder'),
    'Excess Inventory Attention': ('excess', 3, 'Review Discount Strategy'),
    'Sufficient Inventory': ('sufficient', 4, 'Monitor Inventory'),
}
CLASSIFICATION_NOTE = (
    'Primary inventory categories are mutually exclusive: stockout, replenishment attention, '
    'excess stock, sufficient stock, or not assessed. Products analysed counts confirmed '
    'forecasts and can include rows not assessed for inventory. Priority is a display order, '
    'not a numerical risk score. Counts refer to product-store combinations, not unique products.'
)
DECISION_NOTE = (
    'These are preliminary stock-review actions, not purchasing recommendations. '
    'Review delivery timing, purchase cost, minimum order quantity and available cash '
    'in the Financial Decision Lab before deciding whether to buy.'
)


class BatchInventoryError(ValueError):
    """Invalid trusted adapter input, without echoing private submitted values."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _problem(code, message):
    return {'code': code, 'message': message}


def _day(value):
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError('A valid YYYY-MM-DD date is required.')


def _identity(row):
    product = row.get('product', row.get('item_id'))
    store = row.get('store', row.get('store_id'))
    if not isinstance(product, str) or not product.strip() or not isinstance(store, str) or not store.strip():
        raise BatchInventoryError('invalid_catalog', 'Every sales series needs a Product and Store identifier.')
    return product, store


def _confirmed_forecast(entry, product, store):
    """Validate stored forecast structure; never invent or refit a missing result."""
    if not isinstance(entry, dict) or not isinstance(entry.get('result'), dict):
        raise ValueError('Confirm a complete sales-history window before assessment.')
    result = entry['result']
    if (result.get('product'), result.get('store')) != (product, store):
        raise ValueError('The confirmed forecast does not match this product and store.')
    analysis, history = result.get('analysis'), result.get('history')
    if not isinstance(analysis, dict) or not isinstance(history, list) or len(history) < 42:
        raise ValueError('At least 42 consecutive known daily observations must be confirmed.')
    start, end = _day(entry.get('start_date')), _day(entry.get('end_date'))
    if _day(analysis.get('history_start')) != start or _day(analysis.get('history_end')) != end:
        raise ValueError('The confirmed forecast dates do not match the selected history window.')
    if ((end - start).days + 1 != len(history) or entry.get('observations') != len(history)
            or analysis.get('observations') != len(history)):
        raise ValueError('The confirmed history must contain exactly one known observation per day.')
    for offset, observed in enumerate(history):
        if not isinstance(observed, dict) or _day(observed.get('date')) != start + timedelta(days=offset):
            raise ValueError('The confirmed history contains a missing or unknown date.')
        amount = observed.get('units_sold')
        if type(amount) is not int or not 0 <= amount <= 1000000:
            raise ValueError('The confirmed history contains unknown or invalid daily sales.')
    future = analysis.get('future')
    if not isinstance(future, list) or len(future) != 14:
        raise ValueError('A confirmed 14-day forecast is required.')
    demand = []
    for offset, prediction in enumerate(future, 1):
        if not isinstance(prediction, dict) or _day(prediction.get('date')) != end + timedelta(days=offset):
            raise ValueError('The forecast must start after the selected history and cover 14 consecutive dates.')
        number(prediction.get('prediction'), 'daily forecast', 1000000)
        demand.append(prediction['prediction'])
    method = analysis.get('selected_method')
    if method not in ('moving_average_7', 'same_weekday_4'):
        raise ValueError('A supported confirmed forecast method is required.')
    backtest = analysis.get('backtest')
    if not isinstance(backtest, dict) or not isinstance(backtest.get(method), dict):
        raise ValueError('The selected method needs its chronological validation result.')
    mae = backtest[method].get('mae')
    number(mae, 'average forecast error')
    total = analysis.get('total_forecast_demand')
    number(total, 'forecast demand')
    return {
        'forecast_start': (end + timedelta(days=1)).isoformat(),
        'forecast_end': (end + timedelta(days=14)).isoformat(),
        'expected_stock_date': end.isoformat(), 'forecast_demand': total,
        'forecast_method': method, 'mae': mae, 'daily_demand': demand,
    }


def _unconfirmed_issues(source):
    issues = []
    if source.get('missing_dates'):
        issues.append(_problem('missing_dates', 'Some daily sales dates are missing. They remain unknown, not zero.'))
    if source.get('unknown_sales_dates'):
        issues.append(_problem('unknown_sales', 'Some daily sales values are unknown. Supply known values or choose a complete window.'))
    longest = source.get('longest_continuous_days')
    if type(longest) is int and longest < 42:
        issues.append(_problem('insufficient_history', 'At least 42 consecutive dates with known sales are needed; 84 days are recommended.'))
    else:
        issues.append(_problem('forecast_not_selected', 'Confirm a complete sales-history window of at least 42 days before assessing this combination.'))
    return issues


def _inventory_index(inventory, max_series):
    if inventory is None:
        return {}, []
    if not isinstance(inventory, dict) or not isinstance(inventory.get('rows'), list):
        raise BatchInventoryError('invalid_inventory', 'Use validated inventory snapshot rows.')
    if len(inventory['rows']) > max_series:
        raise BatchInventoryError('too_many_inventory_rows', 'Inventory snapshots exceed the permitted series limit.')
    indexed, unidentified = {}, []
    for row in inventory['rows']:
        if not isinstance(row, dict):
            raise BatchInventoryError('invalid_inventory', 'Use validated inventory snapshot rows.')
        product, store = row.get('product'), row.get('store')
        if not isinstance(product, str) or not product or not isinstance(store, str) or not store:
            unidentified.append(row)
            continue
        key = product, store
        if key in indexed:
            raise BatchInventoryError('duplicate_inventory', 'Keep one stock snapshot per product and store.')
        indexed[key] = row
    return indexed, unidentified


def build_risk_overview(payload, *, max_series):
    """Return all sales combinations, keeping unassessed rows and exact reasons.

    ``payload`` is the private, confirmed dataset, not browser-supplied forecast
    values. Catalog rows retain unconfirmed and insufficient-history combinations.
    ``inventory_inputs`` contains only the five valid engine inputs when assessed;
    the caller supplies ``excess_cover_days`` explicitly in the inventory bundle.
    Dates are ISO strings; unmodified engine Decimal values use the caller's
    existing serializer. No input object is changed.
    """
    if type(max_series) is not int or not 1 <= max_series <= 100:
        raise BatchInventoryError('invalid_limit', 'Supply a series limit from 1 to 100.')
    if not isinstance(payload, dict) or not isinstance(payload.get('series'), list):
        raise BatchInventoryError('invalid_dataset', 'Use a confirmed business dataset.')
    catalog = payload.get('catalog_series', payload['series'])
    if not isinstance(catalog, list) or len(catalog) > max_series or len(payload['series']) > max_series:
        raise BatchInventoryError('too_many_series', 'The sales catalog exceeds the permitted series limit.')
    confirmed, catalog_keys, series_ids = {}, set(), set()
    for entry in payload['series']:
        if not isinstance(entry, dict):
            raise BatchInventoryError('invalid_dataset', 'Use confirmed product-store records.')
        key = _identity(entry)
        if key in confirmed:
            raise BatchInventoryError('duplicate_series', 'Each product and store must have only one confirmed window.')
        confirmed[key] = entry
    inventory = payload.get('inventory')
    indexed, unidentified = _inventory_index(inventory, max_series)
    rows, matched, mismatches = [], set(), 0
    for source in catalog:
        if not isinstance(source, dict):
            raise BatchInventoryError('invalid_catalog', 'Use valid sales catalog records.')
        product, store = key = _identity(source)
        series_id = source.get('series_id')
        if not isinstance(series_id, str) or not series_id:
            raise BatchInventoryError('invalid_catalog', 'Every sales combination needs its validated series identifier.')
        if key in catalog_keys or series_id in series_ids:
            raise BatchInventoryError('duplicate_series', 'Each sales catalog combination and identifier must be unique.')
        catalog_keys.add(key)
        series_ids.add(series_id)
        snapshot = indexed.get(key)
        if snapshot is not None:
            matched.add(key)
        row = {
            'series_id': series_id, 'item_id': product, 'store_id': store,
            'forecast_start': None, 'forecast_end': None, 'forecast_demand': None,
            'forecast_method': None, 'mae': None, 'expected_stock_date': None,
            'current_stock': snapshot.get('current_stock') if snapshot else None,
            'stock_as_of_date': snapshot.get('stock_as_of_date') if snapshot else None,
            'assessment_status': 'not_assessed', 'status': 'Not assessed',
            'risk_code': 'not_assessed', 'priority': 5,
            'action': 'Complete Missing Data', 'action_reason': '',
            'assessment_provenance': ('Stock quantities and their dates are user-provided and not independently verified. '
                                      'Supplier delivery time, backup stock and the excess-stock coverage threshold are planning assumptions. '
                                      'On-order units are not available stock; missing on-order units become zero only after explicit confirmation.'),
            'issues': [], 'inventory_inputs': None, 'risk': None,
        }
        selected = confirmed.get(key)
        daily_demand = None
        if selected is None:
            row['issues'].extend(_unconfirmed_issues(source))
        else:
            try:
                if selected.get('series_id') != series_id:
                    raise ValueError('The confirmed series identifier does not match the catalog.')
                forecast = _confirmed_forecast(selected, product, store)
                daily_demand = forecast.pop('daily_demand')
                row.update(forecast)
            except (ValueError, TypeError, OverflowError, KeyError):
                row['issues'].append(_problem('invalid_confirmed_forecast', 'The confirmed forecast is incomplete or inconsistent. Review and confirm a complete history window again.'))
        if snapshot is None:
            row['issues'].append(_problem('missing_inventory', 'Provide a matching Product and Store stock snapshot; current stock is unknown.'))
        else:
            if snapshot.get('stock_as_of_date') is None:
                row['issues'].append(_problem('missing_stock_date', 'Enter the closing-stock date matching the selected history final day.'))
            else:
                try:
                    snapshot_day = _day(snapshot['stock_as_of_date']).isoformat()
                    row['stock_as_of_date'] = snapshot_day
                    if row['expected_stock_date'] and snapshot_day != row['expected_stock_date']:
                        mismatches += 1
                        row['issues'].append(_problem('snapshot_date_mismatch', 'Stock As Of Date must exactly match the selected sales-history final date. Stock is not moved between dates.'))
                except ValueError:
                    row['issues'].append(_problem('invalid_stock_date', 'Enter a valid YYYY-MM-DD closing-stock date.'))
            inputs = {}
            for field, label in (('current_stock', 'Current stock'), ('lead_time_days', 'Supplier delivery time'),
                                 ('safety_stock', 'Backup stock'), ('on_order_units', 'On-order units')):
                value = snapshot.get(field)
                if value is None and field == 'on_order_units' and inventory.get('assume_no_on_order') is True:
                    value = 0
                if value is None:
                    row['issues'].append(_problem('missing_' + field, label + ' is unknown. Enter a value' + (' or explicitly confirm there are no pending orders.' if field == 'on_order_units' else '.')))
                    continue
                try:
                    inputs[field] = units(value, field, 365 if field == 'lead_time_days' else 1000000)
                except ValueError:
                    row['issues'].append(_problem('invalid_' + field, label + ' must be a valid nonnegative whole number within the supported limit.'))
            threshold = inventory.get('excess_cover_days')
            if threshold is None:
                row['issues'].append(_problem('missing_excess_cover_days', 'Set the excess-stock coverage threshold in days before assessment.'))
            else:
                try:
                    threshold = number(threshold, 'excess stock coverage threshold', 3650)
                    if not threshold:
                        raise ValueError('A positive coverage threshold is required.')
                except ValueError:
                    row['issues'].append(_problem('invalid_excess_cover_days', 'Set an excess-stock coverage threshold greater than zero and at most 3,650 days.'))
            if not row['issues'] and daily_demand is not None:
                risk = inventory_risk(product, daily_demand, **inputs, excess_cover_days=threshold)
                risk_code, priority, action = PRIMARY[risk['status']]
                row.update(assessment_status='assessed', status=risk['status'], risk_code=risk_code,
                           priority=priority, action=action, action_reason=risk['explanation'] + ' ' + DECISION_NOTE,
                           inventory_inputs=dict(inputs, excess_cover_days=threshold), risk=risk)
                if snapshot.get('on_order_units') is None:
                    row['issues'].append(_problem('assumed_no_on_order', 'On-order units are zero only because you explicitly declared no pending orders.'))
        if row['assessment_status'] == 'not_assessed':
            row['action_reason'] = ' '.join(issue['message'] for issue in row['issues'])
        rows.append(row)
    if set(confirmed) - catalog_keys:
        raise BatchInventoryError('invalid_catalog', 'Confirmed series must belong to the same sales catalog.')
    unmatched = [dict(product=row.get('product'), store=row.get('store'), stock_as_of_date=row.get('stock_as_of_date'))
                 for key, row in indexed.items() if key not in matched]
    unmatched.extend(dict(product=row.get('product'), store=row.get('store'), stock_as_of_date=row.get('stock_as_of_date'))
                     for row in unidentified)
    counts = {code: sum(row['risk_code'] == code for row in rows) for code in RISK_CODES}
    summary = {
        'total_products': len(rows),
        'products_analysed': sum(row['forecast_start'] is not None for row in rows),
        'high_stockout_risk': counts['stockout'], 'reorder_attention': counts['reorder_attention'],
        'excess_inventory_risk': counts['excess'], 'sufficient_inventory': counts['sufficient'],
        'data_incomplete': counts['not_assessed'], 'classification_note': CLASSIFICATION_NOTE,
    }
    overview = {
        'summary': summary, 'rows': rows,
        'stores': sorted({row['store_id'] for row in rows}), 'filtered_count': len(rows),
        'inventory_quality': {
            'provided': inventory is not None,
            'row_count': len(inventory['rows']) if inventory else 0,
            'matched_rows': len(matched), 'unmatched_rows': len(unmatched),
            'unmatched': unmatched, 'date_mismatch_count': mismatches,
            'missing_snapshot_count': sum('missing_inventory' in {issue['code'] for issue in row['issues']} for row in rows),
            'assumed_no_on_order_count': sum('assumed_no_on_order' in {issue['code'] for issue in row['issues']} for row in rows),
            'report': inventory.get('report', {}) if inventory else {},
        },
        'decision_note': DECISION_NOTE,
        'period_note': 'Each product-store row uses its own confirmed 14-day forecast dates. Different periods are not combined into a total demand or financial result.',
    }
    return filter_risk_overview(overview)


def filter_risk_overview(overview, risk='all', store=None, search='', sort='priority'):
    """Filter/sort display rows while retaining full-dataset summary counts."""
    if risk not in ('all',) + RISK_CODES or sort not in SORT_OPTIONS:
        raise BatchInventoryError('invalid_filter', 'Select a supported risk filter and sort order.')
    if store is not None and not isinstance(store, str) or not isinstance(search, str):
        raise BatchInventoryError('invalid_filter', 'Store and search filters must be text.')
    query = search.strip().casefold()
    rows = [row for row in overview['rows']
            if (risk == 'all' or row['risk_code'] == risk)
            and (store is None or row['store_id'] == store)
            and (not query or query in row['item_id'].casefold() or query in row['store_id'].casefold())]
    def key(row):
        tie = row['item_id'].casefold(), row['store_id'].casefold(), row['series_id']
        if sort == 'priority':
            return (row['priority'],) + tie
        if sort == 'product':
            return tie
        value = row['current_stock'] if sort == 'stock_asc' else row['forecast_demand']
        if value is None:
            return (True, Decimal(0)) + tie
        numeric = Decimal(str(value))
        return (False, numeric if sort == 'stock_asc' else -numeric) + tie
    return dict(overview, rows=sorted(rows, key=key), filtered_count=len(rows))
